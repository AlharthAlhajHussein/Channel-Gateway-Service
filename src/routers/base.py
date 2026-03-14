from fastapi import APIRouter
from fastapi.responses import JSONResponse
from helpers import settings

base_router = APIRouter(
    prefix="/api/v1",
    tags=["Base"]
)

@base_router.get("/")
async def health_check():
    """Simple health check endpoint."""
    return JSONResponse(status_code=200, 
                        content={
                        "APP Name": settings.app_name,
                        "APP Version": settings.app_version,  
                        "status": "OK",
                        "service": "channel-gateway"
                        }
            )