"""
Notification API Routes
Provides endpoints for managing user notifications
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

from app.config.database import Database
from app.middleware.auth import get_current_user
from app.services.notification_service import NotificationService
from app.models.notification import Notification, NotificationPreferences


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def get_database():
    """Dependency to get database instance"""
    return Database.get_db()


# Request/Response Models

class NotificationResponse(BaseModel):
    """Notification response model"""
    id: str
    type: str
    priority: str
    title: str
    message: str
    related_id: Optional[str] = None
    related_type: Optional[str] = None
    action_label: Optional[str] = None
    action_url: Optional[str] = None
    is_read: bool
    read_at: Optional[str] = None
    created_at: str


class NotificationListResponse(BaseModel):
    """List of notifications response"""
    notifications: List[NotificationResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Unread count response"""
    unread_count: int


class MarkReadResponse(BaseModel):
    """Mark as read response"""
    success: bool
    message: str


class PreferencesUpdateRequest(BaseModel):
    """Notification preferences update request"""
    workflow_success_enabled: Optional[bool] = None
    workflow_failed_enabled: Optional[bool] = None
    workflow_action_failed_enabled: Optional[bool] = None
    call_completed_enabled: Optional[bool] = None
    call_failed_enabled: Optional[bool] = None
    call_negative_sentiment_enabled: Optional[bool] = None
    call_appointment_detected_enabled: Optional[bool] = None
    call_email_extracted_enabled: Optional[bool] = None
    campaign_started_enabled: Optional[bool] = None
    campaign_completed_enabled: Optional[bool] = None
    campaign_paused_enabled: Optional[bool] = None
    campaign_milestone_enabled: Optional[bool] = None
    integration_disconnected_enabled: Optional[bool] = None
    integration_auth_expired_enabled: Optional[bool] = None
    integration_rate_limit_enabled: Optional[bool] = None
    system_feature_enabled: Optional[bool] = None
    system_maintenance_enabled: Optional[bool] = None
    system_limit_warning_enabled: Optional[bool] = None


# Helper function to convert Notification to response model
def notification_to_response(notification: Notification) -> NotificationResponse:
    """Convert Notification model to response model"""
    return NotificationResponse(
        id=notification.id,
        type=notification.type.value,
        priority=notification.priority.value,
        title=notification.title,
        message=notification.message,
        related_id=notification.related_id,
        related_type=notification.related_type,
        action_label=notification.action_label,
        action_url=notification.action_url,
        is_read=notification.is_read,
        read_at=notification.read_at.isoformat() if notification.read_at else None,
        created_at=notification.created_at.isoformat()
    )


# Routes

@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    unread_only: bool = Query(False, description="Get only unread notifications"),
    limit: int = Query(50, ge=1, le=100, description="Number of notifications to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get notifications for the current user

    - **unread_only**: Filter to only unread notifications
    - **limit**: Maximum number of notifications to return (1-100)
    - **offset**: Offset for pagination
    """
    user_id = str(current_user["_id"])
    service = NotificationService(db)

    # Get notifications
    notifications = await service.get_user_notifications(
        user_id=user_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset
    )

    # Get unread count
    unread_count = await service.get_unread_count(user_id)

    # Get total count (for pagination)
    total_query = {"user_id": user_id}
    if unread_only:
        total_query["is_read"] = False
    total = await db.notifications.count_documents(total_query)

    return NotificationListResponse(
        notifications=[notification_to_response(n) for n in notifications],
        total=total,
        unread_count=unread_count
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get count of unread notifications for the current user
    """
    user_id = str(current_user["_id"])
    service = NotificationService(db)

    unread_count = await service.get_unread_count(user_id)

    return UnreadCountResponse(unread_count=unread_count)


@router.put("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Mark a specific notification as read
    """
    user_id = str(current_user["_id"])
    service = NotificationService(db)

    success = await service.mark_as_read(notification_id, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return MarkReadResponse(
        success=True,
        message="Notification marked as read"
    )


@router.put("/mark-all-read", response_model=MarkReadResponse)
async def mark_all_notifications_as_read(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Mark all notifications as read for the current user
    """
    user_id = str(current_user["_id"])
    service = NotificationService(db)

    count = await service.mark_all_as_read(user_id)

    return MarkReadResponse(
        success=True,
        message=f"Marked {count} notifications as read"
    )


@router.delete("/{notification_id}", response_model=MarkReadResponse)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Delete a specific notification
    """
    user_id = str(current_user["_id"])
    service = NotificationService(db)

    success = await service.delete_notification(notification_id, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return MarkReadResponse(
        success=True,
        message="Notification deleted"
    )


@router.get("/preferences", response_model=NotificationPreferences)
async def get_notification_preferences(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get notification preferences for the current user
    """
    user_id = str(current_user["_id"])
    service = NotificationService(db)

    preferences = await service.get_user_preferences(user_id)

    return preferences


@router.put("/preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    preferences_update: PreferencesUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Update notification preferences for the current user

    Only provide the fields you want to update. All fields are optional.
    """
    user_id = str(current_user["_id"])
    service = NotificationService(db)

    # Filter out None values
    update_dict = {k: v for k, v in preferences_update.dict().items() if v is not None}

    if not update_dict:
        raise HTTPException(status_code=400, detail="No preferences to update")

    preferences = await service.update_user_preferences(user_id, update_dict)

    return preferences
