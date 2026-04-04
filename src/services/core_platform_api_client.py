import httpx
import json
import logging
from fastapi import HTTPException
from helpers import settings
from models.in_out_messages import PlatformType
from .redis_client import get_redis

logger = logging.getLogger("uvicorn.error")

# Global HTTPX client
http_client: httpx.AsyncClient = None

def init_http_client():
    global http_client
    http_client = httpx.AsyncClient(
        base_url=settings.core_platform_api_url,
        # Using the internal secret we discussed earlier
        headers={"X-Internal-Secret": settings.core_platform_api_key},
        timeout=10.0
    )

async def close_http_client():
    if http_client:
        await http_client.aclose()

async def lookup_agent_routing_data(platform: str, receiver_identifier: str) -> dict:
    """
    Looks up the internal agent_id and credentials using the platform's public ID 
    (e.g., WhatsApp Business Phone ID or Telegram Bot ID).
    Implements a Cache-Aside pattern using Redis to prevent overwhelming the Core DB.
    """
    redis_client = await get_redis()
    
    # Cache key is now based on what we know from the webhook
    cache_key = f"agent_config:{platform}:{receiver_identifier}"

    # 1. Try Cache First (Microsecond response time)
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        logger.info(f"Cache HIT for {platform} identifier: {receiver_identifier}")
        return json.loads(cached_data)

    # 2. Cache Miss: Ask Core Platform to translate identifier -> agent_id + tokens
    logger.info(f"Cache MISS. Fetching routing data for {platform} identifier: {receiver_identifier}")
    try:
        params = {}
        if platform == PlatformType.TELEGRAM:
            params["telegram_bot_username"] = receiver_identifier
        elif platform == PlatformType.WHATSAPP:
            params["whatsapp_number"] = receiver_identifier
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        response = await http_client.get(
            "/internal/agents/config",
            params=params
        )
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="No agent linked to this identifier")
            
        response.raise_for_status()
        data = response.json()
        
        routing_data = {
            "company_id": str(data.get("company_id")),
            "agent_id": str(data.get("id")),
            "platform": platform,
            "telegram_token": data.get("telegram_token"),
            "whatsapp_token": data.get("whatsapp_token"),
            "rag_container_id": data.get("rag_container_id")
        }
        # 3. Store in Cache (TTL of 1 hour)
        await redis_client.setex(cache_key, 600, json.dumps(routing_data))
        return routing_data

    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"Routing lookup failed for {receiver_identifier}. Status: {e.response.status_code}")
        raise HTTPException(status_code=404, detail="No agent linked to this identifier")
    except Exception as e:
        logger.error(f"Core API connection error during lookup: {e}")
        raise HTTPException(status_code=500, detail="Internal routing engine error")