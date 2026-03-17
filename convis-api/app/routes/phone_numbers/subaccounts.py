"""
Twilio Subaccount Management - Multi-tenant Isolation
Create separate subaccounts per customer for clean separation of:
- Phone numbers
- Usage logs
- Rate limits
- Billing
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime
import logging

from app.config.database import Database
from app.services.twilio_service import TwilioService
from app.utils.encryption import encryption_service
from app.utils.twilio_helpers import decrypt_twilio_credentials

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request/Response Models ====================

class CreateSubaccountRequest(BaseModel):
    user_id: str = Field(..., description="User ID (tenant ID)")
    friendly_name: str = Field(..., description="Name for the subaccount")


class SubaccountInfo(BaseModel):
    sid: str
    friendly_name: str
    status: str
    created_at: str


class CreateSubaccountResponse(BaseModel):
    message: str
    subaccount: SubaccountInfo
    note: str = "Store the subaccount SID and auth_token securely. They will be used for all operations for this tenant."


class ListSubaccountsResponse(BaseModel):
    message: str
    subaccounts: List[SubaccountInfo]
    total: int


class SubaccountStatsRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    subaccount_sid: str = Field(..., description="Subaccount SID")


class SubaccountStats(BaseModel):
    subaccount_sid: str
    friendly_name: str
    phone_numbers_count: int
    total_calls: Optional[int] = 0
    total_sms: Optional[int] = 0


# ==================== Endpoints ====================

@router.post("/create-subaccount", response_model=CreateSubaccountResponse, status_code=status.HTTP_201_CREATED)
async def create_subaccount(request: CreateSubaccountRequest):
    """
    Create a Twilio subaccount for multi-tenant isolation.

    Benefits:
    - Each customer gets their own isolated Twilio environment
    - Separate usage logs and analytics
    - Independent rate limits
    - Clean billing separation
    - No cross-tenant data leaks

    Args:
        request: Subaccount creation request

    Returns:
        CreateSubaccountResponse: Subaccount details with SID and auth token
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        provider_connections_collection = db['provider_connections']
        subaccounts_collection = db['subaccounts']

        logger.info(f"Creating subaccount for user {request.user_id}")

        # Validate user
        try:
            user_obj_id = ObjectId(request.user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        user = users_collection.find_one({"_id": user_obj_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get parent Twilio account credentials
        parent_connection = provider_connections_collection.find_one({
            "provider": "twilio",
            "is_parent_account": True
        })

        if not parent_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No parent Twilio account found. Configure parent account first."
            )

        parent_sid, parent_token = decrypt_twilio_credentials(parent_connection)
        if not parent_sid or not parent_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Parent Twilio credentials are missing or invalid."
            )

        # Initialize Twilio service with parent account
        twilio_service = TwilioService(parent_sid, parent_token)

        # Create subaccount
        subaccount_data = await twilio_service.create_subaccount(
            friendly_name=request.friendly_name
        )

        # Store subaccount in database
        now = datetime.utcnow()
        subaccount_doc = {
            "user_id": user_obj_id,
            "subaccount_sid": subaccount_data['sid'],
            "subaccount_auth_token": encryption_service.encrypt(subaccount_data['auth_token']),
            "friendly_name": request.friendly_name,
            "status": "active",
            "created_at": now,
            "updated_at": now
        }

        result = subaccounts_collection.insert_one(subaccount_doc)

        # Also create a provider connection for this subaccount
        subaccount_connection = {
            "user_id": user_obj_id,
            "provider": "twilio",
            "account_sid": subaccount_data['sid'],
            "auth_token": subaccount_data['auth_token'],
            "is_subaccount": True,
            "parent_account_sid": parent_connection["account_sid"],
            "status": "active",
            "created_at": now,
            "updated_at": now
        }

        provider_connections_collection.insert_one(subaccount_connection)

        logger.info(f"Successfully created subaccount {subaccount_data['sid']} for user {request.user_id}")

        return CreateSubaccountResponse(
            message="Subaccount created successfully",
            subaccount=SubaccountInfo(
                sid=subaccount_data['sid'],
                friendly_name=request.friendly_name,
                status="active",
                created_at=now.isoformat() + "Z"
            ),
            note="Store the subaccount SID securely. Use it for all operations for this tenant."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating subaccount: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating subaccount: {str(e)}"
        )


@router.get("/subaccounts/{user_id}", response_model=ListSubaccountsResponse, status_code=status.HTTP_200_OK)
async def list_user_subaccounts(user_id: str):
    """
    List all subaccounts for a user.

    Args:
        user_id: User ID

    Returns:
        ListSubaccountsResponse: List of subaccounts
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        subaccounts_collection = db['subaccounts']

        # Validate user
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        user = users_collection.find_one({"_id": user_obj_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Fetch subaccounts
        subaccounts = list(subaccounts_collection.find({"user_id": user_obj_id}))

        subaccount_list = [
            SubaccountInfo(
                sid=sub["subaccount_sid"],
                friendly_name=sub["friendly_name"],
                status=sub.get("status", "active"),
                created_at=sub["created_at"].isoformat() + "Z"
            )
            for sub in subaccounts
        ]

        return ListSubaccountsResponse(
            message=f"Found {len(subaccount_list)} subaccount(s)",
            subaccounts=subaccount_list,
            total=len(subaccount_list)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing subaccounts: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing subaccounts: {str(e)}"
        )


@router.post("/subaccount-stats", response_model=SubaccountStats, status_code=status.HTTP_200_OK)
async def get_subaccount_stats(request: SubaccountStatsRequest):
    """
    Get usage statistics for a subaccount.

    Args:
        request: Stats request

    Returns:
        SubaccountStats: Usage statistics
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        subaccounts_collection = db['subaccounts']
        phone_numbers_collection = db['phone_numbers']

        # Validate user
        try:
            user_obj_id = ObjectId(request.user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        user = users_collection.find_one({"_id": user_obj_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Fetch subaccount
        subaccount = subaccounts_collection.find_one({
            "user_id": user_obj_id,
            "subaccount_sid": request.subaccount_sid
        })

        if not subaccount:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subaccount not found"
            )

        # Count phone numbers in this subaccount
        phone_count = phone_numbers_collection.count_documents({
            "user_id": user_obj_id,
            "subaccount_sid": request.subaccount_sid
        })

        # TODO: Add call and SMS counts from logs
        # For now, return basic stats

        return SubaccountStats(
            subaccount_sid=request.subaccount_sid,
            friendly_name=subaccount["friendly_name"],
            phone_numbers_count=phone_count,
            total_calls=0,  # TODO: Implement from call_logs
            total_sms=0     # TODO: Implement from sms_logs
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subaccount stats: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting subaccount stats: {str(e)}"
        )
