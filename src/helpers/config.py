from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

import os

# Calculate the absolute path to the root directory where .env lives
# Assuming config.py is inside src/helpers/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(CURRENT_DIR)
ENV_PATH = os.path.join(SRC_DIR, ".env")

class Settings(BaseSettings):
    """Settings for the application."""
    
    app_name: str = "Gateway Channel Service"
    app_version: str = "1.0.0"
    
    # Redis settings
    redis_password: str | None = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # API URLs to other services (CORE Platform API) 
    core_platform_api_url: str | None = None
    core_platform_api_key: str | None = None    # Internal secret to authenticate with your Core API
    
    # Google Cloud settings
    gcp_project_id: str = "agents-platform-490417"
    
    # WhatsApp settings
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None
    
    # Telegram Setting
    telegram_webhook_secret: str | None = None
    # telegram_bot_token: Optional[str] = None
    # telegram_bot_identifier: Optional[str] = None
    
    class Config:
        env_file = ENV_PATH
        env_file_encoding = "utf-8"
        extra = "ignore"
            

settings = Settings()

def get_settings():
    return settings