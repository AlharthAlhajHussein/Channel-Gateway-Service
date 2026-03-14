import hmac
import hashlib
import logging
from fastapi import APIRouter, Request, Query, Header, HTTPException, Response
from helpers.config import settings

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
    """
    Handles Meta's one-time Webhook Verification Handshake.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("[WhatsApp] Webhook verified successfully by Meta.")
        # Meta STRICTLY requires the challenge to be returned as plain text
        return Response(content=str(hub_challenge), media_type="text/plain")
    
    logger.error("[WhatsApp] Webhook verification failed. Invalid token or mode.")
    raise HTTPException(status_code=403, detail="Verification failed")

@whatsapp_router.post("")
async def receive_whatsapp_message(
    request: Request,
    x_hub_signature_256: str = Header(None)
):
    """
    Receives messages from Meta, verifying the cryptographic signature.
    """
    if not x_hub_signature_256:
        logger.error("[WhatsApp] Missing X-Hub-Signature-256 header.")
        raise HTTPException(status_code=401, detail="Missing signature header")

    # 1. Read the raw bytes of the request. 
    # Do NOT use request.json() here, as formatting changes break the hash.
    raw_body = await request.body()

    # 2. Calculate the expected HMAC SHA-256 signature using your App Secret
    expected_signature = hmac.new(
        key=settings.whatsapp_app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    # Meta prepends 'sha256=' to their signature header
    expected_signature_header = f"sha256={expected_signature}"

    # 3. Compare safely to prevent timing attacks
    if not hmac.compare_digest(expected_signature_header, x_hub_signature_256):
        logger.error("[WhatsApp] Cryptographic signature mismatch! Possible spoofing attempt.")
        raise HTTPException(status_code=403, detail="Invalid payload signature")

    # 4. If we reach here, the payload is 100% authentic from Meta.
    payload = await request.json()
    logger.info(f"[WhatsApp] Secure payload received.")
    
    # TODO: In Phase 3, we will pass this payload to the Normalizer and Rate Limiter.

    # 5. Always return 200 OK immediately so Meta doesn't retry the delivery
    return Response(status_code=200)