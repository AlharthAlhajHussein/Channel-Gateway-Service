# Channel-Gateway-Service

Welcome to the highly-available "front door" and universal adapter of the Agents Platform. This service handles webhooks from platforms like WhatsApp and Telegram, processes media, and securely queues them for the AI Orchestrator.

For a deep dive into the architecture, edge cases, and tech stack, please read the [SERVICE_DOCUMENTATION.md](./SERVICE_DOCUMENTATION.md).

---

## Prerequisites
- **Python 3.13** (via Conda recommended)
- **Docker & Docker Compose** (for Redis)
- **UV** package manager
- **API Keys & Credentials**: GCP Service Account (for Cloud Storage/PubSub), Telegram Bot Token/Secret, Meta WhatsApp Token.

---

## Setup & Installation (Manual Development Mode)

### 1. Set up Environment Configuration
Create a `.env` file in the root directory by copying the example template. Configure your Redis, GCP, and Webhook credentials.
```bash
cp .env.example .env
```

### 2. Create and Activate Conda Environment
```bash
conda create -n channel-gateway-env python=3.13 uv -c conda-forge
conda activate channel-gateway-env
```

### Install dependancies

```bash
cd src
uv pip install -r requirements.txt
```

### Run redis using docker
create your own compose file for redis and run
```bash
docker compose up redis
```

## START APP

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```
