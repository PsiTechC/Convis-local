"""
HubSpot Integration Service
Handles HubSpot CRM operations for contacts, deals, notes, and activities
"""
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from app.models.integration import HubSpotCredentials
from app.services.integrations.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class HubSpotService:
    """HubSpot CRM API integration service"""

    def __init__(self, credentials: HubSpotCredentials):
        """Initialize HubSpot service with credentials"""
        self.access_token = credentials.access_token
        self.portal_id = credentials.portal_id

        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to HubSpot API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=self.headers,
                timeout=30
            )

            response.raise_for_status()
            return response.json() if response.text else {}

        except requests.exceptions.HTTPError as e:
            logger.error(f"HubSpot API HTTP error: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            raise Exception(f"HubSpot API error: {e.response.text if e.response else str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"HubSpot API request error: {e}")
            raise Exception(f"HubSpot connection error: {str(e)}")

    def test_connection(self) -> Dict[str, Any]:
        """Test HubSpot connection and credentials"""
        try:
            # Try to get access token info
            result = self._make_request("GET", "/oauth/v1/access-tokens/" + self.access_token)
            return {
                "success": True,
                "message": "Successfully connected to HubSpot",
                "hub_id": result.get("hub_id"),
                "user": result.get("user")
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    def search_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Search for a contact by email address"""
        try:
            search_data = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "email",
                                "operator": "EQ",
                                "value": email
                            }
                        ]
                    }
                ],
                "properties": ["email", "firstname", "lastname", "phone", "company"]
            }

            result = self._make_request(
                "POST",
                "/crm/v3/objects/contacts/search",
                data=search_data
            )

            results = result.get("results", [])
            if results:
                return results[0]
            return None

        except Exception as e:
            logger.error(f"Error searching HubSpot contact: {e}")
            return None

    def create_contact(
        self,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a HubSpot contact

        Args:
            config: Action configuration with email, firstname, lastname, etc.
            context_data: Data for template rendering

        Returns:
            Created contact details
        """
        try:
            # Render required fields
            email = TemplateRenderer.render(
                config.get("email", ""),
                context_data
            )

            if not email:
                return {
                    "success": False,
                    "error": "Email is required",
                    "message": "Email is required to create a contact"
                }

            # Check if contact already exists
            existing_contact = self.search_contact_by_email(email)
            if existing_contact and not config.get("update_if_exists", True):
                return {
                    "success": False,
                    "error": "Contact already exists",
                    "contact_id": existing_contact.get("id"),
                    "message": f"Contact with email {email} already exists"
                }

            # If exists and update_if_exists is True, update instead
            if existing_contact and config.get("update_if_exists", True):
                return self.update_contact(
                    existing_contact.get("id"),
                    config,
                    context_data
                )

            # Build contact properties
            properties = {
                "email": email
            }

            # Add optional fields
            optional_fields = [
                "firstname", "lastname", "phone", "company",
                "website", "address", "city", "state", "zip",
                "jobtitle", "lifecyclestage", "hs_lead_status"
            ]

            for field in optional_fields:
                if field in config:
                    properties[field] = TemplateRenderer.render(
                        config[field],
                        context_data
                    )

            # Add custom properties
            if "custom_properties" in config:
                for prop_name, prop_value in config["custom_properties"].items():
                    properties[prop_name] = TemplateRenderer.render(
                        str(prop_value),
                        context_data
                    )

            contact_data = {"properties": properties}

            # Create the contact
            logger.info(f"Creating HubSpot contact: {email}")
            result = self._make_request(
                "POST",
                "/crm/v3/objects/contacts",
                data=contact_data
            )

            contact_id = result.get("id")

            return {
                "success": True,
                "contact_id": contact_id,
                "email": email,
                "url": f"https://app.hubspot.com/contacts/{self.portal_id}/contact/{contact_id}",
                "message": f"Created HubSpot contact {email}"
            }

        except Exception as e:
            logger.error(f"Error creating HubSpot contact: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create HubSpot contact: {str(e)}"
            }

    def update_contact(
        self,
        contact_id: str,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing HubSpot contact"""
        try:
            properties = {}

            # Update allowed fields
            updatable_fields = [
                "firstname", "lastname", "phone", "company",
                "website", "address", "city", "state", "zip",
                "jobtitle", "lifecyclestage", "hs_lead_status"
            ]

            for field in updatable_fields:
                if field in config:
                    properties[field] = TemplateRenderer.render(
                        config[field],
                        context_data
                    )

            # Add custom properties
            if "custom_properties" in config:
                for prop_name, prop_value in config["custom_properties"].items():
                    properties[prop_name] = TemplateRenderer.render(
                        str(prop_value),
                        context_data
                    )

            if not properties:
                return {
                    "success": False,
                    "error": "No properties to update",
                    "message": "No properties specified for update"
                }

            update_data = {"properties": properties}

            # Update the contact
            logger.info(f"Updating HubSpot contact: {contact_id}")
            result = self._make_request(
                "PATCH",
                f"/crm/v3/objects/contacts/{contact_id}",
                data=update_data
            )

            return {
                "success": True,
                "contact_id": contact_id,
                "url": f"https://app.hubspot.com/contacts/{self.portal_id}/contact/{contact_id}",
                "message": f"Updated HubSpot contact {contact_id}"
            }

        except Exception as e:
            logger.error(f"Error updating HubSpot contact: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to update HubSpot contact: {str(e)}"
            }

    def create_note(
        self,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a note and associate with contact/deal

        Args:
            config: Must include 'note_body' and either 'contact_email' or 'contact_id'
            context_data: Data for template rendering
        """
        try:
            # Render note body
            note_body = TemplateRenderer.render(
                config.get("note_body", ""),
                context_data
            )

            if not note_body:
                return {
                    "success": False,
                    "error": "Note body is required",
                    "message": "Note body is required"
                }

            # Get contact ID
            contact_id = None
            if "contact_id" in config:
                contact_id = TemplateRenderer.render(config["contact_id"], context_data)
            elif "contact_email" in config:
                email = TemplateRenderer.render(config["contact_email"], context_data)
                contact = self.search_contact_by_email(email)
                if contact:
                    contact_id = contact.get("id")

            # Create note
            note_data = {
                "properties": {
                    "hs_note_body": note_body,
                    "hs_timestamp": str(int(datetime.utcnow().timestamp() * 1000))
                }
            }

            logger.info("Creating HubSpot note")
            result = self._make_request(
                "POST",
                "/crm/v3/objects/notes",
                data=note_data
            )

            note_id = result.get("id")

            # Associate with contact if we have contact_id
            if contact_id:
                association_data = [
                    {
                        "to": {"id": contact_id},
                        "types": [
                            {
                                "associationCategory": "HUBSPOT_DEFINED",
                                "associationTypeId": 202  # Note to Contact
                            }
                        ]
                    }
                ]

                self._make_request(
                    "PUT",
                    f"/crm/v3/objects/notes/{note_id}/associations/contacts",
                    data=association_data
                )

            return {
                "success": True,
                "note_id": note_id,
                "contact_id": contact_id,
                "message": f"Created HubSpot note"
            }

        except Exception as e:
            logger.error(f"Error creating HubSpot note: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create HubSpot note: {str(e)}"
            }

    def create_engagement(
        self,
        engagement_type: str,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create an engagement (call, meeting, email, task)

        Args:
            engagement_type: 'CALL', 'MEETING', 'EMAIL', 'TASK'
            config: Engagement details
            context_data: Data for template rendering
        """
        try:
            # Build engagement data based on type
            properties = {}

            if engagement_type == "CALL":
                properties["hs_call_title"] = TemplateRenderer.render(
                    config.get("title", "Call"),
                    context_data
                )
                properties["hs_call_body"] = TemplateRenderer.render(
                    config.get("body", ""),
                    context_data
                )
                if "duration" in config:
                    properties["hs_call_duration"] = str(config["duration"])
                properties["hs_call_status"] = config.get("status", "COMPLETED")

            # Set timestamp
            properties["hs_timestamp"] = str(int(datetime.utcnow().timestamp() * 1000))

            engagement_data = {
                "properties": properties
            }

            # Create engagement
            endpoint = f"/crm/v3/objects/{engagement_type.lower()}s"
            result = self._make_request("POST", endpoint, data=engagement_data)

            return {
                "success": True,
                "engagement_id": result.get("id"),
                "message": f"Created {engagement_type} engagement"
            }

        except Exception as e:
            logger.error(f"Error creating engagement: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create engagement: {str(e)}"
            }
