import hmac
import hashlib
import logging
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query, Header, HTTPException, Response
from helpers.config import settings
from models.in_out_messages import IncomingMessage, PlatformType

# Import our internal services
from services.normalizers import parse_whatsapp_payload
from services.core_platform_api_client import lookup_agent_routing_data
from services.pubsub_publisher import publish_incoming_message
from services.media_handler import get_whatsapp_media_bytes, upload_media_to_gcs

logger = logging.getLogger("uvicorn.error")

whatsapp_router = APIRouter(
    prefix="/webhooks/whatsapp", 
    tags=["WhatsApp"]
)

@whatsapp_router.get("")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: int = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """Handles Meta's one-time Webhook Verification Handshake."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("[WhatsApp] Webhook verified successfully by Meta.")
        return Response(content=str(hub_challenge), media_type="text/plain")
    
    logger.error("[WhatsApp] Webhook verification failed. Invalid token or mode.")
    raise HTTPException(status_code=403, detail="Verification failed")


@whatsapp_router.post("")
async def receive_whatsapp_message(
    request: Request,
    x_hub_signature_256: str = Header(None)
):
    # 1. Security Check
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing signature header")

    raw_body = await request.body()
    expected_signature = hmac.new(
        key=settings.whatsapp_app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    expected_signature_header = f"sha256={expected_signature}"

    if not hmac.compare_digest(expected_signature_header, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid payload signature")

    payload = json.loads(raw_body.decode("utf-8"))

    # 2. Normalize and Filter
    parsed_data = parse_whatsapp_payload(payload)
    if not parsed_data:
        return Response(status_code=200)

    # 3. Lookup Real Agent ID & Credentials from Core Platform
    receiver_identifier = parsed_data["receiver_identifier"]
    try:
        routing_data = await lookup_agent_routing_data(
            platform=PlatformType.WHATSAPP, 
            receiver_identifier=receiver_identifier
        )
    except HTTPException:
        logger.warning(f"[WhatsApp] Message received for unregistered phone ID: {receiver_identifier}")
        return Response(status_code=200)

    # 4. === MULTIMODAL ROUTING & GCS UPLOAD ===
    message_type = parsed_data.get("message_type", "text")
    media_url = None

    if message_type in ["image", "voice", "text_and_image"] and parsed_data.get("media_id"):
        logger.info(f"[WhatsApp] {message_type} received. Processing media...")
        access_token = routing_data.get("whatsapp_token")
        
        if not access_token:
            logger.error(f"[WhatsApp] Missing access token for agent {routing_data['agent_id']}")
            return Response(status_code=200)

        try:
            # 1. Stream raw bytes from Meta's Graph API
            media_bytes, mime_type = await get_whatsapp_media_bytes(parsed_data["media_id"], access_token)
            
            # 2. Safely determine file extension and force correct MIME type based on our message_type
            if message_type == "voice":
                file_ext = "ogg"
                if mime_type == "application/octet-stream":
                    mime_type = "audio/ogg"
            else:
                file_ext = "jpg"
                if mime_type == "application/octet-stream":
                    mime_type = "image/jpeg"
                    
            # 3. Generate a unique filename
            unique_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{file_ext}"
            
            # 4. Enforce exact inbound-media path
            gcs_path = f"inbound-media/{routing_data.get('company_id', 'unknown_company')}/{routing_data['agent_id']}/{unique_filename}"

            # 5. Stream to Cloud Storage
            media_url = await upload_media_to_gcs(media_bytes, gcs_path, mime_type)
            logger.info(f"[GCS Upload Success] Saved to: {media_url}")
            
        except Exception as e:
            logger.error(f"[WhatsApp] Media pipeline failed: {e}")
            return Response(status_code=200) # ALWAYS return 200 so Meta doesn't infinite loop

    # 5. Standardize into the Pydantic Model
    incoming_msg = IncomingMessage(
        platform=PlatformType.WHATSAPP,
        # CRITICAL FIX: Standardize sender_info to be a dict to match Pub/Sub keying logic
        sender_info={"id": parsed_data["sender_id"]},
        destination_agent_id=routing_data["agent_id"],
        text=parsed_data.get("text"),
        message_type=message_type,
        media_url=media_url
    )
    logger.info(f"[Normalized] {incoming_msg.platform.value} msg from {incoming_msg.sender_info['id']} to Agent {incoming_msg.destination_agent_id}")

    # 6. Publish to GCP Pub/Sub (with ordering keys from the previous phase!)
    try:
        await publish_incoming_message(incoming_msg)
    except Exception as e:
        logger.error(f"[WhatsApp] Failed to publish to Pub/Sub: {e}")
        # Return 500 only if queue is down, allowing Meta to safely retry
        raise HTTPException(status_code=500, detail="Internal queue error")

    # 7. Success! Return 200 OK
    return Response(status_code=200)