from fastapi import APIRouter, HTTPException, status
from app.models.reset_password import ResetPassword, ResetPasswordResponse
from app.config.database import Database
import bcrypt
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/reset-password", response_model=ResetPasswordResponse, status_code=status.HTTP_200_OK)
async def reset_password(reset_data: ResetPassword):
    """
    Reset user password

    Args:
        reset_data: Email and new password

    Returns:
        ResetPasswordResponse: Success message

    Raises:
        HTTPException: If user not found or internal error occurs
    """
    try:
        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        logger.info(f"Password reset request for email: {reset_data.email}")

        # Find user by email
        user = users_collection.find_one({"email": reset_data.email})

        if not user:
            logger.warning(f"User not found for email: {reset_data.email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Hash the new password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(reset_data.newPassword.encode('utf-8'), salt)

        # Update user password
        users_collection.update_one(
            {"email": reset_data.email},
            {"$set": {"password": hashed_password.decode('utf-8')}}
        )

        logger.info(f"Password reset successful for {reset_data.email}")

        return ResetPasswordResponse(message="Password reset successful")

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Reset password error: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {str(error)}"
        )
