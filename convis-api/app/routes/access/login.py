from fastapi import APIRouter, HTTPException, status, Response
from app.models.login import Login, LoginResponse
from app.config.database import Database
from app.config.settings import settings
from app.utils.threadpool import run_in_thread
import bcrypt
import jwt
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(login_data: Login, response: Response):
    """
    User login

    Args:
        login_data: Email and password
        response: FastAPI Response object to set cookies

    Returns:
        LoginResponse: Login success with redirect URL and user info

    Raises:
        HTTPException: If credentials invalid or user not verified
    """
    try:
        logger.info(f"Incoming login request: {login_data.email}")

        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        # Find user by email
        user = await run_in_thread(users_collection.find_one, {"email": login_data.email})
        logger.info(f"Database lookup result: {'Found' if user else 'Not found'}")

        if not user:
            logger.warning(f"User not found for email: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        # Validate password
        is_password_valid = bcrypt.checkpw(
            login_data.password.strip().encode('utf-8'),
            user['password'].encode('utf-8')
        )

        if not is_password_valid:
            logger.warning(f"Password does not match for user: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        logger.info(f"Login attempt successful for user: {login_data.email}")

        # Check if user is verified
        if not user.get('verified', False):
            logger.warning(f"User not verified: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email first."
            )

        # Generate JWT token
        token_payload = {
            "email": user['email'],
            "clientId": str(user['_id']),
            "exp": datetime.utcnow() + timedelta(days=1)
        }
        token = jwt.encode(token_payload, settings.jwt_secret, algorithm="HS256")
        logger.info(f"Token generated for user: {login_data.email}")

        # Set cookie in response
        # Use secure cookies in production (when using HTTPS)
        is_production = settings.environment == "production"
        response.set_cookie(
            key="token",
            value=token,
            httponly=True,
            secure=is_production,  # True in production with HTTPS
            max_age=60 * 60 * 24,  # 1 day
            samesite="lax",
            path="/"
        )

        # Return response
        return LoginResponse(
            redirectUrl=f"/client-dashboard/{str(user['_id'])}",
            clientId=str(user['_id']),
            isAdmin_683ed29d13d9992915a2a803_amdin_=(user.get('role') == 'admin'),
            token=token
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Login error: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
