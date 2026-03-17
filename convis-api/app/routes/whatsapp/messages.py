"""
WhatsApp Messages Routes
Handles sending and managing WhatsApp messages
"""

from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from typing import List, Dict, Any
from datetime import datetime
from bson import ObjectId
import asyncio

from app.models.whatsapp import (
    WhatsAppMessageSend,
    WhatsAppMessageBulkSend,
    WhatsAppMessageResponse,
    WhatsAppStats,
    WhatsAppTemplateResponse
)
from app.config.database import Database
from app.utils.auth import get_current_user
from app.utils.encryption import encryption_service
from app.services.whatsapp_service import WhatsAppService

router = APIRouter()


async def get_whatsapp_service(credential_id: str, user_id: str) -> WhatsAppService:
    """Helper function to get Railway WhatsApp service instance with credentials"""
    db = Database.get_db()
    credentials_collection = db["whatsapp_credentials"]

    try:
        credential = credentials_collection.find_one({
            "_id": ObjectId(credential_id),
            "user_id": ObjectId(user_id)
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credential ID format"
        )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp credential not found"
        )

    if credential.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WhatsApp credential is not active. Please verify your connection."
        )

    # Decrypt credentials
    api_key = encryption_service.decrypt(credential["api_key"])
    bearer_token = encryption_service.decrypt(credential["bearer_token"])
    api_url = credential.get("api_url", "https://whatsapp-api-backend-production.up.railway.app")

    return WhatsAppService(
        api_key=api_key,
        bearer_token=bearer_token,
        base_url=api_url
    )


async def save_message_to_db(
    user_id: str,
    credential_id: str,
    to: str,
    message_type: str,
    status: str,
    message_id: str = None,
    content: Dict[str, Any] = None,
    error: str = None,
    campaign_id: str = None
) -> str:
    """Save sent message to database"""
    db = Database.get_db()
    messages_collection = db["whatsapp_messages"]

    doc = {
        "user_id": ObjectId(user_id),
        "credential_id": ObjectId(credential_id),
        "to": to,
        "message_type": message_type,
        "status": status,
        "message_id": message_id,
        "content": content or {},
        "error": error,
        "sent_at": datetime.utcnow(),
        "delivered_at": None,
        "read_at": None
    }

    if campaign_id:
        doc["campaign_id"] = ObjectId(campaign_id)

    result = messages_collection.insert_one(doc)
    return str(result.inserted_id)


@router.post("/send", response_model=WhatsAppMessageResponse)
async def send_whatsapp_message(
    payload: WhatsAppMessageSend,
    current_user: dict = Depends(get_current_user)
):
    """
    Send a WhatsApp message (text or template)
    """
    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    # Get WhatsApp service
    whatsapp_service = await get_whatsapp_service(payload.credential_id, user_id)

    try:
        # Send message based on type
        if payload.message_type == "text":
            result = await whatsapp_service.send_text_message(
                to=payload.to,
                message=payload.text
            )
        else:  # template
            result = await whatsapp_service.send_template_message(
                to=payload.to,
                template_name=payload.template_name,
                parameters=payload.template_params
            )

        # Save to database
        if result.get("success"):
            message_id = result.get("message_id")
            db_id = await save_message_to_db(
                user_id=user_id,
                credential_id=payload.credential_id,
                to=payload.to,
                message_type=payload.message_type,
                status="sent",
                message_id=message_id,
                content={
                    "text": payload.text if payload.message_type == "text" else None,
                    "template_name": payload.template_name if payload.message_type == "template" else None,
                    "template_params": payload.template_params if payload.message_type == "template" else None
                }
            )

            return WhatsAppMessageResponse(
                id=db_id,
                message_id=message_id,
                to=payload.to,
                status="sent",
                message_type=payload.message_type,
                sent_at=datetime.utcnow().isoformat()
            )
        else:
            error_msg = result.get("error", "Unknown error")

            # Save failed message
            db_id = await save_message_to_db(
                user_id=user_id,
                credential_id=payload.credential_id,
                to=payload.to,
                message_type=payload.message_type,
                status="failed",
                error=error_msg
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to send message: {error_msg}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sending message: {str(e)}"
        )


async def send_single_message_background(
    whatsapp_service: WhatsAppService,
    user_id: str,
    credential_id: str,
    to: str,
    message_type: str,
    text: str = None,
    template_name: str = None,
    template_params: List[str] = None,
    campaign_id: str = None
):
    """Background task to send a single message"""
    try:
        if message_type == "text":
            result = await whatsapp_service.send_text_message(to=to, message=text)
        else:
            result = await whatsapp_service.send_template_message(
                to=to,
                template_name=template_name,
                parameters=template_params
            )

        if result.get("success"):
            await save_message_to_db(
                user_id=user_id,
                credential_id=credential_id,
                to=to,
                message_type=message_type,
                status="sent",
                message_id=result.get("message_id"),
                campaign_id=campaign_id
            )
        else:
            await save_message_to_db(
                user_id=user_id,
                credential_id=credential_id,
                to=to,
                message_type=message_type,
                status="failed",
                error=result.get("error"),
                campaign_id=campaign_id
            )

    except Exception as e:
        await save_message_to_db(
            user_id=user_id,
            credential_id=credential_id,
            to=to,
            message_type=message_type,
            status="failed",
            error=str(e),
            campaign_id=campaign_id
        )


@router.post("/send-bulk")
async def send_bulk_whatsapp_messages(
    payload: WhatsAppMessageBulkSend,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Send WhatsApp messages to multiple recipients
    Messages are queued and sent in the background
    """
    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    # Get WhatsApp service
    whatsapp_service = await get_whatsapp_service(payload.credential_id, user_id)

    # Queue messages for background sending
    for recipient in payload.recipients:
        background_tasks.add_task(
            send_single_message_background,
            whatsapp_service=whatsapp_service,
            user_id=user_id,
            credential_id=payload.credential_id,
            to=recipient,
            message_type=payload.message_type,
            text=payload.text,
            template_name=payload.template_name,
            template_params=payload.template_params
        )

    return {
        "success": True,
        "message": f"Queued {len(payload.recipients)} messages for sending",
        "recipients_count": len(payload.recipients)
    }


@router.get("/messages", response_model=List[WhatsAppMessageResponse])
async def get_whatsapp_messages(
    credential_id: str = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """
    Get WhatsApp message history for the user
    """
    db = Database.get_db()
    messages_collection = db["whatsapp_messages"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    query = {"user_id": ObjectId(user_id)}

    if credential_id:
        try:
            query["credential_id"] = ObjectId(credential_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid credential ID format"
            )

    messages = messages_collection.find(query).sort("sent_at", -1).skip(offset).limit(limit)

    result = []
    for msg in messages:
        result.append(WhatsAppMessageResponse(
            id=str(msg["_id"]),
            message_id=msg.get("message_id"),
            to=msg["to"],
            status=msg["status"],
            message_type=msg["message_type"],
            sent_at=msg["sent_at"].isoformat() if isinstance(msg["sent_at"], datetime) else msg["sent_at"],
            error=msg.get("error")
        ))

    return result


@router.get("/stats", response_model=WhatsAppStats)
async def get_whatsapp_stats(
    current_user: dict = Depends(get_current_user)
):
    """
    Get WhatsApp statistics for the user
    """
    db = Database.get_db()
    messages_collection = db["whatsapp_messages"]
    credentials_collection = db["whatsapp_credentials"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    # Get message stats
    pipeline = [
        {"$match": {"user_id": ObjectId(user_id)}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]

    stats_result = list(messages_collection.aggregate(pipeline))
    stats_dict = {item["_id"]: item["count"] for item in stats_result}

    total_messages = sum(stats_dict.values())

    # Get credentials count
    credentials_count = credentials_collection.count_documents({"user_id": ObjectId(user_id)})
    active_credentials = credentials_collection.count_documents({
        "user_id": ObjectId(user_id),
        "status": "active"
    })

    return WhatsAppStats(
        total_messages=total_messages,
        sent=stats_dict.get("sent", 0),
        delivered=stats_dict.get("delivered", 0),
        read=stats_dict.get("read", 0),
        failed=stats_dict.get("failed", 0),
        credentials_count=credentials_count,
        active_credentials=active_credentials
    )


@router.get("/templates", response_model=List[WhatsAppTemplateResponse])
async def get_whatsapp_templates(
    credential_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get available WhatsApp message templates
    """
    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    # Get WhatsApp service
    whatsapp_service = await get_whatsapp_service(credential_id, user_id)

    try:
        result = await whatsapp_service.get_message_templates()

        if result.get("success"):
            templates = result.get("templates", [])
            return [
                WhatsAppTemplateResponse(
                    id=template.get("id", ""),
                    name=template.get("name", ""),
                    status=template.get("status", ""),
                    category=template.get("category", ""),
                    language=template.get("language", "en_US"),
                    components=template.get("components", [])
                )
                for template in templates
            ]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch templates: {result.get('error')}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching templates: {str(e)}"
        )


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whatsapp_message(
    message_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a message record from history
    Note: This only deletes from our database, not from WhatsApp
    """
    db = Database.get_db()
    messages_collection = db["whatsapp_messages"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    try:
        result = messages_collection.delete_one({
            "_id": ObjectId(message_id),
            "user_id": ObjectId(user_id)
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid message ID format"
        )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    return None
