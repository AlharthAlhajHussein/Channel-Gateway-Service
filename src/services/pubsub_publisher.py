import asyncio
import logging
from google.cloud import pubsub_v1
from helpers import settings
from models.in_out_messages import IncomingMessage

logger = logging.getLogger("uvicorn.error")

# Initialize the GCP Publisher Client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(settings.gcp_project_id, "incoming_messages")

async def publish_incoming_message(message: IncomingMessage):
    """Publishes the standardized message to the incoming Pub/Sub queue."""
    try:
        # Convert Pydantic model to JSON string, then encode to bytes
        data_bytes = message.model_dump_json().encode("utf-8")
        
        # Publish asynchronously
        future = publisher.publish(topic_path, data=data_bytes)
        message_id = await asyncio.wrap_future(future)
        
        logger.info(f"[Pub/Sub] Successfully published IncomingMessage. Msg ID: {message_id}")
        return message_id
    except Exception as e:
        logger.error(f"[Pub/Sub] Failed to publish message: {e}")
        # We don't want to crash the webhook response if Pub/Sub blips
        raise