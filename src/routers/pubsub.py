import base64
import json
import logging
from fastapi import APIRouter, HTTPException, Response
from pydantic import ValidationError
from models.in_out_messages import OutgoingMessage, PlatformType
from routers.schems.pubsub import PubSubPushRequest

# Import the core client from Phase 1 and our new dispatchers
from services.core_platform_api_client import lookup_agent_routing_data 
from services.dispatchers import send_telegram_message, send_whatsapp_message

logger = logging.getLogger("uvicorn.error")

pubsub_router = APIRouter(
    prefix="/pubsub", 
    tags=["Pub/Sub"]
)

@pubsub_router.post("/outbound-push")
async def handle_outbound_pubsub_push(request: PubSubPushRequest):
    """Receives AI responses from Pub/Sub and delivers them to the user."""
    try:
        # 1. Decode Base64 Payload
        decoded_bytes = base64.b64decode(request.message.data)
        decoded_str = decoded_bytes.decode("utf-8")
        payload_dict = json.loads(decoded_str)
        
        # 2. Validate using Pydantic
        outgoing_msg = OutgoingMessage(**payload_dict)
        logger.info(f"\n[Outbound] Routing message to {outgoing_msg.platform.value} user {outgoing_msg.sender_info}")

        # 3. Credential Hydration (Fetch from Redis/Core API)
        # Note: Your Core API needs to return the specific tokens and WhatsApp phone ID
        creds = await lookup_agent_routing_data(outgoing_msg.platform, outgoing_msg.sender_info["username"])
        
        # 4. Platform Dispatcher
        if outgoing_msg.platform == PlatformType.TELEGRAM:
            bot_token = creds.get("telegram_token")
            if not bot_token:
                logger.error(f"Missing Telegram token for agent {outgoing_msg.destination_agent_id}")
                return Response(status_code=200) # Drop message, config error
                
            await send_telegram_message(outgoing_msg, bot_token)

        elif outgoing_msg.platform == PlatformType.WHATSAPP:
            access_token = creds.get("whatsapp_token")
            phone_number_id = creds.get("whatsapp_phone_number_id")
            
            if not access_token or not phone_number_id:
                logger.error(f"Missing WhatsApp config for agent {outgoing_msg.destination_agent_id}")
                return Response(status_code=200) # Drop message, config error
                
            await send_whatsapp_message(outgoing_msg, phone_number_id, access_token)

        # 5. Success -> ACK (Return 200 to delete message from queue)
        return Response(status_code=200)

    except ValidationError as e:
        logger.error(f"[Outbound Error] Invalid Payload structure: {e}")
        # Return 200 OK to drop bad payloads permanently.
        return Response(status_code=200) 
        
    except HTTPException as e:
        # This was raised by our dispatcher (5xx error) or credential lookup.
        # We allow this to bubble up and return the 500 status so Pub/Sub retries.
        raise e
        
    except Exception as e:
        logger.error(f"[Outbound Error] Unexpected failure: {e}")
        # Return 500 to NACK and retry later
        raise HTTPException(status_code=500, detail="Internal Server Error")