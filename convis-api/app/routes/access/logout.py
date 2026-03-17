from fastapi import APIRouter, Response, status
from app.models.logout import LogoutResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/logout", response_model=LogoutResponse, status_code=status.HTTP_200_OK)
async def logout(response: Response):
    """
    User logout - clears the authentication cookie

    Args:
        response: FastAPI Response object to clear cookies

    Returns:
        LogoutResponse: Logout success message
    """
    # Clear the token cookie
    response.set_cookie(
        key="token",
        value="",
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        max_age=0,  # Expire immediately
        samesite="lax",
        path="/"
    )

    logger.info("User logged out successfully")

    return LogoutResponse(message="Logged out")
