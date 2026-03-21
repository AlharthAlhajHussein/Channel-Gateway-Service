import logging

logger = logging.getLogger("uvicorn.error")

def parse_telegram_payload(payload: dict) -> dict | None:
    """Extracts text or voice file IDs from Telegram JSON."""
    if "message" not in payload:
        return None
        
    msg = payload["message"]
    
    # CASE 1: Standard Text Message
    if "text" in msg:
        return {
            "sender_info": msg["chat"], 
            "text": msg["text"], 
            "media_id": None
        }
        
    # CASE 2: Voice Note
    elif "voice" in msg:
        return {
            "sender_info": msg["chat"], 
            "text": None, 
            "media_id": msg["voice"]["file_id"] # Telegram's internal ID for the audio file
        }
        
    # Ignore stickers, photos, videos, etc.
    logger.debug("[Telegram] Ignored unsupported media type.")
    return None

def     parse_whatsapp_payload(payload: dict) -> dict | None:
    """
    Extracts sender, text, and receiver_id from WhatsApp JSON.
    Gracefully ignores status updates (sent, delivered, read) and non-text media.
    """
    try:
        # WhatsApp payloads are deeply nested arrays
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        # This is the crucial edge case: WhatsApp sends status updates here too
        if "messages" not in value:
            logger.debug("[WhatsApp] Ignored non-message event (e.g., read receipt or delivery status).")
            return None
            
        msg = value["messages"][0]
        
        if msg.get("type") != "text":
            logger.debug(f"[WhatsApp] Ignored non-text message of type: {msg.get('type')}.")
            return None
            
        return {
            "sender_id": msg["from"],
            "text": msg["text"]["body"],
            "receiver_identifier": value.get("metadata", {}).get("phone_number_id")
        }
    except (IndexError, KeyError, TypeError) as e:
        logger.error(f"[WhatsApp] Failed to parse payload structure: {e}")
        return None