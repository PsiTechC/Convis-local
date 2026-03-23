"""
WhatsApp Service
Handles integration with Railway WhatsApp API Backend
"""

import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class WhatsAppService:
    """Service for interacting with Railway WhatsApp API Backend"""

    def __init__(
        self,
        api_key: str,
        bearer_token: str,
        base_url: str = "https://whatsapp-api-backend-production.up.railway.app"
    ):
        """
        Initialize WhatsApp service for Railway API

        Args:
            api_key: x-api-key header value
            bearer_token: Authorization Bearer token
            base_url: Railway API base URL
        """
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "Authorization": f"Bearer {bearer_token}"
        }

    async def send_text_message(self, to: str, message: str) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp
        Note: WhatsApp Business API does NOT support free-form text messages.
        Only pre-approved template messages are allowed.

        Args:
            to: Recipient phone number with country code (e.g., +1234567890)
            message: Text message content

        Returns:
            Error response - text messages not supported
        """
        logger.error("WhatsApp Business API does not support free-form text messages. Only template messages are allowed.")

        return {
            "success": False,
            "error": "WhatsApp Business API only allows pre-approved template messages. Free-form text messages are not supported. Please use a template instead.",
            "response": {
                "message": "Text messages not supported by WhatsApp Business API",
                "suggestion": "Use a pre-approved template message instead"
            }
        }

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        parameters: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send a template message via WhatsApp (Railway API)

        Args:
            to: Recipient phone number (e.g., +919131296862)
            template_name: Name of the approved template (e.g., "atithi_host_1")
            parameters: List of parameter values for template variables

        Returns:
            API response with message ID
        """
        url = f"{self.base_url}/api/send-message"

        payload = {
            "to_number": to,
            "template_name": template_name,
            "whatsapp_request_type": "TEMPLATE",
            "parameters": parameters or []
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            logger.info(f"Template message '{template_name}' sent to {to}: {result}")

            # Extract message ID from Railway API response
            message_id = result.get("metaResponse", {}).get("messages", [{}])[0].get("id")

            return {
                "success": True,
                "message_id": message_id,
                "response": result
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send template message to {to}: {str(e)}")
            error_response = {}
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_response = e.response.json()
                except:
                    error_response = {"error": e.response.text}

            return {
                "success": False,
                "error": str(e),
                "response": error_response
            }

    async def sync_templates(self) -> Dict[str, Any]:
        """
        Sync/fetch available WhatsApp templates from Railway API

        Returns:
            List of available templates
        """
        # Try multiple possible endpoints
        endpoints = [
            "/api/templates",  # Most common endpoint for fetching templates
            "/api/get-templates",  # Alternative endpoint
            "/api/sync-templates",  # Sync endpoint (may only trigger sync)
        ]

        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"

            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
                result = response.json()

                logger.info(f"Templates response from {endpoint}: {result}")

                # Railway API might return templates in different formats
                # Try to extract templates from various possible response structures
                templates = []

                if isinstance(result, dict):
                    # Try different possible keys
                    templates = (
                        result.get("templates", []) or
                        result.get("data", []) or
                        result.get("message_templates", []) or
                        []
                    )

                    # If templates is still empty but result has 'data' as dict
                    if not templates and "data" in result and isinstance(result["data"], list):
                        templates = result["data"]

                elif isinstance(result, list):
                    # If the response itself is a list of templates
                    templates = result

                # If we found templates, use this endpoint
                if templates:
                    logger.info(f"Found templates using endpoint: {endpoint}")
                    break

            except requests.exceptions.RequestException as e:
                logger.warning(f"Endpoint {endpoint} failed: {str(e)}")
                continue

        # Normalize template format
        normalized_templates = []
        for template in templates:
            if isinstance(template, dict):
                # Extract template information
                normalized_templates.append({
                    "id": template.get("id") or template.get("name"),
                    "name": template.get("name"),
                    "status": template.get("status", "APPROVED"),
                    "language": template.get("language", "en"),
                    "category": template.get("category", "UTILITY"),
                    "components": template.get("components", [])
                })

        logger.info(f"Normalized {len(normalized_templates)} templates")

        if normalized_templates:
            return {
                "success": True,
                "templates": normalized_templates,
                "response": result
            }
        else:
            return {
                "success": False,
                "error": "No templates found. The Railway API may not have a template fetching endpoint, or templates need to be synced first.",
                "templates": []
            }

    async def create_template(
        self,
        template_name: str,
        category: str,
        language: str,
        body_text: str,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        buttons: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Create a new WhatsApp template via Railway API

        Args:
            template_name: Unique name for the template (lowercase, no spaces)
            category: Template category (UTILITY, MARKETING, AUTHENTICATION)
            language: Language code (e.g., 'en', 'en_US')
            body_text: Main message body (can include {{1}}, {{2}} placeholders)
            header_text: Optional header text
            footer_text: Optional footer text
            buttons: Optional list of button configurations

        Returns:
            API response with template creation status
        """
        # Try multiple possible endpoints for template creation
        endpoints = [
            "/api/message-templates",  # Common WhatsApp Business API endpoint
            "/api/create-template",    # Custom endpoint
            "/api/templates/create",   # Alternative format
        ]

        success_response = None
        last_error = None

        # Build components
        components = []

        if header_text:
            components.append({
                "type": "HEADER",
                "format": "TEXT",
                "text": header_text
            })

        components.append({
            "type": "BODY",
            "text": body_text
        })

        if footer_text:
            components.append({
                "type": "FOOTER",
                "text": footer_text
            })

        if buttons:
            components.append({
                "type": "BUTTONS",
                "buttons": buttons
            })

        payload = {
            "name": template_name,
            "category": category,
            "language": language,
            "components": components
        }

        # Try each endpoint
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"

            try:
                logger.info(f"Attempting to create template at {url}")
                response = requests.post(url, headers=self.headers, json=payload, timeout=30)

                # If we get a 2xx response, consider it success
                if 200 <= response.status_code < 300:
                    result = response.json()
                    logger.info(f"Template '{template_name}' created successfully via {endpoint}: {result}")

                    return {
                        "success": True,
                        "template": result,
                        "response": result
                    }
                else:
                    # Not a success, but not necessarily an error - try next endpoint
                    logger.warning(f"Endpoint {endpoint} returned status {response.status_code}")
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    continue

            except requests.exceptions.RequestException as e:
                logger.warning(f"Endpoint {endpoint} failed: {str(e)}")
                last_error = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        last_error = e.response.json()
                    except:
                        last_error = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
                continue

        # If we get here, none of the endpoints worked
        logger.error(f"Failed to create template '{template_name}' - all endpoints failed")

        return {
            "success": False,
            "error": f"Template creation is not supported by the Railway WhatsApp API. Please create templates directly in WhatsApp Business Manager (https://business.facebook.com/wa/manage/message-templates/). Last error: {last_error}",
            "response": last_error
        }

    async def get_message_templates(self) -> Dict[str, Any]:
        """
        Get all message templates (alias for sync_templates)

        Returns:
            List of message templates
        """
        return await self.sync_templates()

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the Railway WhatsApp API connection by syncing templates

        Returns:
            Connection test results
        """
        result = await self.sync_templates()

        if result.get("success"):
            return {
                "success": True,
                "message": "Connection successful! Railway WhatsApp API is accessible.",
                "templates_count": len(result.get("templates", []))
            }
        else:
            return {
                "success": False,
                "message": "Connection failed",
                "error": result.get("error")
            }

    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """
        Get status of a sent message
        Note: This may not be available in Railway API - check documentation

        Args:
            message_id: WhatsApp message ID

        Returns:
            Message status information
        """
        # Railway API may not have a direct status endpoint
        # You might need to rely on webhooks for status updates
        logger.warning("Message status endpoint not implemented for Railway API. Use webhooks for status updates.")
        return {
            "success": False,
            "error": "Status endpoint not available. Use webhooks for message status updates."
        }

    async def send_bulk_messages(
        self,
        recipients: List[str],
        template_name: str,
        parameters_per_recipient: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, Any]:
        """
        Send template messages to multiple recipients

        Args:
            recipients: List of phone numbers
            template_name: Template name to use
            parameters_per_recipient: Dict mapping phone number to parameters list

        Returns:
            Bulk send results
        """
        results = []
        success_count = 0
        failed_count = 0

        for recipient in recipients:
            params = parameters_per_recipient.get(recipient, []) if parameters_per_recipient else []

            result = await self.send_template_message(
                to=recipient,
                template_name=template_name,
                parameters=params
            )

            results.append({
                "to": recipient,
                "success": result.get("success"),
                "message_id": result.get("message_id"),
                "error": result.get("error")
            })

            if result.get("success"):
                success_count += 1
            else:
                failed_count += 1

        return {
            "success": True,
            "total": len(recipients),
            "successful": success_count,
            "failed": failed_count,
            "results": results
        }

    # Webhook-related methods can remain for handling incoming status updates
    async def verify_webhook_signature(self, payload: str, signature: str, app_secret: str) -> bool:
        """
        Verify webhook signature from WhatsApp

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value
            app_secret: Your app secret

        Returns:
            True if signature is valid
        """
        import hmac
        import hashlib

        expected_signature = hmac.new(
            app_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(
            f"sha256={expected_signature}",
            signature
        )
