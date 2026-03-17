from fastapi import APIRouter, HTTPException, status
from app.models.check_user import CheckUser, CheckUserResponse
from app.config.database import Database
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/check-user", response_model=CheckUserResponse, status_code=status.HTTP_200_OK)
async def check_user(user_data: CheckUser):
    """
    Check if a user exists by email

    Args:
        user_data: Email to check

    Returns:
        CheckUserResponse: Boolean indicating if user exists

    Raises:
        HTTPException: If internal error occurs
    """
    try:
        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        # Find user by email
        user = users_collection.find_one({"email": user_data.email})

        # Return whether user exists
        return CheckUserResponse(exists=bool(user))

    except Exception as error:
        import traceback
        logger.error(f"Error checking user existence: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(error)}"
        )
