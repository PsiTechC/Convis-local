"""
Rate Limiting Middleware for Convis
Prevents abuse and ensures fair usage across all users
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# Create limiter instance
# Uses client IP address as the key for rate limiting
limiter = Limiter(key_func=get_remote_address, default_limits=["1000/hour"])


def get_user_id_from_request(request: Request) -> str:
    """
    Extract user ID from JWT token for per-user rate limiting
    Falls back to IP address if no user is authenticated
    """
    try:
        # Try to get user from request state (set by auth middleware)
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        # Fall back to IP address
        return get_remote_address(request)
    except Exception:
        return get_remote_address(request)


# Custom rate limit exceeded handler
async def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom error response for rate limit exceeded
    """
    logger.warning(f"Rate limit exceeded for {get_remote_address(request)}: {exc.detail}")

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down and try again later.",
            "error": "rate_limit_exceeded",
            "retry_after": exc.detail
        }
    )


# Rate limit configurations for different endpoint types
RATE_LIMITS = {
    # WebSocket endpoints (voice calls) - most critical
    "websocket": "10/minute",  # Max 10 concurrent call initiations per minute

    # API key operations
    "api_key_create": "5/hour",  # Max 5 new API keys per hour

    # Assistant operations
    "assistant_create": "20/hour",  # Max 20 new assistants per hour
    "assistant_update": "60/hour",  # Max 60 updates per hour

    # Call operations
    "outbound_call": "30/minute",  # Max 30 outbound calls per minute
    "call_query": "100/minute",  # Max 100 call log queries per minute

    # File uploads
    "file_upload": "20/hour",  # Max 20 file uploads per hour

    # General API
    "general": "200/minute"  # General API rate limit
}


def get_rate_limit(endpoint_type: str) -> str:
    """Get rate limit string for a specific endpoint type"""
    return RATE_LIMITS.get(endpoint_type, RATE_LIMITS["general"])
