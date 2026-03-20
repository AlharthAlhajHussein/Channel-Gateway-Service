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
    """Receives secure messages from Meta, normalizes them, and publishes to Pub/Sub."""
    
    # 1. Security Check (Phase 2 logic)
    if not x_hub_signature_256:
        logger.error("[WhatsApp] Missing X-Hub-Signature-256 header.")
        raise HTTPException(status_code=401, detail="Missing signature header")

    raw_body = await request.body()
    expected_signature = hmac.new(
        key=settings.whatsapp_app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    expected_signature_header = f"sha256={expected_signature}"

    if not hmac.compare_digest(expected_signature_header, x_hub_signature_256):
        logger.error("[WhatsApp] Cryptographic signature mismatch! Possible spoofing attempt.")
        raise HTTPException(status_code=403, detail="Invalid payload signature")

    # Decode the already-read raw_body to JSON safely
    payload = json.loads(raw_body.decode("utf-8"))

    # 2. Normalize and Filter
    parsed_data = parse_whatsapp_payload(payload)
    if not parsed_data:
        # Edge Case Handled: It was a read receipt, delivery status, or unsupported media.
        # We MUST return 200 OK so Meta knows we received it and doesn't retry.
        return Response(status_code=200)

    # 3. Lookup Real Agent ID from Core Platform
    receiver_identifier = parsed_data["receiver_identifier"]
    try:
        routing_data = await lookup_agent_routing_data(
            platform=PlatformType.WHATSAPP, 
            receiver_identifier=receiver_identifier
        )
        real_agent_id = routing_data["agent_id"]
    except HTTPException:
        # Edge Case Handled: Meta sent a message to a phone number not registered in our DB.
        # Drop the message safely but return 200 OK to Meta.
        logger.warning(f"[WhatsApp] Message received for unregistered phone ID: {receiver_identifier}")
        return Response(status_code=200)

    # 4. Standardize into the Pydantic Model
    incoming_msg = IncomingMessage(
        platform=PlatformType.WHATSAPP,
        sender_info=parsed_data["sender_id"],
        destination_agent_id=real_agent_id,
        text=parsed_data["text"]
    )
    logger.info(f"[Normalized] {incoming_msg.platform.value} msg from {incoming_msg.sender_info} to Agent {incoming_msg.destination_agent_id}")

    # 5. Publish to GCP Pub/Sub
    try:
        await publish_incoming_message(incoming_msg)
    except Exception as e:
        logger.error(f"[WhatsApp] Failed to publish to Pub/Sub: {e}")
        # Edge Case Handled: If our internal queue is down, we return 500.
        # Meta will see the 500 and safely hold onto the message to retry delivering it later!
        raise HTTPException(status_code=500, detail="Internal queue error")

    # 6. Success! Return 200 OK
    return Response(status_code=200)
