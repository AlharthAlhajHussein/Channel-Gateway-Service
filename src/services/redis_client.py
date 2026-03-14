import redis.asyncio as redis
from helpers import settings

# Global variable to hold the pool
redis_pool = None

async def init_redis():
    global redis_pool
    redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"
    redis_pool = redis.ConnectionPool.from_url(
        redis_url, 
        decode_responses=True, # Automatically decodes bytes to strings
        max_connections=100
    )
    return redis.Redis(connection_pool=redis_pool)

async def close_redis():
    if redis_pool:
        await redis_pool.disconnect()

# Dependency for FastAPI routes
async def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=redis_pool)