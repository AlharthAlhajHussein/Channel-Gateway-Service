from pydantic import BaseModel


class PubSubMessage(BaseModel):
    data: str  # Pub/Sub sends your payload as a Base64 encoded string
    messageId: str


class PubSubPushRequest(BaseModel):
    message: PubSubMessage
