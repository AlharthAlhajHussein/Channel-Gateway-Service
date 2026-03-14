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
    redis_password: Optional[str] = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # API URLs to other services (CORE Platform API) 
    core_platform_api_url: str = "http://localhost:8000"
    core_platform_api_key: str = "alharth562001"# Internal secret to authenticate with your Core API
    
    # Google Cloud settings
    gcp_project_id: str = Field(default="pdf-ocr-extractor-488523", validation_alias="GCP_PROJECT_ID")
    
    # WhatsApp settings
    whatsapp_verify_token: str = "your_custom_verify_token_here" 
    whatsapp_app_secret: str = "your_meta_app_secret_here"
    
    
    class Config:
        env_file = ENV_PATH
        env_file_encoding = "utf-8"
        extra = "ignore" 
            

settings = Settings()

def get_settings():
    return settings