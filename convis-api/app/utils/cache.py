"""
Redis caching utility for API responses
Optimized for high concurrency (1000s of users)
"""
import json
import hashlib
import time
from typing import Optional, Any
import redis.asyncio as aioredis
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

# Global Redis connection pool for high concurrency
_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_client: Optional[aioredis.Redis] = None
_redis_unavailable = False  # Flag to prevent repeated connection attempts
_redis_last_attempt = 0  # Timestamp of last connection attempt
_REDIS_RETRY_INTERVAL = 60  # Retry Redis connection every 60 seconds


async def get_redis_client() -> aioredis.Redis:
    """Get or create Redis client with connection pooling"""
    global _redis_client, _redis_pool, _redis_unavailable, _redis_last_attempt

    # If Redis was marked unavailable, only retry after interval
    if _redis_unavailable:
        current_time = time.time()
        if current_time - _redis_last_attempt < _REDIS_RETRY_INTERVAL:
            return None  # Don't retry yet, silently return None
        # Reset and try again
        _redis_unavailable = False

    if _redis_client is None:
        try:
            # Skip if no Redis URL configured
            if not settings.redis_url:
                _redis_unavailable = True
                _redis_last_attempt = time.time()
                return None

            # In development mode, skip Redis Cloud if using production Redis URL
            if settings.environment == "development" and "redis-cloud.com" in settings.redis_url:
                logger.info("Development mode: Skipping Redis Cloud - running without cache")
                _redis_unavailable = True
                _redis_last_attempt = time.time()
                return None

            # Create connection pool for high concurrency
            _redis_pool = aioredis.ConnectionPool.from_url(
                settings.redis_url,
                max_connections=100,  # Support 1000s of concurrent requests
                decode_responses=False,  # Binary mode for better performance
                health_check_interval=30,
                socket_connect_timeout=5,  # 5 second timeout
                socket_timeout=5,
            )
            _redis_client = aioredis.Redis(connection_pool=_redis_pool)

            # Test connection
            await _redis_client.ping()
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            # Log only once, not on every request
            logger.warning(f"Redis cache unavailable - running without cache: {e}")
            _redis_client = None
            _redis_unavailable = True
            _redis_last_attempt = time.time()

    return _redis_client


async def close_redis():
    """Close Redis connection"""
    global _redis_client, _redis_pool
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate consistent cache key from arguments"""
    # Create hash of arguments for consistent key generation
    # Using MD5 for non-security purposes (cache key generation only)
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()  # nosec B324
    return f"convis:{prefix}:{key_hash}"


async def get_from_cache(key: str) -> Optional[Any]:
    """Get value from cache"""
    try:
        client = await get_redis_client()
        if client is None:
            return None  # Silently return None when Redis unavailable

        data = await client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        # Only log at debug level to avoid log spam
        logger.debug(f"Cache get error for key {key}: {e}")
        return None


async def set_to_cache(key: str, value: Any, expire: int = 300) -> bool:
    """Set value in cache with expiration (default 5 minutes)"""
    try:
        client = await get_redis_client()
        if client is None:
            return False  # Silently return False when Redis unavailable

        data = json.dumps(value, default=str)
        await client.setex(key, expire, data)
        return True
    except Exception as e:
        # Only log at debug level to avoid log spam
        logger.debug(f"Cache set error for key {key}: {e}")
        return False


async def delete_from_cache(key: str) -> bool:
    """Delete value from cache"""
    try:
        client = await get_redis_client()
        if client is None:
            return False

        await client.delete(key)
        return True
    except Exception as e:
        logger.debug(f"Cache delete error for key {key}: {e}")
        return False


async def invalidate_pattern(pattern: str) -> int:
    """Invalidate all keys matching pattern"""
    try:
        client = await get_redis_client()
        if client is None:
            return 0

        count = 0
        async for key in client.scan_iter(match=f"convis:{pattern}*"):
            await client.delete(key)
            count += 1

        return count
    except Exception as e:
        logger.debug(f"Cache invalidation error for pattern {pattern}: {e}")
        return 0


def cache_key_decorator(expire: int = 300, prefix: str = "api"):
    """Decorator for caching function results"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = generate_cache_key(f"{prefix}:{func.__name__}", *args, **kwargs)
            
            # Try to get from cache
            cached = await get_from_cache(cache_key)
            if cached is not None:
                return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            await set_to_cache(cache_key, result, expire=expire)
            
            return result
        
        return wrapper
    return decorator

