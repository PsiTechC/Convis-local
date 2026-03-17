"""
Request ID middleware for request tracing
Critical for debugging high concurrency issues
"""
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to all requests for tracing"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip WebSocket requests — BaseHTTPMiddleware breaks WebSocket upgrades
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        # Generate or get request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in request state for access in routes
        request.state.request_id = request_id

        # Add to response headers
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id(request: Request) -> str:
    """Get request ID from request state"""
    return getattr(request.state, "request_id", "unknown")

