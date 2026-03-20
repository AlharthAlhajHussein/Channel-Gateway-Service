import logging

logger = logging.getLogger("uvicorn.error")

def parse_telegram_payload(payload: dict) -> dict | None:
    """
    Extracts sender and text from Telegram JSON.
    Gracefully ignores edits, channel posts, and non-text media (stickers, photos).
    """
    # Telegram standard messages live inside the "message" key
    if "message" not in payload:
        logger.debug("[Telegram] Ignored non-message update (e.g., edited message or callback query).")
        return None
        
    msg = payload["message"]
    
    # We only process text messages currently
    if "text" not in msg:
        logger.debug("[Telegram] Ignored non-text message (e.g., photo, sticker, voice).")
        return None
        
    return {
        "sender_info": msg["chat"],
        "text": msg["text"]
    }

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