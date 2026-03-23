"""
n8n Integration Service

Provides functionality to interact with n8n workflow automation platform:
- Trigger webhooks after calls
- List/manage workflows via n8n API
- Get workflow executions
"""

import httpx
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class N8NService:
    """Service to interact with n8n API and webhooks"""

    def __init__(self):
        self.api_url = os.getenv("N8N_API_URL", "http://n8n:5678")
        self.webhook_url = os.getenv("N8N_WEBHOOK_URL", "http://n8n:5678/webhook")
        self.api_key = os.getenv("N8N_API_KEY", "")
        self.enabled = os.getenv("N8N_ENABLED", "true").lower() == "true"
        self.timeout = 30  # seconds

    @property
    def headers(self) -> Dict[str, str]:
        """Get headers for n8n API requests"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["X-N8N-API-KEY"] = self.api_key
        return headers

    def is_enabled(self) -> bool:
        """Check if n8n integration is enabled"""
        return self.enabled

    # ==================== Webhook Methods ====================

    async def trigger_webhook(
        self,
        webhook_path: str,
        data: Dict[str, Any],
        is_test: bool = False
    ) -> Dict[str, Any]:
        """
        Trigger an n8n webhook with data

        Args:
            webhook_path: The webhook path/ID (e.g., "call-completed" or UUID)
            data: The data to send to the webhook
            is_test: If True, use webhook-test endpoint

        Returns:
            Dict with success status and response/error
        """
        if not self.enabled:
            logger.info("n8n integration is disabled, skipping webhook trigger")
            return {"success": False, "error": "n8n integration is disabled"}

        try:
            base = self.webhook_url.replace("/webhook", "/webhook-test") if is_test else self.webhook_url
            url = f"{base}/{webhook_path}"

            logger.info(f"Triggering n8n webhook: {url}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=data)

                if response.status_code >= 200 and response.status_code < 300:
                    logger.info(f"Successfully triggered n8n webhook: {webhook_path}")
                    try:
                        response_data = response.json()
                    except:
                        response_data = {"message": response.text}
                    return {
                        "success": True,
                        "status_code": response.status_code,
                        "response": response_data
                    }
                else:
                    logger.error(f"n8n webhook failed with status {response.status_code}: {response.text}")
                    return {
                        "success": False,
                        "status_code": response.status_code,
                        "error": response.text
                    }

        except httpx.TimeoutException:
            logger.error(f"Timeout triggering n8n webhook: {webhook_path}")
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            logger.error(f"Error triggering n8n webhook: {e}")
            return {"success": False, "error": str(e)}

    async def trigger_call_completed(
        self,
        call_data: Dict[str, Any],
        user_id: str,
        webhook_path: str = "call-completed"
    ) -> Dict[str, Any]:
        """
        Trigger n8n webhook after call completion

        Args:
            call_data: Call information (transcript, summary, sentiment, etc.)
            user_id: The user ID
            webhook_path: Custom webhook path (default: "call-completed")

        Returns:
            Dict with success status
        """
        # Get analysis data for issue tracking
        analysis = call_data.get("analysis", {})

        trigger_data = {
            "event": "call_completed",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            # Call information
            "call": {
                "id": call_data.get("call_sid"),
                "status": call_data.get("status", "completed"),
                "duration": call_data.get("duration"),
                "direction": call_data.get("direction"),
                "from_number": call_data.get("from_number"),
                "to_number": call_data.get("to_number"),
                "transcript": call_data.get("transcript") or call_data.get("transcription"),
                "summary": call_data.get("summary"),
                "sentiment": call_data.get("sentiment"),
                "sentiment_score": call_data.get("sentiment_score"),
                "recording_url": call_data.get("recording_url"),
                "started_at": call_data.get("started_at") or call_data.get("created_at"),
                "ended_at": call_data.get("ended_at"),
            },
            # Customer information (for sending emails, creating contacts)
            "customer": {
                "name": call_data.get("customer_name"),
                "phone": call_data.get("customer_phone") or call_data.get("to_number"),
                "email": call_data.get("customer_email"),
            },
            # Top-level customer fields for easier access in n8n
            "customer_name": call_data.get("customer_name"),
            "customer_email": call_data.get("customer_email"),
            "customer_phone": call_data.get("customer_phone") or call_data.get("to_number"),
            "email_mentioned": call_data.get("email_mentioned", False),
            # Issue tracking fields (for creating tickets, Jira issues, etc.)
            "issue": {
                "description": call_data.get("issue_description") or analysis.get("issue_description"),
                "category": call_data.get("issue_category") or analysis.get("issue_category"),
                "priority": call_data.get("issue_priority") or analysis.get("issue_priority"),
                "action_required": call_data.get("action_required") or analysis.get("action_required"),
            },
            # Top-level issue fields for easier access in n8n
            "issue_description": call_data.get("issue_description") or analysis.get("issue_description"),
            "issue_category": call_data.get("issue_category") or analysis.get("issue_category"),
            "issue_priority": call_data.get("issue_priority") or analysis.get("issue_priority"),
            "action_required": call_data.get("action_required") or analysis.get("action_required"),
            # Extracted data from call
            "extracted_data": call_data.get("extracted_data") or analysis.get("extracted_data", {}),
            # Assistant information
            "assistant": {
                "id": call_data.get("assistant_id"),
                "name": call_data.get("assistant_name"),
            },
            "assistant_id": call_data.get("assistant_id"),
            "assistant_name": call_data.get("assistant_name"),
            # Campaign information
            "campaign": {
                "id": call_data.get("campaign_id"),
                "name": call_data.get("campaign_name"),
            },
            "campaign_id": call_data.get("campaign_id"),
            # Appointment information
            "appointment_booked": call_data.get("appointment_booked", False),
            "appointment_date": call_data.get("appointment_date"),
            "appointment": call_data.get("appointment_details") or analysis.get("appointment", {}),
            # Analysis summary
            "summary": call_data.get("summary"),
            "sentiment": call_data.get("sentiment"),
            "transcript": call_data.get("transcript") or call_data.get("transcription"),
            # Additional metadata
            "metadata": call_data.get("metadata", {})
        }

        logger.info(f"[N8N] Triggering webhook with customer_email={trigger_data.get('customer_email')}, issue_description={trigger_data.get('issue_description')[:50] if trigger_data.get('issue_description') else 'None'}")

        return await self.trigger_webhook(webhook_path, trigger_data)

    async def trigger_call_failed(
        self,
        call_data: Dict[str, Any],
        user_id: str,
        webhook_path: str = "call-failed"
    ) -> Dict[str, Any]:
        """Trigger n8n webhook when call fails"""
        trigger_data = {
            "event": "call_failed",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "call": {
                "id": call_data.get("call_sid"),
                "status": call_data.get("status", "failed"),
                "error": call_data.get("error_message"),
                "from_number": call_data.get("from_number"),
                "to_number": call_data.get("to_number"),
            },
            "customer": {
                "name": call_data.get("customer_name"),
                "phone": call_data.get("customer_phone") or call_data.get("to_number"),
            },
            "assistant": {
                "id": call_data.get("assistant_id"),
            },
            "campaign": {
                "id": call_data.get("campaign_id"),
            }
        }

        return await self.trigger_webhook(webhook_path, trigger_data)

    async def trigger_campaign_completed(
        self,
        campaign_data: Dict[str, Any],
        user_id: str,
        webhook_path: str = "campaign-completed"
    ) -> Dict[str, Any]:
        """Trigger n8n webhook when campaign completes"""
        trigger_data = {
            "event": "campaign_completed",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "campaign": {
                "id": campaign_data.get("campaign_id"),
                "name": campaign_data.get("name"),
                "status": campaign_data.get("status", "completed"),
                "total_contacts": campaign_data.get("total_contacts"),
                "completed_calls": campaign_data.get("completed_calls"),
                "successful_calls": campaign_data.get("successful_calls"),
                "failed_calls": campaign_data.get("failed_calls"),
                "started_at": campaign_data.get("started_at"),
                "completed_at": campaign_data.get("completed_at"),
            },
            "statistics": campaign_data.get("statistics", {}),
            "metadata": campaign_data.get("metadata", {})
        }

        return await self.trigger_webhook(webhook_path, trigger_data)

    # ==================== API Methods ====================

    async def list_workflows(
        self,
        active_only: bool = False,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        List all workflows from n8n

        Args:
            active_only: If True, only return active workflows
            limit: Maximum number of workflows to return

        Returns:
            Dict with workflows list or error
        """
        if not self.enabled:
            return {"success": False, "error": "n8n integration is disabled", "data": []}

        try:
            url = f"{self.api_url}/api/v1/workflows"
            params = {"limit": limit}
            if active_only:
                params["active"] = "true"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "data": data.get("data", []),
                        "nextCursor": data.get("nextCursor")
                    }
                else:
                    logger.error(f"Failed to list n8n workflows: {response.status_code}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status_code}",
                        "data": []
                    }

        except Exception as e:
            logger.error(f"Error listing n8n workflows: {e}")
            return {"success": False, "error": str(e), "data": []}

    async def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific workflow by ID"""
        if not self.enabled:
            return None

        try:
            url = f"{self.api_url}/api/v1/workflows/{workflow_id}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to get n8n workflow {workflow_id}: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error getting n8n workflow: {e}")
            return None

    async def activate_workflow(self, workflow_id: str) -> bool:
        """Activate a workflow"""
        if not self.enabled:
            return False

        try:
            url = f"{self.api_url}/api/v1/workflows/{workflow_id}/activate"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers)
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Error activating n8n workflow: {e}")
            return False

    async def deactivate_workflow(self, workflow_id: str) -> bool:
        """Deactivate a workflow"""
        if not self.enabled:
            return False

        try:
            url = f"{self.api_url}/api/v1/workflows/{workflow_id}/deactivate"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers)
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Error deactivating n8n workflow: {e}")
            return False

    async def get_executions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get workflow executions

        Args:
            workflow_id: Filter by workflow ID
            status: Filter by status (success, error, waiting)
            limit: Maximum number of executions to return

        Returns:
            Dict with executions list
        """
        if not self.enabled:
            return {"success": False, "error": "n8n integration is disabled", "data": []}

        try:
            url = f"{self.api_url}/api/v1/executions"
            params = {"limit": limit}
            if workflow_id:
                params["workflowId"] = workflow_id
            if status:
                params["status"] = status

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "data": data.get("data", []),
                        "nextCursor": data.get("nextCursor")
                    }
                else:
                    logger.error(f"Failed to get n8n executions: {response.status_code}")
                    return {"success": False, "error": f"API error: {response.status_code}", "data": []}

        except Exception as e:
            logger.error(f"Error getting n8n executions: {e}")
            return {"success": False, "error": str(e), "data": []}

    async def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific execution by ID"""
        if not self.enabled:
            return None

        try:
            url = f"{self.api_url}/api/v1/executions/{execution_id}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to get n8n execution {execution_id}: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error getting n8n execution: {e}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        """
        Check n8n service health

        Tries multiple endpoints since different n8n deployments
        (Docker, Cloud Run, etc.) may expose different health endpoints
        """
        if not self.enabled:
            return {"healthy": False, "error": "n8n integration is disabled"}

        # List of endpoints to try for health check
        # Cloud Run n8n typically responds on root or /rest/settings
        health_endpoints = [
            "/rest/settings",  # n8n settings endpoint (works on most deployments)
            "/healthz",        # Standard health endpoint
            "/health",         # Alternative health endpoint
            "/",               # Root endpoint (n8n serves UI here)
        ]

        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            for endpoint in health_endpoints:
                try:
                    url = f"{self.api_url}{endpoint}"
                    logger.debug(f"Trying n8n health check at: {url}")

                    response = await client.get(url, headers=self.headers)

                    # Consider any 2xx or 3xx response as healthy
                    # n8n may return 401 for API endpoints without key, but that still means it's running
                    if response.status_code < 500:
                        logger.info(f"n8n health check passed at {endpoint} with status {response.status_code}")
                        return {
                            "healthy": True,
                            "status_code": response.status_code,
                            "api_url": self.api_url,
                            "endpoint_checked": endpoint
                        }

                except httpx.TimeoutException:
                    logger.debug(f"Timeout on n8n health check at {endpoint}")
                    continue
                except Exception as e:
                    logger.debug(f"Error on n8n health check at {endpoint}: {e}")
                    continue

        # All endpoints failed
        logger.error(f"n8n health check failed for all endpoints at {self.api_url}")
        return {
            "healthy": False,
            "error": "Could not connect to n8n service",
            "api_url": self.api_url
        }


# Singleton instance
n8n_service = N8NService()
