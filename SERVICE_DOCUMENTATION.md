# Channel-Gateway-Service: Architecture & Developer Guide

## 1. Overview & Purpose
The **Channel-Gateway-Service** is the highly-available "front door" and universal adapter of the Agents Platform. Its primary job is to receive chaotic, channel-specific incoming webhooks (from WhatsApp, Telegram, etc.), securely validate them, and normalize them into a single, clean internal format.

It is responsible for intercepting media files (like voice notes and images), saving them to your own cloud storage, figuring out which AI agent should respond, and safely queuing the standardized message into an event bus for the AI Orchestrator to process asynchronously. 

---

## 2. Core Technologies & Stack
* **Web Framework:** **FastAPI** (Python 3.13) - Provides ultra-fast, async HTTP webhook endpoints.
* **HTTP Client:** **HTTPX** - Used for async downloads of media files and fetching routing data from the Core Platform.
* **Caching:** **Redis** - Crucial for the Cache-Aside pattern. It memorizes which phone numbers/bot IDs route to which AI Agents, drastically reducing database load.
* **Cloud Storage:** **Google Cloud Storage (GCS)** - Used to safely persist user-uploaded media (voice notes, images) so the heavy byte data doesn't clog up the message queues.
* **Message Broker:** **GCP Pub/Sub** - The highly reliable queue where standardized messages are published.
* **Containerization:** **Docker** - Deployed as a lightweight, stateless Python slim container, easily scalable on Google Cloud Run to handle massive webhook traffic spikes.

---

## 3. Core Workflows (How it Works)

### A. Webhook Ingestion & Security
* **Trigger:** An external platform (e.g., Telegram) hits our webhook endpoint (`/webhooks/telegram/{identifier}`).
* **Security Check:** The endpoint immediately validates channel-specific security headers (like `x-telegram-bot-api-secret-token`) to ensure the request is genuinely from the provider and not a malicious actor.

### B. Normalization Phase (`services/normalizers.py`)
* **The Problem:** WhatsApp sends deeply nested JSON arrays. Telegram sends flat objects. 
* **The Solution:** The `parse_payload` functions strip away the junk, ignore irrelevant events (like WhatsApp read receipts), and return a clean dictionary containing the sender ID, text, and media IDs.

### C. Agent Routing (Cache-Aside)
* The system extracts the receiver's public identifier (e.g., the WhatsApp Phone Number or Telegram Bot Username).
* It asks **Redis**: *"Which AI Agent owns this number?"*
* If Redis misses, it asks the Core Platform API, and then caches the result for 1 hour. This ensures 1-millisecond routing lookups under heavy load.

### D. Multimodal Media Pipeline (`services/media_handler.py`)
* If the normalizer detects an image or voice note, the gateway halts.
* It securely downloads the raw bytes directly from Meta's or Telegram's servers using the agent's specific API tokens.
* It uploads those bytes to a centralized **GCP Bucket** (`inbound-media/company_id/agent_id/...`) and gets a `gs://` URI.

### E. Dispatch to Pub/Sub
* The gateway packages the text, sender info, agent ID, and the GCS media URL into a strictly typed `IncomingMessage` Pydantic model.
* It publishes this model to the GCP `incoming_messages` topic. 
* **Crucial Step:** It uses an `ordering_key` (e.g., `whatsapp:sender123:agent456`) to guarantee that if a user sends 3 messages rapidly, the AI Orchestrator receives them in the exact order they were sent.

---

## 4. Edge Cases & Resilience (Already Handled)
* **Infinite Webhook Retry Prevention:** If a user sends an unsupported file (like a sticker) or messages an unregistered bot, the gateway immediately returns `200 OK`. If we returned an error, Meta/Telegram would infinitely retry sending the unprocessable message.
* **Zero Message Loss on Queue Failure:** If GCP Pub/Sub goes down, the gateway explicitly returns a `500 Internal Server Error`. Telegram/WhatsApp will see the 500 and *hold* the message on their servers, retrying it later when our queue recovers.
* **Ghost Event Filtering:** Meta webhooks trigger for *everything* (sent, delivered, read, deleted). The normalizers safely catch and drop these non-message events so the AI doesn't try to reply to a "Read Receipt".
* **Unique File Collisions:** Downloaded media files are saved with a highly specific timestamp and UUID hex (`20240101_abcd1234.ogg`) to guarantee files from different users never overwrite each other in the GCP bucket.

---

## 5. Future Development & Advanced Features Roadmap

### A. Streaming Uploads for Large Media
* **Current State:** A voice note is fully downloaded into the API's RAM (`media_response.content`), then uploaded to GCS.
* **Future Feature:** Implement a streaming pass-through. Pipe the incoming `httpx` stream directly into the Google Cloud Storage upload stream. This will drastically reduce memory consumption on the server, especially if you start supporting video files in the future.

### B. Rate Limiting & Abuse Prevention
* **Current State:** The gateway accepts messages as fast as Telegram/WhatsApp sends them.
* **Future Feature:** Implement a Redis-based rate limiter per `sender_id`. If a user spams 50 messages in 10 seconds, the gateway should drop the excess to prevent malicious users from intentionally draining your Gemini LLM API credits.
