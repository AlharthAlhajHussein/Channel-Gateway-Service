import hmac
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Header, HTTPException, Response
from helpers.config import settings
from models.in_out_messages import IncomingMessage, PlatformType

# Import our new services
from services.normalizers import parse_telegram_payload
from services.core_platform_api_client import lookup_agent_routing_data
from services.pubsub_publisher import publish_incoming_message
from services.media_handler import get_telegram_media_bytes, upload_media_to_gcs

logger = logging.getLogger("uvicorn.error")

telegram_router = APIRouter(
    prefix="/webhooks/telegram", 
    tags=["Telegram"]
)

@telegram_router.post("/{identifier}")
async def receive_telegram_message(
    identifier: str, 
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None) 
):
    # 1. Security Check (Phase 2)
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(x_telegram_bot_api_secret_token, settings.telegram_webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid secret token")

    payload = await request.json()

    # 2. Normalize and Filter (Phase 3)
    parsed_data = parse_telegram_payload(payload)
    if not parsed_data:
        # It was an image, an edit, or unsupported. 
        # Return 200 OK immediately so Telegram drops it and doesn't retry.
        return Response(status_code=200)
    parsed_data['sender_info']['bot_identifier'] = identifier
    
    # 3. Lookup Real Agent ID from Core Platform (Phase 1 logic)
    # We use the 'identifier' from the URL (the Telegram Bot ID)
    try:
        routing_data = await lookup_agent_routing_data(
            platform=PlatformType.TELEGRAM, 
            receiver_identifier=identifier
        )
    except HTTPException:
        # If the bot isn't registered in our DB, we drop the message safely
        logger.warning(f"Message received for unregistered bot: {identifier}")
        return Response(status_code=200)

    # 4. === MULTIMODAL ROUTING & GCS UPLOAD ===
    message_type = parsed_data.get("message_type", "text")
    media_url = None
    
    # Handle Images and Voices. (Assumes parse_telegram_payload now outputs `message_type` properly)
    # We execute this pipeline if media_id exists.
    if message_type in ["image", "voice", "text_and_image"] and parsed_data.get("media_id"):
        logger.info(f"[Telegram] {message_type} received. Processing media...")
        bot_token = routing_data.get("telegram_token")
        
        try:
            # 1. Stream raw bytes from Telegram
            media_bytes, mime_type = await get_telegram_media_bytes(parsed_data["media_id"], bot_token)
            
            # 2. Safely determine file extension and force correct MIME type based on our message_type
            if message_type == "voice":
                file_ext = "ogg"
                if mime_type == "application/octet-stream":
                    mime_type = "audio/ogg"
            else:
                file_ext = "jpg"
                if mime_type == "application/octet-stream":
                    mime_type = "image/jpeg"
                    
            # 3. Generate an absolutely unique filename to prevent collisions
            unique_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{file_ext}"
            
            # 4. Enforce exact inbound-media path
            gcs_path = f"inbound-media/{routing_data.get('company_id', 'unknown_company')}/{routing_data['agent_id']}/{unique_filename}"
            
            # 5. Stream to Cloud Storage
            media_url = await upload_media_to_gcs(media_bytes, gcs_path, mime_type)
            logger.info(f"[GCS Upload Success] Saved to: {media_url}")
            
        except Exception as e:
            logger.error(f"[Telegram] Media pipeline failed: {e}")
            return Response(status_code=200) # ALWAYS return 200 so Telegram doesn't infinite loop

    # 5. Standardize into the Pydantic Model
    incoming_msg = IncomingMessage(
        platform=PlatformType.TELEGRAM,
        sender_info=parsed_data["sender_info"],
        destination_agent_id=routing_data["agent_id"],
        text=parsed_data.get("text"),
        message_type=message_type,
        media_url=media_url
    )
    logger.info(f"[Normalized] {incoming_msg.platform.value} msg from: {incoming_msg.sender_info} to Agent Id: {incoming_msg.destination_agent_id}")

    # 5. Publish to GCP Pub/Sub
    try:
        await publish_incoming_message(incoming_msg)
        # logger.info(f"[PUBLISH] Final Output: {incoming_msg}")
    except Exception:
        # If Pub/Sub is down, return a 500. 
        # Telegram will see the 500 and hold onto the message to retry it later!
        raise HTTPException(status_code=500, detail="Internal queue error")

    # 6. Success! Return 200 OK
    return Response(status_code=200)