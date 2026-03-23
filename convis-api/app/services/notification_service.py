"""
Notification Service
Handles creation, retrieval, and management of user notifications
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pymongo.database import Database as PyMongoDatabase
from bson import ObjectId

from app.models.notification import (
    Notification,
    NotificationType,
    NotificationPriority,
    NotificationPreferences
)


class NotificationService:
    """Service for managing notifications"""

    def __init__(self, db: PyMongoDatabase):
        self.db = db
        self.notifications_collection = db.notifications
        self.preferences_collection = db.notification_preferences

    async def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        related_id: Optional[str] = None,
        related_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        action_label: Optional[str] = None,
        action_url: Optional[str] = None,
        expires_in_days: Optional[int] = None
    ) -> Notification:
        """Create a new notification"""

        # Check user preferences first
        preferences = await self.get_user_preferences(user_id)
        if not self._should_create_notification(notification_type, preferences):
            return None

        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        notification = Notification(
            user_id=user_id,
            type=notification_type,
            priority=priority,
            title=title,
            message=message,
            related_id=related_id,
            related_type=related_type,
            metadata=metadata,
            action_label=action_label,
            action_url=action_url,
            expires_at=expires_at
        )

        # Insert into database
        result = self.notifications_collection.insert_one(
            notification.dict(by_alias=True, exclude={"id"})
        )
        notification.id = str(result.inserted_id)

        return notification

    def _should_create_notification(
        self,
        notification_type: NotificationType,
        preferences: NotificationPreferences
    ) -> bool:
        """Check if notification should be created based on user preferences"""

        # Map notification types to preference fields
        preference_map = {
            NotificationType.WORKFLOW_SUCCESS: preferences.workflow_success_enabled,
            NotificationType.WORKFLOW_FAILED: preferences.workflow_failed_enabled,
            NotificationType.WORKFLOW_ACTION_FAILED: preferences.workflow_action_failed_enabled,
            NotificationType.CALL_COMPLETED: preferences.call_completed_enabled,
            NotificationType.CALL_FAILED: preferences.call_failed_enabled,
            NotificationType.CALL_NEGATIVE_SENTIMENT: preferences.call_negative_sentiment_enabled,
            NotificationType.CALL_APPOINTMENT_DETECTED: preferences.call_appointment_detected_enabled,
            NotificationType.CALL_EMAIL_EXTRACTED: preferences.call_email_extracted_enabled,
            NotificationType.CAMPAIGN_STARTED: preferences.campaign_started_enabled,
            NotificationType.CAMPAIGN_COMPLETED: preferences.campaign_completed_enabled,
            NotificationType.CAMPAIGN_PAUSED: preferences.campaign_paused_enabled,
            NotificationType.CAMPAIGN_MILESTONE: preferences.campaign_milestone_enabled,
            NotificationType.INTEGRATION_DISCONNECTED: preferences.integration_disconnected_enabled,
            NotificationType.INTEGRATION_AUTH_EXPIRED: preferences.integration_auth_expired_enabled,
            NotificationType.INTEGRATION_RATE_LIMIT: preferences.integration_rate_limit_enabled,
            NotificationType.SYSTEM_FEATURE: preferences.system_feature_enabled,
            NotificationType.SYSTEM_MAINTENANCE: preferences.system_maintenance_enabled,
            NotificationType.SYSTEM_LIMIT_WARNING: preferences.system_limit_warning_enabled,
        }

        return preference_map.get(notification_type, True)

    async def get_user_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Notification]:
        """Get notifications for a user"""

        query = {"user_id": user_id}

        # Filter by read status
        if unread_only:
            query["is_read"] = False

        # Filter out expired notifications
        query["$or"] = [
            {"expires_at": None},
            {"expires_at": {"$gt": datetime.utcnow()}}
        ]

        cursor = self.notifications_collection.find(query)\
            .sort("created_at", -1)\
            .skip(offset)\
            .limit(limit)

        notifications = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            notifications.append(Notification(**doc))

        return notifications

    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications"""

        query = {
            "user_id": user_id,
            "is_read": False,
            "$or": [
                {"expires_at": None},
                {"expires_at": {"$gt": datetime.utcnow()}}
            ]
        }

        return self.notifications_collection.count_documents(query)

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read"""

        result = self.notifications_collection.update_one(
            {
                "_id": ObjectId(notification_id),
                "user_id": user_id
            },
            {
                "$set": {
                    "is_read": True,
                    "read_at": datetime.utcnow()
                }
            }
        )

        return result.modified_count > 0

    async def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user"""

        result = self.notifications_collection.update_many(
            {
                "user_id": user_id,
                "is_read": False
            },
            {
                "$set": {
                    "is_read": True,
                    "read_at": datetime.utcnow()
                }
            }
        )

        return result.modified_count

    async def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Delete a notification"""

        result = self.notifications_collection.delete_one(
            {
                "_id": ObjectId(notification_id),
                "user_id": user_id
            }
        )

        return result.deleted_count > 0

    async def delete_old_notifications(self, days: int = 30) -> int:
        """Delete old read notifications (cleanup task)"""

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = self.notifications_collection.delete_many(
            {
                "is_read": True,
                "read_at": {"$lt": cutoff_date}
            }
        )

        return result.deleted_count

    async def delete_expired_notifications(self) -> int:
        """Delete expired notifications"""

        result = self.notifications_collection.delete_many(
            {
                "expires_at": {"$lt": datetime.utcnow()}
            }
        )

        return result.deleted_count

    async def get_user_preferences(self, user_id: str) -> NotificationPreferences:
        """Get user notification preferences"""

        doc = self.preferences_collection.find_one({"user_id": user_id})

        if doc:
            doc["_id"] = str(doc["_id"])
            return NotificationPreferences(**doc)

        # Create default preferences if not found
        preferences = NotificationPreferences(user_id=user_id)
        self.preferences_collection.insert_one(
            preferences.dict(by_alias=True, exclude={"id"})
        )

        return preferences

    async def update_user_preferences(
        self,
        user_id: str,
        preferences_update: Dict[str, bool]
    ) -> NotificationPreferences:
        """Update user notification preferences"""

        # Ensure preferences exist
        await self.get_user_preferences(user_id)

        # Update preferences
        preferences_update["updated_at"] = datetime.utcnow()

        self.preferences_collection.update_one(
            {"user_id": user_id},
            {"$set": preferences_update}
        )

        return await self.get_user_preferences(user_id)

    # Helper methods for creating specific notification types

    async def notify_workflow_success(
        self,
        user_id: str,
        workflow_id: str,
        workflow_name: str,
        execution_id: str
    ) -> Optional[Notification]:
        """Create workflow success notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.WORKFLOW_SUCCESS,
            title="Workflow Completed Successfully",
            message=f"Workflow '{workflow_name}' completed successfully.",
            priority=NotificationPriority.LOW,
            related_id=workflow_id,
            related_type="workflow",
            metadata={"execution_id": execution_id},
            action_label="View Workflow",
            action_url=f"/workflows/{workflow_id}",
            expires_in_days=7
        )

    async def notify_workflow_failed(
        self,
        user_id: str,
        workflow_id: str,
        workflow_name: str,
        execution_id: str,
        error_message: str
    ) -> Optional[Notification]:
        """Create workflow failure notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.WORKFLOW_FAILED,
            title="Workflow Failed",
            message=f"Workflow '{workflow_name}' failed: {error_message[:100]}",
            priority=NotificationPriority.HIGH,
            related_id=workflow_id,
            related_type="workflow",
            metadata={"execution_id": execution_id, "error": error_message},
            action_label="View Workflow",
            action_url=f"/workflows/{workflow_id}",
            expires_in_days=14
        )

    async def notify_workflow_action_failed(
        self,
        user_id: str,
        workflow_id: str,
        workflow_name: str,
        action_name: str,
        error_message: str
    ) -> Optional[Notification]:
        """Create workflow action failure notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.WORKFLOW_ACTION_FAILED,
            title="Workflow Action Failed",
            message=f"Action '{action_name}' failed in workflow '{workflow_name}': {error_message[:80]}",
            priority=NotificationPriority.MEDIUM,
            related_id=workflow_id,
            related_type="workflow",
            metadata={"action_name": action_name, "error": error_message},
            action_label="Fix Workflow",
            action_url=f"/workflows/{workflow_id}",
            expires_in_days=14
        )

    async def notify_call_completed(
        self,
        user_id: str,
        call_id: str,
        contact_name: str,
        duration_seconds: int
    ) -> Optional[Notification]:
        """Create call completed notification"""

        minutes = duration_seconds // 60

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CALL_COMPLETED,
            title="Call Completed",
            message=f"Call with {contact_name} completed ({minutes} min)",
            priority=NotificationPriority.LOW,
            related_id=call_id,
            related_type="call",
            action_label="View Call",
            action_url=f"/calls/{call_id}",
            expires_in_days=3
        )

    async def notify_call_failed(
        self,
        user_id: str,
        call_id: str,
        contact_name: str,
        reason: str
    ) -> Optional[Notification]:
        """Create call failed notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CALL_FAILED,
            title="Call Failed",
            message=f"Call to {contact_name} failed: {reason}",
            priority=NotificationPriority.MEDIUM,
            related_id=call_id,
            related_type="call",
            action_label="View Details",
            action_url=f"/calls/{call_id}",
            expires_in_days=7
        )

    async def notify_negative_sentiment(
        self,
        user_id: str,
        call_id: str,
        contact_name: str,
        sentiment_score: float
    ) -> Optional[Notification]:
        """Create negative sentiment notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CALL_NEGATIVE_SENTIMENT,
            title="Negative Sentiment Detected",
            message=f"Call with {contact_name} had negative sentiment (score: {sentiment_score:.2f})",
            priority=NotificationPriority.HIGH,
            related_id=call_id,
            related_type="call",
            metadata={"sentiment_score": sentiment_score},
            action_label="Review Call",
            action_url=f"/calls/{call_id}",
            expires_in_days=14
        )

    async def notify_appointment_detected(
        self,
        user_id: str,
        call_id: str,
        contact_name: str,
        appointment_time: str
    ) -> Optional[Notification]:
        """Create appointment detected notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CALL_APPOINTMENT_DETECTED,
            title="Appointment Detected",
            message=f"Appointment scheduled with {contact_name} for {appointment_time}",
            priority=NotificationPriority.HIGH,
            related_id=call_id,
            related_type="call",
            metadata={"appointment_time": appointment_time},
            action_label="View Call",
            action_url=f"/calls/{call_id}",
            expires_in_days=30
        )

    async def notify_email_extracted(
        self,
        user_id: str,
        call_id: str,
        contact_name: str,
        email: str
    ) -> Optional[Notification]:
        """Create email extracted notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CALL_EMAIL_EXTRACTED,
            title="Email Address Captured",
            message=f"Email {email} extracted from call with {contact_name}",
            priority=NotificationPriority.MEDIUM,
            related_id=call_id,
            related_type="call",
            metadata={"email": email},
            action_label="View Call",
            action_url=f"/calls/{call_id}",
            expires_in_days=7
        )

    async def notify_campaign_started(
        self,
        user_id: str,
        campaign_id: str,
        campaign_name: str,
        contact_count: int
    ) -> Optional[Notification]:
        """Create campaign started notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CAMPAIGN_STARTED,
            title="Campaign Started",
            message=f"Campaign '{campaign_name}' started with {contact_count} contacts",
            priority=NotificationPriority.MEDIUM,
            related_id=campaign_id,
            related_type="campaign",
            action_label="View Campaign",
            action_url=f"/campaigns/{campaign_id}",
            expires_in_days=7
        )

    async def notify_campaign_completed(
        self,
        user_id: str,
        campaign_id: str,
        campaign_name: str,
        completed_count: int,
        total_count: int
    ) -> Optional[Notification]:
        """Create campaign completed notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CAMPAIGN_COMPLETED,
            title="Campaign Completed",
            message=f"Campaign '{campaign_name}' completed: {completed_count}/{total_count} calls",
            priority=NotificationPriority.MEDIUM,
            related_id=campaign_id,
            related_type="campaign",
            action_label="View Results",
            action_url=f"/campaigns/{campaign_id}",
            expires_in_days=30
        )

    async def notify_campaign_milestone(
        self,
        user_id: str,
        campaign_id: str,
        campaign_name: str,
        milestone: str,
        progress: int
    ) -> Optional[Notification]:
        """Create campaign milestone notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.CAMPAIGN_MILESTONE,
            title="Campaign Milestone Reached",
            message=f"Campaign '{campaign_name}' reached {milestone} ({progress}% complete)",
            priority=NotificationPriority.LOW,
            related_id=campaign_id,
            related_type="campaign",
            metadata={"milestone": milestone, "progress": progress},
            action_label="View Campaign",
            action_url=f"/campaigns/{campaign_id}",
            expires_in_days=7
        )

    async def notify_integration_disconnected(
        self,
        user_id: str,
        integration_id: str,
        integration_name: str,
        reason: str
    ) -> Optional[Notification]:
        """Create integration disconnected notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.INTEGRATION_DISCONNECTED,
            title="Integration Disconnected",
            message=f"{integration_name} integration was disconnected: {reason}",
            priority=NotificationPriority.URGENT,
            related_id=integration_id,
            related_type="integration",
            metadata={"reason": reason},
            action_label="Reconnect",
            action_url=f"/integrations/{integration_id}",
            expires_in_days=30
        )

    async def notify_integration_auth_expired(
        self,
        user_id: str,
        integration_id: str,
        integration_name: str
    ) -> Optional[Notification]:
        """Create integration auth expired notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.INTEGRATION_AUTH_EXPIRED,
            title="Integration Authorization Expired",
            message=f"{integration_name} needs to be re-authorized",
            priority=NotificationPriority.HIGH,
            related_id=integration_id,
            related_type="integration",
            action_label="Re-authorize",
            action_url=f"/integrations/{integration_id}",
            expires_in_days=30
        )

    async def notify_system_feature(
        self,
        user_id: str,
        feature_name: str,
        description: str,
        learn_more_url: Optional[str] = None
    ) -> Optional[Notification]:
        """Create new feature notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM_FEATURE,
            title=f"New Feature: {feature_name}",
            message=description,
            priority=NotificationPriority.LOW,
            action_label="Learn More" if learn_more_url else None,
            action_url=learn_more_url,
            expires_in_days=30
        )

    async def notify_system_maintenance(
        self,
        user_id: str,
        maintenance_time: str,
        duration: str,
        impact: str
    ) -> Optional[Notification]:
        """Create system maintenance notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM_MAINTENANCE,
            title="Scheduled Maintenance",
            message=f"System maintenance scheduled for {maintenance_time} ({duration}). {impact}",
            priority=NotificationPriority.HIGH,
            metadata={"maintenance_time": maintenance_time, "duration": duration, "impact": impact},
            expires_in_days=7
        )

    async def notify_limit_warning(
        self,
        user_id: str,
        limit_type: str,
        current_usage: int,
        limit: int,
        percentage: int
    ) -> Optional[Notification]:
        """Create usage limit warning notification"""

        return await self.create_notification(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM_LIMIT_WARNING,
            title=f"{limit_type} Limit Warning",
            message=f"You've used {current_usage}/{limit} {limit_type} ({percentage}% of your limit)",
            priority=NotificationPriority.MEDIUM if percentage < 90 else NotificationPriority.HIGH,
            metadata={"limit_type": limit_type, "current_usage": current_usage, "limit": limit, "percentage": percentage},
            action_label="Upgrade Plan",
            action_url="/settings/billing",
            expires_in_days=14
        )
