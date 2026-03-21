import hmac
import hashlib
import logging
import json
from fastapi import APIRouter, Request, Query, Header, HTTPException, Response
from helpers.config import settings
from models.in_out_messages import IncomingMessage, PlatformType

# Import our internal services
from services.normalizers import parse_whatsapp_payload
from services.core_platform_api_client import lookup_agent_routing_data
from services.pubsub_publisher import publish_incoming_message # Assuming this is your publisher filename
from services.voice_processor import get_whatsapp_audio_bytes, transcribe_audio_to_text

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
        real_agent_id = routing_data["agent_id"]
    except HTTPException:
        logger.warning(f"[WhatsApp] Message received for unregistered phone ID: {receiver_identifier}")
        return Response(status_code=200)

    # 4. === NEW VOICE PROCESSING LOGIC ===
    if parsed_data["text"] is None and parsed_data["media_id"] is not None:
        logger.info(f"[WhatsApp] Voice note received. Extracting audio...")
        access_token = routing_data.get("whatsapp_token")
        
        if not access_token:
            logger.error(f"[WhatsApp] Missing access token for agent {real_agent_id}")
            return Response(status_code=200)

        try:
            # Download via Meta Graph and transcribe via GCP Speech
            audio_bytes = await get_whatsapp_audio_bytes(parsed_data["media_id"], access_token)
            transcribed_text = await transcribe_audio_to_text(audio_bytes)
            
            if not transcribed_text:
                logger.warning("[WhatsApp] Voice note was empty or unintelligible.")
                return Response(status_code=200) # Drop gracefully
                
            # Replace the 'None' text with our transcription
            parsed_data["text"] = transcribed_text
            logger.info(f"[STT Success] Transcribed: '{transcribed_text}'")
            
        except Exception as e:
            logger.error(f"[WhatsApp] Audio pipeline failed: {e}")
            return Response(status_code=200) # ALWAYS return 200 so Meta doesn't infinite loop

    # 5. Standardize into the Pydantic Model
    incoming_msg = IncomingMessage(
        platform=PlatformType.WHATSAPP,
        sender_id=parsed_data["sender_id"],
        destination_agent_id=real_agent_id,
        text=parsed_data["text"]
    )
    logger.info(f"[Normalized] {incoming_msg.platform.value} msg from {incoming_msg.sender_id} to Agent {incoming_msg.destination_agent_id}")

    # 6. Publish to GCP Pub/Sub (with ordering keys from the previous phase!)
    try:
        await publish_incoming_message(incoming_msg)
    except Exception as e:
        logger.error(f"[WhatsApp] Failed to publish to Pub/Sub: {e}")
        # Return 500 only if queue is down, allowing Meta to safely retry
        raise HTTPException(status_code=500, detail="Internal queue error")

    # 7. Success! Return 200 OK
    return Response(status_code=200)