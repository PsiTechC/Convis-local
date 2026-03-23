from fastapi import APIRouter, HTTPException, status, Depends, Header
from app.models.user import UserUpdate, UserUpdateResponse
from app.config.database import Database
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.put("/{user_id}", response_model=UserUpdateResponse, status_code=status.HTTP_200_OK)
async def update_user_profile(user_id: str, user_data: UserUpdate, authorization: str = Header(None)):
    """
    Update user profile information

    Args:
        user_id: User ID to update
        user_data: Updated user data (companyName, email, phoneNumber)
        authorization: Bearer token for authentication

    Returns:
        UserUpdateResponse: Success message and updated user data

    Raises:
        HTTPException: If user not found or internal error occurs
    """
    try:
        # Verify authorization token exists
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization token"
            )

        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        logger.info(f"Update profile request for user ID: {user_id}")

        # Validate user_id format
        try:
            object_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )

        # Find user by ID
        user = users_collection.find_one({"_id": object_id})

        if not user:
            logger.warning(f"User not found for ID: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Build update data (only include fields that are provided)
        update_data = {}
        if user_data.companyName is not None:
            update_data["companyName"] = user_data.companyName
        if user_data.email is not None:
            # Check if new email is already taken by another user
            existing_user = users_collection.find_one({
                "email": user_data.email,
                "_id": {"$ne": object_id}
            })
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use by another account"
                )
            update_data["email"] = user_data.email
        if user_data.phoneNumber is not None:
            update_data["phoneNumber"] = user_data.phoneNumber

        # If no data to update, return current user
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data provided to update"
            )

        # Update user in database
        result = users_collection.update_one(
            {"_id": object_id},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            logger.warning(f"No changes made for user {user_id}")

        # Get updated user data
        updated_user = users_collection.find_one({"_id": object_id})

        # Remove sensitive data from response
        if updated_user:
            updated_user.pop('password', None)
            updated_user.pop('otp', None)
            updated_user['_id'] = str(updated_user['_id'])

        logger.info(f"Profile updated successfully for user {user_id}")

        return UserUpdateResponse(
            message="Profile updated successfully",
            user=updated_user
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Update profile error: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {str(error)}"
        )
