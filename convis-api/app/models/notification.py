"""
Notification Model
Stores user notifications for workflow events, calls, campaigns, and system alerts
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class NotificationType(str, Enum):
    """Types of notifications"""
    # Workflow notifications
    WORKFLOW_SUCCESS = "workflow_success"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_ACTION_FAILED = "workflow_action_failed"
    WORKFLOW_DELAYED = "workflow_delayed"

    # Call notifications
    CALL_COMPLETED = "call_completed"
    CALL_FAILED = "call_failed"
    CALL_NEGATIVE_SENTIMENT = "call_negative_sentiment"
    CALL_APPOINTMENT_DETECTED = "call_appointment_detected"
    CALL_EMAIL_EXTRACTED = "call_email_extracted"

    # Campaign notifications
    CAMPAIGN_STARTED = "campaign_started"
    CAMPAIGN_COMPLETED = "campaign_completed"
    CAMPAIGN_PAUSED = "campaign_paused"
    CAMPAIGN_MILESTONE = "campaign_milestone"

    # Integration notifications
    INTEGRATION_DISCONNECTED = "integration_disconnected"
    INTEGRATION_AUTH_EXPIRED = "integration_auth_expired"
    INTEGRATION_RATE_LIMIT = "integration_rate_limit"

    # System notifications
    SYSTEM_FEATURE = "system_feature"
    SYSTEM_MAINTENANCE = "system_maintenance"
    SYSTEM_LIMIT_WARNING = "system_limit_warning"


class NotificationPriority(str, Enum):
    """Priority levels for notifications"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Notification(BaseModel):
    """Notification model"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(..., description="User ID who receives this notification")
    type: NotificationType = Field(..., description="Type of notification")
    priority: NotificationPriority = Field(NotificationPriority.MEDIUM, description="Priority level")

    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")

    # Optional metadata
    related_id: Optional[str] = Field(None, description="Related entity ID (workflow, call, campaign)")
    related_type: Optional[str] = Field(None, description="Type of related entity")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    # Action button (optional)
    action_label: Optional[str] = Field(None, description="Label for action button")
    action_url: Optional[str] = Field(None, description="URL for action button")

    # Status
    is_read: bool = Field(False, description="Whether notification has been read")
    read_at: Optional[datetime] = Field(None, description="When notification was read")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="When notification should be auto-deleted")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NotificationPreferences(BaseModel):
    """User notification preferences"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(..., description="User ID")

    # Workflow notification settings
    workflow_success_enabled: bool = Field(True)
    workflow_failed_enabled: bool = Field(True)
    workflow_action_failed_enabled: bool = Field(True)

    # Call notification settings
    call_completed_enabled: bool = Field(False, description="Usually too many, disabled by default")
    call_failed_enabled: bool = Field(True)
    call_negative_sentiment_enabled: bool = Field(True)
    call_appointment_detected_enabled: bool = Field(True)
    call_email_extracted_enabled: bool = Field(True)

    # Campaign notification settings
    campaign_started_enabled: bool = Field(True)
    campaign_completed_enabled: bool = Field(True)
    campaign_paused_enabled: bool = Field(True)
    campaign_milestone_enabled: bool = Field(True)

    # Integration notification settings
    integration_disconnected_enabled: bool = Field(True)
    integration_auth_expired_enabled: bool = Field(True)
    integration_rate_limit_enabled: bool = Field(True)

    # System notification settings
    system_feature_enabled: bool = Field(True)
    system_maintenance_enabled: bool = Field(True)
    system_limit_warning_enabled: bool = Field(True)

    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
