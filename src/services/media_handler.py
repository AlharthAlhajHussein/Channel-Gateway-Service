import httpx
import logging
from google.cloud import storage

logger = logging.getLogger("uvicorn.error")

# Initialize the GCS Client globally so connection pools are reused
try:
    storage_client = storage.Client()
    # Update this to match your actual deployed GCP bucket name
    BUCKET_NAME = "agent-platform-bucket-1" 
    bucket = storage_client.bucket(BUCKET_NAME)
except Exception as e:
    logger.error(f"[GCS Config Error] Failed to initialize Google Cloud Storage client: {e}")
    storage_client = None
    bucket = None

async def get_telegram_media_bytes(file_id: str, bot_token: str) -> tuple[bytes, str]:
    """
    Fetches media file bytes and mime type from Telegram servers.
    Handles the two-step download process securely.
    """
    async with httpx.AsyncClient() as client:
        # 1. Ask Telegram for the file path based on the media_id
        file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        info_response = await client.get(file_info_url)
        info_response.raise_for_status()
        
        data = info_response.json()
        if not data.get("ok"):
            raise Exception(f"Telegram getFile failed: {data.get('description')}")
            
        file_path = data["result"]["file_path"]
        
        # 2. Download the actual file bytes
        # Setting a 30s timeout here to handle larger audio/image files safely
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        media_response = await client.get(download_url, timeout=30.0)
        media_response.raise_for_status()
        
        # Extract MIME type or guess from the extension provided by Telegram
        content_type = media_response.headers.get("Content-Type", "application/octet-stream")
        
        return media_response.content, content_type

async def upload_media_to_gcs(media_bytes: bytes, gcs_path: str, mime_type: str) -> str:
    """
    Uploads raw bytes to GCP Cloud Storage and returns the uniform gs:// URI.
    """
    if not bucket:
        raise Exception("GCS Bucket is not configured. Is GOOGLE_APPLICATION_CREDENTIALS set?")
        
    try:
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(media_bytes, content_type=mime_type)
        
        # Returning the gs:// URI. The Orchestrator will download it using its own GCP identity
        return f"gs://{BUCKET_NAME}/{gcs_path}"
        
    except Exception as e:
        logger.error(f"[GCS Upload Error] Failed to upload {gcs_path}: {e}")
        raise Exception(f"Failed pushing media to bucket: {e}")

async def get_whatsapp_media_bytes(media_id: str, access_token: str) -> tuple[bytes, str]:
    """
    Downloads the raw media bytes securely from Meta's Graph API.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient() as client:
        # 1. Ask Meta for the secure CDN URL for this specific media ID
        url_req = f"https://graph.facebook.com/v19.0/{media_id}"
        url_res = await client.get(url_req, headers=headers)
        url_res.raise_for_status()
        media_url = url_res.json()["url"]

        # 2. Download the actual media file from the CDN
        # Meta STRICTLY requires the Bearer token on this download request too
        media_response = await client.get(media_url, headers=headers, timeout=30.0)
        media_response.raise_for_status()

        # Extract MIME type from the response headers
        content_type = media_response.headers.get("Content-Type", "application/octet-stream")
        
        return media_response.content, content_type