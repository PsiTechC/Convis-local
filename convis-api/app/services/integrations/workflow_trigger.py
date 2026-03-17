"""
Workflow Trigger Service
Triggers workflows from various events (call completed, campaign finished, etc.)
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from app.models.workflow import TriggerEvent
from app.services.integrations.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


class WorkflowTrigger:
    """Service to trigger workflows from application events"""

    @staticmethod
    async def trigger_call_completed(
        call_data: Dict[str, Any],
        user_id: str,
        assistant_id: Optional[str] = None,
        assigned_workflow_ids: Optional[list] = None
    ) -> None:
        """
        Trigger workflows when a call is completed

        Args:
            call_data: Call information including transcription, duration, etc.
            user_id: User ID who owns the call
            assistant_id: Optional assistant ID to filter workflows
            assigned_workflow_ids: Optional list of specific workflow IDs to trigger
        """
        try:
            logger.info(f"[WORKFLOW_TRIGGER] Triggering call_completed workflows for user {user_id}, assistant={assistant_id}")

            # Get analysis data for issue tracking
            analysis = call_data.get("analysis", {})

            # Prepare trigger data with all necessary fields
            trigger_data = {
                "call_id": call_data.get("_id") or call_data.get("id"),
                "call": {
                    "id": call_data.get("_id") or call_data.get("id"),
                    "status": call_data.get("status"),
                    "duration": call_data.get("duration", 0),
                    "direction": call_data.get("direction"),
                    "from_number": call_data.get("from_number"),
                    "to_number": call_data.get("to_number"),
                    "transcription": call_data.get("transcription") or call_data.get("transcript", ""),
                    "summary": call_data.get("summary", ""),
                    "sentiment": call_data.get("sentiment"),
                    "sentiment_score": call_data.get("sentiment_score", 0.0),
                    "created_at": call_data.get("created_at"),
                    "ended_at": call_data.get("ended_at"),
                    "recording_url": call_data.get("recording_url"),
                },
                # Customer information
                "customer": {
                    "name": call_data.get("customer_name", ""),
                    "phone": call_data.get("to_number") or call_data.get("from_number"),
                    "email": call_data.get("customer_email", ""),
                },
                "customer_name": call_data.get("customer_name", ""),
                "customer_email": call_data.get("customer_email", ""),
                "customer_phone": call_data.get("to_number") or call_data.get("from_number"),
                "email_mentioned": call_data.get("email_mentioned", False),
                # Issue tracking fields (for tickets, Jira, support workflows)
                "issue_description": call_data.get("issue_description") or analysis.get("issue_description"),
                "issue_category": call_data.get("issue_category") or analysis.get("issue_category"),
                "issue_priority": call_data.get("issue_priority") or analysis.get("issue_priority"),
                "action_required": call_data.get("action_required") or analysis.get("action_required"),
                "extracted_data": call_data.get("extracted_data") or analysis.get("extracted_data", {}),
                # Appointment information
                "appointment_booked": call_data.get("appointment_booked", False),
                "appointment_date": call_data.get("appointment_date"),
                "sentiment": call_data.get("sentiment"),
                # Assistant information
                "assistant_id": call_data.get("assistant_id") or assistant_id,
                "assistant_name": call_data.get("assistant_name"),
                "agent": {
                    "name": call_data.get("agent_name", ""),
                    "email": call_data.get("agent_email", ""),
                },
                # Campaign and metadata
                "campaign_id": call_data.get("campaign_id"),
                "metadata": call_data.get("metadata", {}),
                "timestamp": datetime.utcnow().isoformat()
            }

            # Trigger workflows using the new method with assistant filtering
            engine = WorkflowEngine()
            results = await engine.trigger_workflows(
                trigger_event=TriggerEvent.CALL_COMPLETED,
                trigger_data=trigger_data,
                user_id=user_id,
                assistant_id=assistant_id,
                assigned_workflow_ids=assigned_workflow_ids
            )

            success_count = sum(1 for r in results if r.get("success"))
            logger.info(f"[WORKFLOW_TRIGGER] Triggered {success_count}/{len(results)} workflows for call {call_data.get('_id')}")

        except Exception as e:
            logger.error(f"[WORKFLOW_TRIGGER] Error triggering call_completed workflows: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't raise - we don't want to fail the call processing

    @staticmethod
    async def trigger_call_failed(
        call_data: Dict[str, Any],
        user_id: str
    ) -> None:
        """Trigger workflows when a call fails"""
        try:
            logger.info(f"Triggering call_failed workflows for user {user_id}")

            trigger_data = {
                "call_id": call_data.get("_id") or call_data.get("id"),
                "call": {
                    "id": call_data.get("_id") or call_data.get("id"),
                    "status": call_data.get("status"),
                    "error": call_data.get("error_message", ""),
                    "from_number": call_data.get("from_number"),
                    "to_number": call_data.get("to_number"),
                    "created_at": call_data.get("created_at"),
                },
                "customer": {
                    "phone": call_data.get("to_number") or call_data.get("from_number"),
                },
                "timestamp": datetime.utcnow().isoformat()
            }

            engine = WorkflowEngine()
            results = await engine.trigger_workflow(
                TriggerEvent.CALL_FAILED,
                trigger_data,
                user_id
            )

            logger.info(f"Triggered {len(results)} workflows for failed call")

        except Exception as e:
            logger.error(f"Error triggering call_failed workflows: {e}")

    @staticmethod
    async def trigger_call_no_answer(
        call_data: Dict[str, Any],
        user_id: str
    ) -> None:
        """Trigger workflows when a call receives no answer"""
        try:
            trigger_data = {
                "call_id": call_data.get("_id") or call_data.get("id"),
                "call": {
                    "id": call_data.get("_id") or call_data.get("id"),
                    "status": "no-answer",
                    "to_number": call_data.get("to_number"),
                    "from_number": call_data.get("from_number"),
                    "created_at": call_data.get("created_at"),
                },
                "customer": {
                    "phone": call_data.get("to_number"),
                },
                "campaign_id": call_data.get("campaign_id"),
                "timestamp": datetime.utcnow().isoformat()
            }

            engine = WorkflowEngine()
            await engine.trigger_workflow(
                TriggerEvent.CALL_NO_ANSWER,
                trigger_data,
                user_id
            )

        except Exception as e:
            logger.error(f"Error triggering call_no_answer workflows: {e}")

    @staticmethod
    async def trigger_campaign_completed(
        campaign_data: Dict[str, Any],
        user_id: str
    ) -> None:
        """Trigger workflows when a campaign is completed"""
        try:
            logger.info(f"Triggering campaign_completed workflows for user {user_id}")

            trigger_data = {
                "campaign_id": campaign_data.get("_id") or campaign_data.get("id"),
                "campaign": {
                    "id": campaign_data.get("_id") or campaign_data.get("id"),
                    "name": campaign_data.get("name"),
                    "status": campaign_data.get("status"),
                    "total_contacts": campaign_data.get("total_contacts", 0),
                    "completed_calls": campaign_data.get("completed_calls", 0),
                    "successful_calls": campaign_data.get("successful_calls", 0),
                    "failed_calls": campaign_data.get("failed_calls", 0),
                    "started_at": campaign_data.get("started_at"),
                    "completed_at": campaign_data.get("completed_at"),
                },
                "timestamp": datetime.utcnow().isoformat()
            }

            engine = WorkflowEngine()
            results = await engine.trigger_workflow(
                TriggerEvent.CAMPAIGN_COMPLETED,
                trigger_data,
                user_id
            )

            logger.info(f"Triggered {len(results)} workflows for campaign {campaign_data.get('_id')}")

        except Exception as e:
            logger.error(f"Error triggering campaign_completed workflows: {e}")

    @staticmethod
    def trigger_call_completed_sync(
        call_data: Dict[str, Any],
        user_id: str
    ) -> None:
        """
        Synchronous wrapper for trigger_call_completed
        Use this when calling from synchronous code
        """
        try:
            # Create event loop if needed
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run async function
            loop.run_until_complete(
                WorkflowTrigger.trigger_call_completed(call_data, user_id)
            )

        except Exception as e:
            logger.error(f"Error in sync trigger: {e}")

    @staticmethod
    def trigger_call_failed_sync(
        call_data: Dict[str, Any],
        user_id: str
    ) -> None:
        """Synchronous wrapper for trigger_call_failed"""
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(
                WorkflowTrigger.trigger_call_failed(call_data, user_id)
            )

        except Exception as e:
            logger.error(f"Error in sync trigger: {e}")

    @staticmethod
    def trigger_campaign_completed_sync(
        campaign_data: Dict[str, Any],
        user_id: str
    ) -> None:
        """Synchronous wrapper for trigger_campaign_completed"""
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(
                WorkflowTrigger.trigger_campaign_completed(campaign_data, user_id)
            )

        except Exception as e:
            logger.error(f"Error in sync trigger: {e}")
