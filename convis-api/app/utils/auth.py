"""
Authentication utilities for JWT token verification
"""
import logging
from typing import Optional
from fastapi import Header, HTTPException, status
import jwt
from bson import ObjectId
from app.config.settings import settings
from app.config.database import Database

logger = logging.getLogger(__name__)


async def get_current_user(authorization: str = Header(None)) -> dict:
    """
    Verify JWT token and return current user

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        dict: User document from database

    Raises:
        HTTPException: If token is missing, invalid, or user not found
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization token"
        )

    token = authorization.replace('Bearer ', '')

    try:
        # Decode JWT token
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = payload.get('clientId')

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        # Get user from database
        db = Database.get_db()
        users_collection = db['users']

        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID in token"
            )

        user = users_collection.find_one({"_id": user_obj_id})

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        # Add user_id as string for convenience
        user['user_id'] = str(user['_id'])

        return user

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.PyJWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def verify_user_ownership(user: dict, resource_user_id: str) -> None:
    """
    Verify that the authenticated user owns the resource

    Args:
        user: Current authenticated user
        resource_user_id: User ID that owns the resource

    Raises:
        HTTPException: If user does not own the resource
    """
    if user['user_id'] != resource_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource"
        )
