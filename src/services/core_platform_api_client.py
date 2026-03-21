import httpx
import json
import logging
from fastapi import HTTPException
from helpers import settings
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
        timeout=5.0
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
    cache_key = f"route:{platform}:{receiver_identifier}"

    # 1. Try Cache First (Microsecond response time)
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        logger.info(f"Cache HIT for {platform} identifier: {receiver_identifier}")
        return json.loads(cached_data)

    # 2. Cache Miss: Ask Core Platform to translate identifier -> agent_id + tokens
    logger.info(f"Cache MISS. Fetching routing data for {platform} identifier: {receiver_identifier}")
    try:
        # response = await http_client.get(
        #     "/internal/agents/lookup",
        #     params={"platform": platform, "identifier": receiver_identifier}
        # )
        # response.raise_for_status()
        # routing_data = response.json()
        routing_data = {"agent_id": "agent-1", "platform": "telegram", "telegram_token": settings.telegram_bot_token, "telegram_identifier": settings.telegram_bot_identifier}
        # 3. Store in Cache (TTL of 1 hour)
        await redis_client.setex(cache_key, 3600, json.dumps(routing_data))
        return routing_data

    except httpx.HTTPStatusError as e:
        logger.error(f"Routing lookup failed for {receiver_identifier}. Status: {e.response.status_code}")
        # If the number isn't in our DB, return 404 so we can drop the message
        raise HTTPException(status_code=404, detail="No agent linked to this identifier")
    except Exception as e:
        logger.error(f"Core API connection error during lookup: {e}")
        raise HTTPException(status_code=500, detail="Internal routing engine error")