from fastapi import APIRouter, HTTPException, status
from app.models.verify_otp import VerifyOTP, VerifyOTPResponse
from app.config.database import Database
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/verify-otp", response_model=VerifyOTPResponse, status_code=status.HTTP_200_OK)
async def verify_otp(otp_data: VerifyOTP):
    """
    Verify OTP for password reset

    Args:
        otp_data: Email and OTP to verify

    Returns:
        VerifyOTPResponse: Success message

    Raises:
        HTTPException: If OTP is invalid or internal error occurs
    """
    try:
        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        logger.info(f"OTP verification request for email: {otp_data.email}")

        # Find user by email
        user = users_collection.find_one({"email": otp_data.email})

        # Check if user exists and OTP matches
        if not user or user.get('otp') != otp_data.otp:
            logger.warning(f"Invalid OTP for email: {otp_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )

        logger.info(f"OTP verified successfully for {otp_data.email}")

        return VerifyOTPResponse(message="OTP verified successfully")

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"OTP verification error: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OTP verification failed: {str(error)}"
        )
