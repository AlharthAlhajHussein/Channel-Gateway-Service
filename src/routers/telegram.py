import hmac
import logging
from fastapi import APIRouter, Request, Header, HTTPException, Response
from helpers.config import settings
from models.in_out_messages import IncomingMessage, PlatformType

# Import our new services
from services.normalizers import parse_telegram_payload
from services.core_platform_api_client import lookup_agent_routing_data
from services.pubsub_publisher import publish_incoming_message
from services.voice_processor import get_telegram_audio_bytes, transcribe_audio_to_text

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
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(x_telegram_bot_api_secret_token, settings.telegram_secret_token):
        raise HTTPException(status_code=403, detail="Invalid secret token")

    payload = await request.json()

    # 2. Normalize and Filter (Phase 3)
    parsed_data = parse_telegram_payload(payload)
    if not parsed_data:
        # It was an image, an edit, or unsupported. 
        # Return 200 OK immediately so Telegram drops it and doesn't retry.
        return Response(status_code=200)

    # 3. Lookup Real Agent ID from Core Platform (Phase 1 logic)
    # We use the 'identifier' from the URL (the Telegram Bot ID)
    try:
        routing_data = await lookup_agent_routing_data(
            platform=PlatformType.TELEGRAM, 
            receiver_identifier=parsed_data["sender_info"]["username"]
        )
    except HTTPException:
        # If the bot isn't registered in our DB, we drop the message safely
        logger.warning(f"Message received for unregistered bot: {identifier}")
        return Response(status_code=200)

    # 4. === NEW VOICE PROCESSING LOGIC ===
    if parsed_data["text"] is None and parsed_data["media_id"] is not None:
        logger.info(f"[Telegram] Voice note received. Extracting audio...")
        bot_token = routing_data.get("telegram_token")
        
        try:
            # Download and transcribe
            audio_bytes = await get_telegram_audio_bytes(parsed_data["media_id"], bot_token)
            transcribed_text = await transcribe_audio_to_text(audio_bytes)
            
            if not transcribed_text:
                logger.warning("[Telegram] Voice note was empty or unintelligible.")
                return Response(status_code=200) # Drop gracefully
                
            # Replace the 'None' text with our beautiful new transcription!
            parsed_data["text"] = transcribed_text
            logger.info(f"[STT Success] Transcribed: '{transcribed_text}'")
            
        except Exception as e:
            logger.error(f"[Telegram] Audio pipeline failed: {e}")
            return Response(status_code=200) # ALWAYS return 200 so Telegram doesn't infinite loop

    # 5. Standardize into the Pydantic Model
    incoming_msg = IncomingMessage(
        platform=PlatformType.TELEGRAM,
        sender_info=parsed_data["sender_info"],
        destination_agent_id=routing_data["agent_id"],
        text=parsed_data["text"]
    )
    logger.info(f"[Normalized] {incoming_msg.platform.value} msg from: {incoming_msg.sender_info} to Agent Id: {incoming_msg.destination_agent_id}")

    # 5. Publish to GCP Pub/Sub
    try:
        await publish_incoming_message(incoming_msg)
    except Exception:
        # If Pub/Sub is down, return a 500. 
        # Telegram will see the 500 and hold onto the message to retry it later!
        raise HTTPException(status_code=500, detail="Internal queue error")

    # 6. Success! Return 200 OK
    return Response(status_code=200)