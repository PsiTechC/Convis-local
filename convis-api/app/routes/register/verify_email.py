from fastapi import APIRouter, HTTPException, status
from app.models.verify import VerifyEmail, VerifyResponse
from app.config.database import Database
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/verify-email", response_model=VerifyResponse, status_code=status.HTTP_200_OK)
async def verify_email(verify_data: VerifyEmail):
    """
    Verify user email with OTP

    Args:
        verify_data: Email and OTP for verification

    Returns:
        VerifyResponse: Success message

    Raises:
        HTTPException: If user not found, invalid OTP, or internal error occurs
    """
    try:
        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        # Find user by email
        user = users_collection.find_one({"email": verify_data.email})

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found"
            )

        # Check if the provided OTP matches the one stored in the database
        if user.get('otp') != verify_data.otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )

        # Update the user status to verified and remove the OTP
        users_collection.update_one(
            {"email": verify_data.email},
            {
                "$set": {"verified": True},
                "$unset": {"otp": ""}
            }
        )

        logger.info(f"Email verified successfully for {verify_data.email}")

        return VerifyResponse(message="Email verified successfully!")

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error during OTP verification: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(error)}"
        )
