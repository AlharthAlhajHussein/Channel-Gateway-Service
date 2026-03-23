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
            "media_id": None,
            "message_type": "text"
        }
        
    # CASE 2: Voice Note
    elif "voice" in msg:
        return {
            "sender_info": msg["chat"], 
            "text": None, 
            "media_id": msg["voice"]["file_id"], # Telegram's internal ID for the audio file
            "message_type": "voice"
        }
        
    # CASE 3: Photo (Image)
    elif "photo" in msg:
        # Telegram sends multiple sizes, the last one is the highest resolution
        media_id = msg["photo"][-1]["file_id"]
        caption = msg.get("caption")
        
        return {
            "sender_info": msg["chat"],
            "text": caption,
            "media_id": media_id,
            "message_type": "text_and_image" if caption else "image"
        }
        
    # Ignore stickers, photos, videos, etc.
    logger.debug("[Telegram] Ignored unsupported media type.")
    return None

def parse_whatsapp_payload(payload: dict) -> dict | None:
    """
    Extracts sender, text, media_id, and receiver_id from WhatsApp JSON.
    Gracefully ignores status updates (sent, delivered, read) and non-audio media.
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
        msg_type = msg.get("type")
        receiver_id = value.get("metadata", {}).get("phone_number_id")
        
        # CASE 1: Standard Text Message
        if msg_type == "text":
            return {
                "sender_id": msg["from"],
                "text": msg["text"]["body"],
                "media_id": None,
                "receiver_identifier": receiver_id,
                "message_type": "text"
            }
            
        # CASE 2: Voice Note (WhatsApp uses 'audio' or 'voice' interchangeably)
        elif msg_type in ["audio", "voice"]:
            # Fallback safely depending on how Meta formats it
            media_obj = msg.get("audio") or msg.get("voice", {})
            return {
                "sender_id": msg["from"],
                "text": None,
                "media_id": media_obj.get("id"),
                "receiver_identifier": receiver_id,
                "message_type": "voice"
            }
            
        # CASE 3: Image
        elif msg_type == "image":
            caption = msg.get("image", {}).get("caption")
            return {
                "sender_id": msg["from"],
                "text": caption,
                "media_id": msg["image"].get("id"),
                "receiver_identifier": receiver_id,
                "message_type": "text_and_image" if caption else "image"
            }
            
        else:
            logger.debug(f"[WhatsApp] Ignored unsupported media type: {msg_type}")
            return None
            
    except (IndexError, KeyError, TypeError) as e:
        logger.error(f"[WhatsApp] Failed to parse payload structure: {e}")
        return None