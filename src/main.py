from fastapi import FastAPI 
from contextlib import asynccontextmanager
from services.redis_client import init_redis, close_redis
from services.core_platform_api_client import init_http_client, close_http_client
from routers.pubsub import pubsub_router
from routers.base import base_router
from routers.whatsapp import whatsapp_router
from routers.telegram import telegram_router
import logging

logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Initializing Redis connection pool...")
    await init_redis()
    
    logger.info("Initializing HTTPX client pool...")
    init_http_client()
    
    yield # Application handles requests here
    
    # --- Shutdown ---
    logger.info("Closing Redis connection pool...")
    await close_redis()
    
    logger.info("Closing HTTPX client pool...")
    await close_http_client()


# --- 2. Initialize App and Clients ---
app = FastAPI(
    title="Channel Gateway Service",
    escription="Handles incoming/outgoing messages for WhatsApp and Telegram and sends them to the Core Platform API",
    lifespan=lifespan, 
    version="0.1.0", 
    contact={"name": "Channel Gateway Team", "email": "alharth.alhaj.hussein@gmail.com"} 
)

app.include_router(base_router)
app.include_router(whatsapp_router)
app.include_router(telegram_router)
app.include_router(pubsub_router)
