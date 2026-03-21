import httpx
import logging
from google.cloud import speech

logger = logging.getLogger("uvicorn.error")

# Initialize the GCP Speech Async Client
speech_client = speech.SpeechAsyncClient()

async def get_telegram_audio_bytes(file_id: str, bot_token: str) -> bytes:
    """Downloads the raw audio bytes from Telegram's servers."""
    async with httpx.AsyncClient() as client:
        # 1. Ask Telegram for the file's temporary download path
        path_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        path_res = await client.get(path_url)
        path_res.raise_for_status()
        file_path = path_res.json()["result"]["file_path"]

        # 2. Download the actual audio file
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        audio_res = await client.get(download_url)
        audio_res.raise_for_status()
        
        return audio_res.content

async def transcribe_audio_to_text(audio_bytes: bytes) -> str | None:
    """Sends audio to Google Cloud Speech-to-Text and returns the string."""
    audio = speech.RecognitionAudio(content=audio_bytes)
    
    # Telegram sends OGG_OPUS format. This configuration is required to read it without errors.
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
        sample_rate_hertz=48000,
        language_code="ar-SY", 
        alternative_language_codes=["en-US"], # Seamlessly handles bilingual voice notes
        enable_automatic_punctuation=True
    )

    try:
        # Call Google Cloud API
        response = await speech_client.recognize(config=config, audio=audio)
        
        if not response.results:
            return None
            
        # Stitch together the transcription blocks
        transcript = " ".join([result.alternatives[0].transcript for result in response.results])
        return transcript.strip()
        
    except Exception as e:
        logger.error(f"[STT Error] Google Cloud Speech failed: {e}")
        return None

async def get_whatsapp_audio_bytes(media_id: str, access_token: str) -> bytes:
    """Downloads the raw audio bytes securely from Meta's Graph API."""
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient() as client:
        # 1. Ask Meta for the secure CDN URL for this specific media ID
        url_req = f"https://graph.facebook.com/v19.0/{media_id}"
        url_res = await client.get(url_req, headers=headers)
        url_res.raise_for_status()
        media_url = url_res.json()["url"]

        # 2. Download the actual audio file from the CDN
        # Meta STRICTLY requires the Bearer token on this download request too
        audio_res = await client.get(media_url, headers=headers)
        audio_res.raise_for_status()
        
        return audio_res.content