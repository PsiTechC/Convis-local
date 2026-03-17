"""
Messaging Service Management - SMS at Scale
One webhook handles all phone numbers in the service,
eliminating per-number SMS URL configuration.
"""

from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime
import logging

from app.config.database import Database
from app.config.settings import settings
from app.services.twilio_service import TwilioService
from app.utils.twilio_helpers import decrypt_twilio_credentials

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request/Response Models ====================

class CreateMessagingServiceRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    friendly_name: str = Field(..., description="Name for the messaging service")


class MessagingServiceInfo(BaseModel):
    sid: str
    friendly_name: str
    inbound_request_url: Optional[str]
    created_at: str


class CreateMessagingServiceResponse(BaseModel):
    message: str
    service: MessagingServiceInfo
    note: str = "Add phone numbers to this service to enable unified SMS handling"


class AddNumberToServiceRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    service_sid: str = Field(..., description="Messaging Service SID")
    phone_number_id: str = Field(..., description="Phone number ID from database")


class AddNumberToServiceResponse(BaseModel):
    message: str
    phone_number: str
    service_sid: str


# ==================== Endpoints ====================

@router.post("/create-messaging-service", response_model=CreateMessagingServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_messaging_service(request: Request, service_request: CreateMessagingServiceRequest):
    """
    Create a Messaging Service for SMS at scale.

    Benefits:
    - One inbound SMS webhook URL for all numbers in the service
    - Easier to manage than per-number SMS URLs
    - Centralized SMS routing logic
    - Better for auto-scaling SMS operations

    Args:
        request: FastAPI request
        service_request: Service creation request

    Returns:
        CreateMessagingServiceResponse: Created service details
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        provider_connections_collection = db['provider_connections']
        messaging_services_collection = db['messaging_services']

        logger.info(f"Creating messaging service for user {service_request.user_id}")

        # Validate user
        try:
            user_obj_id = ObjectId(service_request.user_id)
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

        # Get Twilio connection
        twilio_connection = provider_connections_collection.find_one({
            "user_id": user_obj_id,
            "provider": "twilio"
        })

        if not twilio_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Twilio connection found. Please connect Twilio first."
            )

        account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
        if not account_sid or not auth_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Twilio credentials are missing or invalid. Please reconnect Twilio."
            )

        # Initialize Twilio service
        twilio_service = TwilioService(account_sid, auth_token)

        # Determine webhook URL
        if settings.api_base_url:
            base_url = settings.api_base_url
        else:
            base_url = f"{request.url.scheme}://{request.url.netloc}"

        inbound_request_url = f"{base_url}/api/twilio-webhooks/sms"
        status_callback = f"{base_url}/api/twilio-webhooks/sms-status"

        # Create messaging service
        service_sid = await twilio_service.create_messaging_service(
            friendly_name=service_request.friendly_name,
            inbound_request_url=inbound_request_url,
            status_callback=status_callback
        )

        # Store in database
        now = datetime.utcnow()
        service_doc = {
            "user_id": user_obj_id,
            "service_sid": service_sid,
            "friendly_name": service_request.friendly_name,
            "inbound_request_url": inbound_request_url,
            "status_callback": status_callback,
            "status": "active",
            "created_at": now,
            "updated_at": now
        }

        messaging_services_collection.insert_one(service_doc)

        logger.info(f"Successfully created messaging service {service_sid}")

        return CreateMessagingServiceResponse(
            message="Messaging service created successfully",
            service=MessagingServiceInfo(
                sid=service_sid,
                friendly_name=service_request.friendly_name,
                inbound_request_url=inbound_request_url,
                created_at=now.isoformat() + "Z"
            ),
            note="Add phone numbers to this service to enable unified SMS handling"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating messaging service: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating messaging service: {str(e)}"
        )


@router.post("/add-number-to-service", response_model=AddNumberToServiceResponse, status_code=status.HTTP_200_OK)
async def add_number_to_messaging_service(add_request: AddNumberToServiceRequest):
    """
    Add a phone number to a Messaging Service.

    Once added, the number will use the service's inbound SMS webhook
    instead of a per-number SMS URL.

    Args:
        add_request: Add number request

    Returns:
        AddNumberToServiceResponse: Success response
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        phone_numbers_collection = db['phone_numbers']
        provider_connections_collection = db['provider_connections']
        messaging_services_collection = db['messaging_services']

        logger.info(f"Adding number {add_request.phone_number_id} to service {add_request.service_sid}")

        # Validate user
        try:
            user_obj_id = ObjectId(add_request.user_id)
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

        # Validate phone number
        try:
            phone_obj_id = ObjectId(add_request.phone_number_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid phone_number_id format"
            )

        phone_doc = phone_numbers_collection.find_one({"_id": phone_obj_id})
        if not phone_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Phone number not found"
            )

        # Verify ownership
        if phone_doc["user_id"] != user_obj_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Phone number belongs to different user"
            )

        # Verify service exists
        service_doc = messaging_services_collection.find_one({
            "user_id": user_obj_id,
            "service_sid": add_request.service_sid
        })

        if not service_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messaging service not found"
            )

        # Get Twilio connection
        twilio_connection = provider_connections_collection.find_one({
            "user_id": user_obj_id,
            "provider": "twilio"
        })

        if not twilio_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Twilio connection found"
            )

        account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
        if not account_sid or not auth_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Twilio credentials are missing or invalid. Please reconnect Twilio."
            )

        # Initialize Twilio service
        twilio_service = TwilioService(account_sid, auth_token)

        # Add number to service
        await twilio_service.add_number_to_messaging_service(
            service_sid=add_request.service_sid,
            phone_number_sid=phone_doc["provider_sid"]
        )

        # Update database
        phone_numbers_collection.update_one(
            {"_id": phone_obj_id},
            {
                "$set": {
                    "messaging_service_sid": add_request.service_sid,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        logger.info(f"Successfully added {phone_doc['phone_number']} to service {add_request.service_sid}")

        return AddNumberToServiceResponse(
            message="Number added to messaging service successfully",
            phone_number=phone_doc["phone_number"],
            service_sid=add_request.service_sid
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding number to service: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding number to service: {str(e)}"
        )


@router.get("/messaging-services/{user_id}", status_code=status.HTTP_200_OK)
async def list_messaging_services(user_id: str):
    """
    List all messaging services for a user.

    Args:
        user_id: User ID

    Returns:
        dict: List of messaging services
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        messaging_services_collection = db['messaging_services']

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

        # Fetch services
        services = list(messaging_services_collection.find({"user_id": user_obj_id}))

        service_list = [
            {
                "sid": service["service_sid"],
                "friendly_name": service["friendly_name"],
                "inbound_request_url": service.get("inbound_request_url"),
                "status": service.get("status", "active"),
                "created_at": service["created_at"].isoformat() + "Z"
            }
            for service in services
        ]

        return {
            "message": f"Found {len(service_list)} messaging service(s)",
            "services": service_list,
            "total": len(service_list)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing messaging services: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing messaging services: {str(e)}"
        )
