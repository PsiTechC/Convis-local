"""
Workflow Executor Service

Executes user-defined workflows when triggers fire (e.g., call completed).
Supports actions like:
- Send email to customer
- Send Slack notification
- Update CRM
- Custom webhook
"""

import logging
import httpx
import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """
    Executes user workflows based on trigger events.

    Each workflow has:
    - trigger_type: When to execute (e.g., "call_completed")
    - template_id: Which template (determines the action)
    - config: User-provided configuration for the action
    - active: Whether the workflow is enabled
    """

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("EMAIL_USER", "")
        self.smtp_pass = os.getenv("EMAIL_PASS", "")
        self.smtp_use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    async def execute_workflows_for_trigger(
        self,
        trigger_type: str,
        user_id: str,
        call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute all active workflows for a user when a trigger fires.

        Args:
            trigger_type: The trigger event (e.g., "call_completed")
            user_id: The user whose workflows to execute
            call_data: Data from the call to pass to workflows

        Returns:
            Dict with execution results
        """
        try:
            from app.config.async_database import AsyncDatabase

            db = await AsyncDatabase.get_db()
            workflows_collection = db["workflows"]

            # Find all active workflows for this user and trigger type
            # Note: "trigger_event" is the field name used by the new workflow system
            # Map trigger_type to trigger_event format (e.g., "call_completed" -> "CALL_COMPLETED")
            trigger_event = trigger_type.upper()

            workflows = await workflows_collection.find({
                "user_id": user_id,
                "trigger_event": trigger_event,
                "is_active": True
            }).to_list(length=100)

            if not workflows:
                logger.info(f"No active workflows found for user {user_id} with trigger {trigger_type}")
                return {"success": True, "executed": 0, "results": []}

            logger.info(f"Found {len(workflows)} active workflows for user {user_id}")

            # Execute all workflows in parallel
            tasks = []
            for workflow in workflows:
                task = self._execute_single_workflow(workflow, call_data, db)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            executed = 0
            workflow_results = []
            for i, result in enumerate(results):
                workflow_id = str(workflows[i]["_id"])
                if isinstance(result, Exception):
                    logger.error(f"Workflow {workflow_id} failed: {result}")
                    workflow_results.append({
                        "workflow_id": workflow_id,
                        "success": False,
                        "error": str(result)
                    })
                else:
                    executed += 1
                    workflow_results.append({
                        "workflow_id": workflow_id,
                        "success": result.get("success", False),
                        "message": result.get("message", "")
                    })

                # Update execution count
                await workflows_collection.update_one(
                    {"_id": workflows[i]["_id"]},
                    {
                        "$inc": {"execution_count": 1},
                        "$set": {
                            "last_execution": {
                                "status": "success" if not isinstance(result, Exception) and result.get("success") else "error",
                                "finished_at": datetime.utcnow().isoformat(),
                                "call_sid": call_data.get("call_sid")
                            },
                            "updated_at": datetime.utcnow()
                        }
                    }
                )

            return {
                "success": True,
                "executed": executed,
                "total": len(workflows),
                "results": workflow_results
            }

        except Exception as e:
            logger.error(f"Error executing workflows: {e}")
            return {"success": False, "error": str(e), "executed": 0}

    async def _execute_single_workflow(
        self,
        workflow: Dict[str, Any],
        call_data: Dict[str, Any],
        db
    ) -> Dict[str, Any]:
        """Execute a single workflow based on its template."""
        try:
            template_id = workflow.get("template_id")
            config = workflow.get("config", {})
            workflow_name = workflow.get("name", "Unnamed Workflow")

            logger.info(f"Executing workflow '{workflow_name}' (template: {template_id})")

            if template_id == "send-email-after-call":
                return await self._execute_email_workflow(config, call_data, db)

            elif template_id == "slack-notification":
                return await self._execute_slack_workflow(config, call_data)

            elif template_id == "update-crm":
                return await self._execute_crm_workflow(config, call_data)

            elif template_id == "create-calendar-event":
                return await self._execute_calendar_workflow(config, call_data, db)

            elif template_id == "custom-webhook":
                return await self._execute_webhook_workflow(config, call_data)

            else:
                logger.warning(f"Unknown template_id: {template_id}")
                return {"success": False, "error": f"Unknown template: {template_id}"}

        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_email_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any],
        db
    ) -> Dict[str, Any]:
        """
        Send follow-up email after call.

        Uses customer email from:
        1. config.to_email (if user specified a fixed email)
        2. call_data.customer_email (extracted from call transcript)
        3. Lead's email from database
        """
        try:
            # Determine recipient email
            to_email = config.get("to_email", "").strip()

            if not to_email:
                # Try customer email from call analysis
                to_email = call_data.get("customer_email", "")

            if not to_email:
                # Try lead's email from database
                lead_id = call_data.get("lead_id")
                if lead_id:
                    leads = db["leads"]
                    lead = await leads.find_one({"_id": ObjectId(lead_id)})
                    if lead:
                        to_email = lead.get("email", "")

            if not to_email:
                logger.warning("No email address available for email workflow")
                return {"success": False, "error": "No recipient email address available"}

            # Build email content
            subject = config.get("subject", "Thank you for your call")
            customer_name = call_data.get("customer_name", "")

            # Replace placeholders in subject
            subject = subject.replace("{{customer_name}}", customer_name or "there")

            # Build email body
            body_parts = [f"Hello {customer_name or 'there'},\n"]
            body_parts.append("Thank you for speaking with us today.\n")

            if config.get("include_summary", True) and call_data.get("summary"):
                body_parts.append("\n--- Call Summary ---\n")
                body_parts.append(call_data.get("summary", ""))
                body_parts.append("\n")

            if config.get("include_transcript", False) and call_data.get("transcript"):
                body_parts.append("\n--- Full Transcript ---\n")
                transcript = call_data.get("transcript", "")
                # Truncate very long transcripts
                if len(transcript) > 5000:
                    transcript = transcript[:5000] + "\n... [truncated]"
                body_parts.append(transcript)
                body_parts.append("\n")

            body_parts.append("\nBest regards,\nYour Team")

            body = "\n".join(body_parts)

            # Send email
            result = await self._send_email(to_email, subject, body)

            if result["success"]:
                logger.info(f"Email sent successfully to {to_email}")

            return result

        except Exception as e:
            logger.error(f"Email workflow failed: {e}")
            return {"success": False, "error": str(e)}

    async def _send_email(self, to_email: str, subject: str, body: str) -> Dict[str, Any]:
        """Send email using SMTP."""
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            if not self.smtp_user or not self.smtp_pass:
                logger.error("SMTP credentials not configured")
                return {"success": False, "error": "Email not configured"}

            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            if self.smtp_use_ssl:
                # Use SSL (port 465)
                await aiosmtplib.send(
                    msg,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    username=self.smtp_user,
                    password=self.smtp_pass,
                    use_tls=True
                )
            else:
                # Use STARTTLS (port 587)
                await aiosmtplib.send(
                    msg,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    username=self.smtp_user,
                    password=self.smtp_pass,
                    start_tls=True
                )

            return {"success": True, "message": f"Email sent to {to_email}"}

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_slack_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send Slack notification via webhook."""
        try:
            webhook_url = config.get("webhook_url", "")
            if not webhook_url:
                return {"success": False, "error": "Slack webhook URL not configured"}

            # Check sentiment filter
            only_negative = config.get("only_negative", False)
            sentiment = call_data.get("sentiment", "neutral")

            if only_negative and sentiment != "negative":
                logger.info(f"Skipping Slack notification - sentiment is {sentiment}, not negative")
                return {"success": True, "message": "Skipped - sentiment not negative"}

            # Build Slack message
            customer_name = call_data.get("customer_name", "Unknown")
            customer_phone = call_data.get("customer_phone", "")
            summary = call_data.get("summary", "No summary available")

            # Sentiment emoji
            sentiment_emoji = {
                "positive": ":smile:",
                "neutral": ":neutral_face:",
                "negative": ":disappointed:"
            }.get(sentiment, ":grey_question:")

            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📞 Call Completed: {customer_name}",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                        {"type": "mrkdwn", "text": f"*Phone:*\n{customer_phone}"}
                    ]
                }
            ]

            if config.get("include_sentiment", True):
                blocks.append({
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Sentiment:*\n{sentiment_emoji} {sentiment.capitalize()}"},
                        {"type": "mrkdwn", "text": f"*Duration:*\n{call_data.get('duration', 0)}s"}
                    ]
                })

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary}"}
            })

            payload = {"blocks": blocks}

            # Add channel if specified
            channel = config.get("channel", "").strip()
            if channel:
                payload["channel"] = channel

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=payload)

                if response.status_code == 200:
                    return {"success": True, "message": "Slack notification sent"}
                else:
                    return {"success": False, "error": f"Slack API error: {response.status_code}"}

        except Exception as e:
            logger.error(f"Slack workflow failed: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_crm_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update CRM with call data."""
        try:
            crm_provider = config.get("crm_provider", "")
            api_key = config.get("api_key", "")

            if not crm_provider or not api_key:
                return {"success": False, "error": "CRM provider or API key not configured"}

            customer_email = call_data.get("customer_email", "")
            customer_name = call_data.get("customer_name", "")
            customer_phone = call_data.get("customer_phone", "")

            if crm_provider == "hubspot":
                return await self._update_hubspot(api_key, config, call_data)

            elif crm_provider == "salesforce":
                # Placeholder for Salesforce integration
                logger.info("Salesforce integration - placeholder")
                return {"success": True, "message": "Salesforce update (placeholder)"}

            elif crm_provider == "pipedrive":
                # Placeholder for Pipedrive integration
                logger.info("Pipedrive integration - placeholder")
                return {"success": True, "message": "Pipedrive update (placeholder)"}

            elif crm_provider == "zoho":
                # Placeholder for Zoho integration
                logger.info("Zoho integration - placeholder")
                return {"success": True, "message": "Zoho update (placeholder)"}

            else:
                return {"success": False, "error": f"Unknown CRM provider: {crm_provider}"}

        except Exception as e:
            logger.error(f"CRM workflow failed: {e}")
            return {"success": False, "error": str(e)}

    async def _update_hubspot(
        self,
        api_key: str,
        config: Dict[str, Any],
        call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update HubSpot with call data."""
        try:
            customer_email = call_data.get("customer_email", "")
            customer_name = call_data.get("customer_name", "")
            customer_phone = call_data.get("customer_phone", "")

            if not customer_email and not customer_phone:
                return {"success": False, "error": "No email or phone to identify contact"}

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                contact_id = None

                # Search for existing contact
                if customer_email:
                    search_response = await client.post(
                        "https://api.hubapi.com/crm/v3/objects/contacts/search",
                        headers=headers,
                        json={
                            "filterGroups": [{
                                "filters": [{
                                    "propertyName": "email",
                                    "operator": "EQ",
                                    "value": customer_email
                                }]
                            }]
                        }
                    )

                    if search_response.status_code == 200:
                        results = search_response.json().get("results", [])
                        if results:
                            contact_id = results[0]["id"]

                # Create contact if not found and config allows
                if not contact_id and config.get("create_contact", True):
                    properties = {}
                    if customer_email:
                        properties["email"] = customer_email
                    if customer_name:
                        # Split name into first/last
                        name_parts = customer_name.split(" ", 1)
                        properties["firstname"] = name_parts[0]
                        if len(name_parts) > 1:
                            properties["lastname"] = name_parts[1]
                    if customer_phone:
                        properties["phone"] = customer_phone

                    if properties:
                        create_response = await client.post(
                            "https://api.hubapi.com/crm/v3/objects/contacts",
                            headers=headers,
                            json={"properties": properties}
                        )

                        if create_response.status_code in [200, 201]:
                            contact_id = create_response.json().get("id")
                            logger.info(f"Created HubSpot contact: {contact_id}")

                # Log call activity if contact found
                if contact_id and config.get("log_activity", True):
                    engagement_data = {
                        "properties": {
                            "hs_timestamp": datetime.utcnow().isoformat() + "Z",
                            "hs_call_title": f"AI Call - {call_data.get('sentiment', 'neutral').capitalize()}",
                            "hs_call_body": call_data.get("summary", "No summary"),
                            "hs_call_duration": str(call_data.get("duration", 0) * 1000),  # HubSpot uses ms
                            "hs_call_status": "COMPLETED"
                        },
                        "associations": [{
                            "to": {"id": contact_id},
                            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 194}]
                        }]
                    }

                    activity_response = await client.post(
                        "https://api.hubapi.com/crm/v3/objects/calls",
                        headers=headers,
                        json=engagement_data
                    )

                    if activity_response.status_code in [200, 201]:
                        logger.info(f"Logged call activity to HubSpot contact {contact_id}")
                        return {"success": True, "message": f"HubSpot updated (contact: {contact_id})"}
                    else:
                        logger.warning(f"Failed to log HubSpot activity: {activity_response.text}")

                if contact_id:
                    return {"success": True, "message": f"HubSpot contact found/created: {contact_id}"}
                else:
                    return {"success": False, "error": "Could not find or create HubSpot contact"}

        except Exception as e:
            logger.error(f"HubSpot update failed: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_calendar_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any],
        db
    ) -> Dict[str, Any]:
        """Create calendar event for follow-up."""
        try:
            # This is typically handled by the appointment extraction in post-call processing
            # Here we just log that the workflow triggered
            appointment = call_data.get("analysis", {}).get("appointment")

            if appointment:
                logger.info(f"Calendar event would be created: {appointment}")
                return {"success": True, "message": "Appointment detected and will be booked"}
            else:
                return {"success": True, "message": "No appointment detected in call"}

        except Exception as e:
            logger.error(f"Calendar workflow failed: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_webhook_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send call data to custom webhook."""
        try:
            webhook_url = config.get("webhook_url", "")
            if not webhook_url:
                return {"success": False, "error": "Webhook URL not configured"}

            method = config.get("method", "POST").upper()

            # Parse custom headers
            custom_headers = {"Content-Type": "application/json"}
            headers_config = config.get("custom_headers", "")
            if headers_config:
                try:
                    import json
                    if isinstance(headers_config, str):
                        extra_headers = json.loads(headers_config)
                    else:
                        extra_headers = headers_config
                    custom_headers.update(extra_headers)
                except:
                    pass

            # Prepare payload
            payload = {
                "event": "call_completed",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "call": {
                    "id": call_data.get("call_sid"),
                    "duration": call_data.get("duration"),
                    "sentiment": call_data.get("sentiment"),
                    "summary": call_data.get("summary"),
                    "transcript": call_data.get("transcript", "")[:10000],  # Limit size
                },
                "customer": {
                    "name": call_data.get("customer_name"),
                    "email": call_data.get("customer_email"),
                    "phone": call_data.get("customer_phone"),
                }
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "POST":
                    response = await client.post(webhook_url, json=payload, headers=custom_headers)
                elif method == "PUT":
                    response = await client.put(webhook_url, json=payload, headers=custom_headers)
                else:
                    return {"success": False, "error": f"Unsupported HTTP method: {method}"}

                if response.status_code >= 200 and response.status_code < 300:
                    return {"success": True, "message": f"Webhook sent ({response.status_code})"}
                else:
                    return {"success": False, "error": f"Webhook failed: {response.status_code}"}

        except Exception as e:
            logger.error(f"Webhook workflow failed: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
workflow_executor = WorkflowExecutor()
