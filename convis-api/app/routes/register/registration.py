from fastapi import APIRouter, HTTPException, status
from app.models.user import UserRegistration, UserResponse
from app.config.database import Database
from app.utils.otp import generate_otp
from app.utils.email import send_otp_email_with_retry
import bcrypt
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegistration):
    """
    Register a new user

    Args:
        user_data: User registration data including email, password, companyName, and phoneNumber

    Returns:
        UserResponse: Success message and user ID

    Raises:
        HTTPException: If email already exists or internal error occurs
    """
    try:
        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        # Check if the user already exists
        existing_user = users_collection.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )

        # Hash the password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user_data.password.encode('utf-8'), salt)

        # Generate OTP
        otp = generate_otp()

        # Create new user document
        new_user = {
            "email": user_data.email,
            "password": hashed_password.decode('utf-8'),
            "role": "client",
            "firstLogin": True,
            "verified": False,
            "otp": otp,
            "companyName": user_data.companyName,
            "phoneNumber": user_data.phoneNumber
        }

        # Insert user into database
        result = users_collection.insert_one(new_user)

        # Try to send OTP email (don't fail if email fails)
        try:
            await send_otp_email_with_retry(user_data.email, otp)
            logger.info(f"OTP sent successfully to {user_data.email}")
        except Exception as email_error:
            logger.warning(f"Failed to send OTP email: {str(email_error)}")
            # Continue anyway - user is registered, just email failed

        # Return success response
        return UserResponse(
            message="User registered successfully. Please check your email for the OTP to verify your account.",
            userId=str(result.inserted_id)
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error during registration: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(error)}"
        )
