import httpx
import logging
from fastapi import HTTPException
from models.in_out_messages import OutgoingMessage

logger = logging.getLogger("uvicorn.error")

async def send_telegram_message(message: OutgoingMessage, bot_token: str):
    """Sends a message to the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": message['sender_info']['id'],
        "text": message.response_text
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
            logger.info(f"[Telegram Dispatch] Success for user {message.sender_info}")
            
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            error_msg = e.response.text
            
            if status in (400, 401, 403, 404):
                # PERMANENT ERROR: User blocked bot, chat not found, or token revoked.
                # We log it, but do NOT raise an exception. We want Pub/Sub to drop this.
                logger.warning(f"[Telegram Dispatch] Permanent failure (Code {status}): {error_msg}")
                return 
            elif status >= 500:
                # TRANSIENT ERROR: Telegram is down. Raise exception so Pub/Sub retries.
                logger.error(f"[Telegram Dispatch] Telegram server error (Code {status}): {error_msg}")
                raise HTTPException(status_code=500, detail="Telegram API down")
                
        except Exception as e:
            # Network timeout or DNS failure. Raise to retry.
            logger.error(f"[Telegram Dispatch] Network error: {e}")
            raise HTTPException(status_code=500, detail="Network failure")

async def send_whatsapp_message(message: OutgoingMessage, phone_number_id: str, access_token: str):
    """Sends a message to the Meta Graph API."""
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": message.sender_info,
        "type": "text",
        "text": {"body": message.response_text}
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            logger.info(f"[WhatsApp Dispatch] Success for user {message.sender_info}")
            
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            error_msg = e.response.text
            
            if status in (400, 401, 403, 404):
                # PERMANENT ERROR: Invalid number, outside 24h window, template restriction.
                logger.warning(f"[WhatsApp Dispatch] Permanent failure (Code {status}): {error_msg}")
                return
            elif status >= 500:
                # TRANSIENT ERROR: Meta is down. Raise to retry.
                logger.error(f"[WhatsApp Dispatch] Meta server error (Code {status}): {error_msg}")
                raise HTTPException(status_code=500, detail="Meta API down")
                
        except Exception as e:
            logger.error(f"[WhatsApp Dispatch] Network error: {e}")
            raise HTTPException(status_code=500, detail="Network failure")
        