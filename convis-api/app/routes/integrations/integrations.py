"""
Integration Management API Routes
Handles CRUD operations for user integrations with encrypted credential storage
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
import logging

from app.config.database import Database
from app.models.integration import (
    Integration, IntegrationType, IntegrationStatus,
    JiraCredentials, HubSpotCredentials, EmailCredentials,
    SlackCredentials, WebhookCredentials, OpenAICredentials,
    AnthropicCredentials, TwilioCredentials, SendGridCredentials,
    DatabaseCredentials, AirtableCredentials, NotionCredentials,
    AsanaCredentials, TrelloCredentials, GitHubCredentials,
    SalesforceCredentials, CalendlyCredentials, DiscordCredentials,
    TeamsCredentials, GenericAPICredentials, GoogleCredentials,
    StripeCredentials, CREDENTIALS_MODEL_MAP,
    IntegrationTest
)
from app.middleware.auth import get_current_user
from app.services.integrations.jira_service import JiraService
from app.services.integrations.hubspot_service import HubSpotService
from app.services.integrations.email_service import EmailService
from app.services.integrations.credentials_encryption import credentials_encryption
from typing import Dict, Any

router = APIRouter()
logger = logging.getLogger(__name__)


def encrypt_credentials(credentials: dict, user_id: str) -> dict:
    """Encrypt sensitive credential data using the encryption service"""
    return credentials_encryption.encrypt_credentials(credentials, user_id)


def decrypt_credentials(credentials: dict, user_id: str) -> dict:
    """Decrypt credential data using the encryption service"""
    return credentials_encryption.decrypt_credentials(credentials, user_id)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_integration(
    integration_data: dict,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Create a new integration"""
    try:
        db = Database.get_db()

        # Validate integration type
        integration_type = integration_data.get("type")
        if not integration_type or integration_type not in [t.value for t in IntegrationType]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integration type"
            )

        # Validate credentials based on type
        credentials = integration_data.get("credentials", {})
        user_id = str(current_user["_id"])

        # Get the credential model for this integration type
        credential_model = CREDENTIALS_MODEL_MAP.get(IntegrationType(integration_type))

        if credential_model:
            try:
                validated_creds = credential_model(**credentials)
                credentials = validated_creds.dict()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {integration_type} credentials: {str(e)}"
                )
        else:
            # For types without a specific model, accept credentials as-is
            logger.info(f"No specific credential model for {integration_type}, using generic validation")

        # Encrypt credentials with user-specific salt
        encrypted_credentials = encrypt_credentials(credentials, user_id)

        # Prepare metadata with display info (non-sensitive)
        metadata = integration_data.get("metadata", {})
        if integration_type == IntegrationType.JIRA:
            metadata["base_url"] = credentials.get("base_url")
            metadata["email"] = credentials.get("email")
        elif integration_type == IntegrationType.HUBSPOT:
            metadata["portal_id"] = credentials.get("portal_id")
        elif integration_type == IntegrationType.EMAIL:
            metadata["smtp_host"] = credentials.get("smtp_host")
            metadata["from_email"] = credentials.get("from_email")

        # Create integration
        integration = Integration(
            user_id=str(current_user["_id"]),
            name=integration_data.get("name"),
            type=integration_type,
            credentials=encrypted_credentials,
            status=IntegrationStatus.TESTING,
            metadata=metadata
        )

        # Insert into database
        result = db.integrations.insert_one(integration.dict(by_alias=True, exclude={"id"}))
        integration_id = str(result.inserted_id)

        logger.info(f"Created integration {integration_id} for user {current_user['_id']}")

        return {
            "success": True,
            "integration_id": integration_id,
            "message": "Integration created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/")
async def get_integrations(
    type: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all integrations for current user"""
    try:
        db = Database.get_db()

        query = {"user_id": str(current_user["_id"])}
        if type:
            query["type"] = type

        integrations = list(db.integrations.find(query).sort("created_at", -1))

        # Remove sensitive credential data
        for integration in integrations:
            integration["_id"] = str(integration["_id"])
            # Mask credentials
            if "credentials" in integration:
                integration["credentials"] = {"masked": True}

        return {
            "success": True,
            "integrations": integrations,
            "count": len(integrations)
        }

    except Exception as e:
        logger.error(f"Error fetching integrations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{integration_id}")
async def get_integration(
    integration_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get a specific integration"""
    try:
        db = Database.get_db()

        # Convert string ID to ObjectId for MongoDB query
        try:
            obj_id = ObjectId(integration_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integration ID format"
            )

        integration = db.integrations.find_one({
            "_id": obj_id,
            "user_id": str(current_user["_id"])
        })

        if not integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found"
            )

        integration["_id"] = str(integration["_id"])
        # Mask credentials
        if "credentials" in integration:
            integration["credentials"] = {"masked": True}

        return {
            "success": True,
            "integration": integration
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{integration_id}")
async def update_integration(
    integration_id: str,
    update_data: dict,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Update an integration"""
    try:
        db = Database.get_db()

        # Convert string ID to ObjectId for MongoDB query
        try:
            obj_id = ObjectId(integration_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integration ID format"
            )

        # Check ownership
        existing = db.integrations.find_one({
            "_id": obj_id,
            "user_id": str(current_user["_id"])
        })

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found"
            )

        # Prepare update
        update_fields = {}

        if "name" in update_data:
            update_fields["name"] = update_data["name"]

        if "credentials" in update_data:
            # Validate and encrypt new credentials
            credentials = update_data["credentials"]
            integration_type = existing["type"]

            if integration_type == IntegrationType.JIRA:
                validated_creds = JiraCredentials(**credentials)
            elif integration_type == IntegrationType.HUBSPOT:
                validated_creds = HubSpotCredentials(**credentials)
            elif integration_type == IntegrationType.EMAIL:
                validated_creds = EmailCredentials(**credentials)

            update_fields["credentials"] = encrypt_credentials(validated_creds.dict())

        if "is_active" in update_data:
            update_fields["is_active"] = update_data["is_active"]

        if "metadata" in update_data:
            update_fields["metadata"] = update_data["metadata"]

        update_fields["updated_at"] = datetime.utcnow()

        # Update
        db.integrations.update_one(
            {"_id": obj_id},
            {"$set": update_fields}
        )

        logger.info(f"Updated integration {integration_id}")

        return {
            "success": True,
            "message": "Integration updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Delete an integration"""
    try:
        db = Database.get_db()

        # Convert string ID to ObjectId for MongoDB query
        try:
            obj_id = ObjectId(integration_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integration ID format"
            )

        result = db.integrations.delete_one({
            "_id": obj_id,
            "user_id": str(current_user["_id"])
        })

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found"
            )

        logger.info(f"Deleted integration {integration_id}")

        return {
            "success": True,
            "message": "Integration deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{integration_id}/test")
async def test_integration(
    integration_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Test an integration connection"""
    try:
        db = Database.get_db()

        # Convert string ID to ObjectId for MongoDB query
        try:
            obj_id = ObjectId(integration_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integration ID format"
            )

        integration_doc = db.integrations.find_one({
            "_id": obj_id,
            "user_id": str(current_user["_id"])
        })

        if not integration_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found"
            )

        # Decrypt credentials
        user_id = str(current_user["_id"])
        credentials = decrypt_credentials(integration_doc["credentials"], user_id)

        # Convert _id to string for Pydantic model
        integration_data = {**integration_doc, "credentials": credentials}
        integration_data["_id"] = str(integration_data["_id"])
        integration = Integration(**integration_data)

        # Test based on type
        test_result = None

        if integration.type == IntegrationType.JIRA:
            creds = JiraCredentials(**credentials)
            service = JiraService(creds)
            test_result = service.test_connection()

        elif integration.type == IntegrationType.HUBSPOT:
            creds = HubSpotCredentials(**credentials)
            service = HubSpotService(creds)
            test_result = service.test_connection()

        elif integration.type == IntegrationType.EMAIL:
            creds = EmailCredentials(**credentials)
            service = EmailService(creds)
            test_result = service.test_connection()

        else:
            # For integration types without specific test implementation,
            # mark as active (credentials saved successfully)
            test_result = {
                "success": True,
                "message": f"Credentials saved for {integration.type.value}. Connection test not available for this integration type."
            }

        # Update integration status
        new_status = IntegrationStatus.ACTIVE if test_result.get("success") else IntegrationStatus.ERROR

        db.integrations.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "status": new_status,
                    "last_tested_at": datetime.utcnow(),
                    "last_error": None if test_result.get("success") else test_result.get("message"),
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return {
            "success": test_result.get("success", False),
            "message": test_result.get("message", "Test completed"),
            "details": test_result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{integration_id}/logs")
async def get_integration_logs(
    integration_id: str,
    limit: int = 50,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get integration action logs"""
    try:
        db = Database.get_db()

        # Convert string ID to ObjectId for MongoDB query
        try:
            obj_id = ObjectId(integration_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integration ID format"
            )

        # Verify ownership
        integration = db.integrations.find_one({
            "_id": obj_id,
            "user_id": str(current_user["_id"])
        })

        if not integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found"
            )

        # Get logs
        logs = list(
            db.integration_logs.find({
                "integration_id": integration_id
            })
            .sort("created_at", -1)
            .limit(limit)
        )

        for log in logs:
            log["_id"] = str(log["_id"])

        return {
            "success": True,
            "logs": logs,
            "count": len(logs)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/types/available")
async def get_available_integration_types():
    """Get all available integration types with their configuration schemas"""

    # Define integration categories and their types
    integration_catalog = {
        "project_management": {
            "label": "Project Management",
            "icon": "clipboard",
            "integrations": [
                {
                    "type": "jira",
                    "name": "Jira",
                    "description": "Create and manage Jira issues",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/jira.svg",
                    "fields": [
                        {"name": "base_url", "label": "Jira URL", "type": "url", "required": True, "placeholder": "https://yourcompany.atlassian.net"},
                        {"name": "email", "label": "Email", "type": "email", "required": True, "placeholder": "your@email.com"},
                        {"name": "api_token", "label": "API Token", "type": "password", "required": True, "placeholder": "Your Jira API token", "help": "Get from https://id.atlassian.com/manage-profile/security/api-tokens"},
                        {"name": "default_project", "label": "Default Project", "type": "text", "required": False, "placeholder": "PROJECT-KEY"},
                    ]
                },
                {
                    "type": "asana",
                    "name": "Asana",
                    "description": "Create and manage Asana tasks",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/asana.svg",
                    "fields": [
                        {"name": "access_token", "label": "Personal Access Token", "type": "password", "required": True, "placeholder": "Your Asana PAT"},
                        {"name": "default_workspace", "label": "Default Workspace ID", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "trello",
                    "name": "Trello",
                    "description": "Create and manage Trello cards",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/trello.svg",
                    "fields": [
                        {"name": "api_key", "label": "API Key", "type": "text", "required": True},
                        {"name": "api_token", "label": "API Token", "type": "password", "required": True},
                        {"name": "default_board", "label": "Default Board ID", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "notion",
                    "name": "Notion",
                    "description": "Add pages to Notion databases",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/notion.svg",
                    "fields": [
                        {"name": "api_key", "label": "Integration Token", "type": "password", "required": True, "placeholder": "secret_..."},
                        {"name": "default_database_id", "label": "Default Database ID", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "github",
                    "name": "GitHub",
                    "description": "Create GitHub issues and manage repos",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/github.svg",
                    "fields": [
                        {"name": "access_token", "label": "Personal Access Token", "type": "password", "required": True},
                        {"name": "default_owner", "label": "Default Owner", "type": "text", "required": False},
                        {"name": "default_repo", "label": "Default Repo", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "linear",
                    "name": "Linear",
                    "description": "Create and manage Linear issues",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/linear.svg",
                    "fields": [
                        {"name": "api_key", "label": "API Key", "type": "password", "required": True},
                    ]
                },
            ]
        },
        "crm": {
            "label": "CRM",
            "icon": "users",
            "integrations": [
                {
                    "type": "hubspot",
                    "name": "HubSpot",
                    "description": "Manage HubSpot contacts, deals, and notes",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/hubspot.svg",
                    "fields": [
                        {"name": "access_token", "label": "Private App Access Token", "type": "password", "required": True},
                        {"name": "portal_id", "label": "Portal ID", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "salesforce",
                    "name": "Salesforce",
                    "description": "Manage Salesforce records",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/salesforce.svg",
                    "fields": [
                        {"name": "instance_url", "label": "Instance URL", "type": "url", "required": True},
                        {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
                        {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True},
                        {"name": "refresh_token", "label": "Refresh Token", "type": "password", "required": True},
                    ]
                },
                {
                    "type": "pipedrive",
                    "name": "Pipedrive",
                    "description": "Manage Pipedrive deals and contacts",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/pipedrive.svg",
                    "fields": [
                        {"name": "api_key", "label": "API Token", "type": "password", "required": True},
                    ]
                },
            ]
        },
        "communication": {
            "label": "Communication",
            "icon": "message-circle",
            "integrations": [
                {
                    "type": "email",
                    "name": "Email (SMTP)",
                    "description": "Send emails via SMTP",
                    "icon": "mail",
                    "fields": [
                        {"name": "smtp_host", "label": "SMTP Host", "type": "text", "required": True, "placeholder": "smtp.gmail.com"},
                        {"name": "smtp_port", "label": "SMTP Port", "type": "number", "required": True, "default": 587},
                        {"name": "smtp_username", "label": "Username", "type": "text", "required": True},
                        {"name": "smtp_password", "label": "Password", "type": "password", "required": True, "help": "For Gmail, use App Password"},
                        {"name": "from_email", "label": "From Email", "type": "email", "required": True},
                        {"name": "from_name", "label": "From Name", "type": "text", "required": False},
                        {"name": "use_tls", "label": "Use TLS", "type": "boolean", "required": False, "default": True},
                    ]
                },
                {
                    "type": "sendgrid",
                    "name": "SendGrid",
                    "description": "Send emails via SendGrid",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/sendgrid.svg",
                    "fields": [
                        {"name": "api_key", "label": "API Key", "type": "password", "required": True},
                        {"name": "from_email", "label": "From Email", "type": "email", "required": True},
                        {"name": "from_name", "label": "From Name", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "slack",
                    "name": "Slack",
                    "description": "Send Slack messages",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/slack.svg",
                    "fields": [
                        {"name": "webhook_url", "label": "Webhook URL", "type": "url", "required": True, "placeholder": "https://hooks.slack.com/services/..."},
                        {"name": "default_channel", "label": "Default Channel", "type": "text", "required": False, "placeholder": "#general"},
                    ]
                },
                {
                    "type": "discord",
                    "name": "Discord",
                    "description": "Send Discord messages",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/discord.svg",
                    "fields": [
                        {"name": "webhook_url", "label": "Webhook URL", "type": "url", "required": True},
                    ]
                },
                {
                    "type": "teams",
                    "name": "Microsoft Teams",
                    "description": "Send Teams messages",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/microsoftteams.svg",
                    "fields": [
                        {"name": "webhook_url", "label": "Webhook URL", "type": "url", "required": True},
                    ]
                },
                {
                    "type": "twilio",
                    "name": "Twilio",
                    "description": "Send SMS via Twilio",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/twilio.svg",
                    "fields": [
                        {"name": "account_sid", "label": "Account SID", "type": "text", "required": True},
                        {"name": "auth_token", "label": "Auth Token", "type": "password", "required": True},
                        {"name": "phone_number", "label": "Twilio Phone Number", "type": "text", "required": False, "placeholder": "+1234567890"},
                    ]
                },
            ]
        },
        "calendar": {
            "label": "Calendar",
            "icon": "calendar",
            "integrations": [
                {
                    "type": "google_calendar",
                    "name": "Google Calendar",
                    "description": "Create and manage calendar events",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/googlecalendar.svg",
                    "auth_type": "oauth2",
                    "fields": [
                        {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
                        {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True},
                        {"name": "refresh_token", "label": "Refresh Token", "type": "password", "required": True},
                    ]
                },
                {
                    "type": "calendly",
                    "name": "Calendly",
                    "description": "Book meetings via Calendly",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/calendly.svg",
                    "fields": [
                        {"name": "api_key", "label": "Personal Access Token", "type": "password", "required": True},
                    ]
                },
            ]
        },
        "database": {
            "label": "Databases",
            "icon": "database",
            "integrations": [
                {
                    "type": "postgresql",
                    "name": "PostgreSQL",
                    "description": "Connect to PostgreSQL database",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/postgresql.svg",
                    "fields": [
                        {"name": "host", "label": "Host", "type": "text", "required": True},
                        {"name": "port", "label": "Port", "type": "number", "required": True, "default": 5432},
                        {"name": "database", "label": "Database", "type": "text", "required": True},
                        {"name": "username", "label": "Username", "type": "text", "required": True},
                        {"name": "password", "label": "Password", "type": "password", "required": True},
                        {"name": "ssl", "label": "Use SSL", "type": "boolean", "required": False, "default": False},
                    ]
                },
                {
                    "type": "mysql",
                    "name": "MySQL",
                    "description": "Connect to MySQL database",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/mysql.svg",
                    "fields": [
                        {"name": "host", "label": "Host", "type": "text", "required": True},
                        {"name": "port", "label": "Port", "type": "number", "required": True, "default": 3306},
                        {"name": "database", "label": "Database", "type": "text", "required": True},
                        {"name": "username", "label": "Username", "type": "text", "required": True},
                        {"name": "password", "label": "Password", "type": "password", "required": True},
                    ]
                },
                {
                    "type": "airtable",
                    "name": "Airtable",
                    "description": "Connect to Airtable bases",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/airtable.svg",
                    "fields": [
                        {"name": "api_key", "label": "API Key / PAT", "type": "password", "required": True},
                        {"name": "base_id", "label": "Default Base ID", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "google_sheets",
                    "name": "Google Sheets",
                    "description": "Read/write Google Sheets",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/googlesheets.svg",
                    "auth_type": "oauth2",
                    "fields": [
                        {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
                        {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True},
                        {"name": "refresh_token", "label": "Refresh Token", "type": "password", "required": True},
                    ]
                },
                {
                    "type": "supabase",
                    "name": "Supabase",
                    "description": "Connect to Supabase",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/supabase.svg",
                    "fields": [
                        {"name": "url", "label": "Project URL", "type": "url", "required": True},
                        {"name": "api_key", "label": "API Key", "type": "password", "required": True},
                    ]
                },
            ]
        },
        "ai": {
            "label": "AI & ML",
            "icon": "cpu",
            "integrations": [
                {
                    "type": "openai",
                    "name": "OpenAI",
                    "description": "Use GPT models for text generation",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/openai.svg",
                    "fields": [
                        {"name": "api_key", "label": "API Key", "type": "password", "required": True, "placeholder": "sk-..."},
                        {"name": "organization_id", "label": "Organization ID", "type": "text", "required": False},
                        {"name": "default_model", "label": "Default Model", "type": "select", "required": False, "options": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"], "default": "gpt-4o-mini"},
                    ]
                },
                {
                    "type": "anthropic",
                    "name": "Anthropic (Claude)",
                    "description": "Use Claude models for text generation",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/anthropic.svg",
                    "fields": [
                        {"name": "api_key", "label": "API Key", "type": "password", "required": True},
                        {"name": "default_model", "label": "Default Model", "type": "select", "required": False, "options": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"], "default": "claude-3-5-sonnet-20241022"},
                    ]
                },
            ]
        },
        "storage": {
            "label": "Storage",
            "icon": "hard-drive",
            "integrations": [
                {
                    "type": "aws_s3",
                    "name": "AWS S3",
                    "description": "Store files in S3",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/amazons3.svg",
                    "fields": [
                        {"name": "access_key_id", "label": "Access Key ID", "type": "text", "required": True},
                        {"name": "secret_access_key", "label": "Secret Access Key", "type": "password", "required": True},
                        {"name": "region", "label": "Region", "type": "text", "required": True, "default": "us-east-1"},
                        {"name": "bucket", "label": "Default Bucket", "type": "text", "required": False},
                    ]
                },
                {
                    "type": "google_drive",
                    "name": "Google Drive",
                    "description": "Store files in Google Drive",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/googledrive.svg",
                    "auth_type": "oauth2",
                    "fields": [
                        {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
                        {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True},
                        {"name": "refresh_token", "label": "Refresh Token", "type": "password", "required": True},
                    ]
                },
            ]
        },
        "payment": {
            "label": "Payment",
            "icon": "credit-card",
            "integrations": [
                {
                    "type": "stripe",
                    "name": "Stripe",
                    "description": "Process payments with Stripe",
                    "icon": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/stripe.svg",
                    "fields": [
                        {"name": "secret_key", "label": "Secret Key", "type": "password", "required": True, "placeholder": "sk_..."},
                        {"name": "webhook_secret", "label": "Webhook Secret", "type": "password", "required": False},
                    ]
                },
            ]
        },
        "generic": {
            "label": "Generic",
            "icon": "link",
            "integrations": [
                {
                    "type": "webhook",
                    "name": "Webhook",
                    "description": "Call any HTTP endpoint",
                    "icon": "webhook",
                    "fields": [
                        {"name": "url", "label": "Webhook URL", "type": "url", "required": True},
                        {"name": "method", "label": "HTTP Method", "type": "select", "required": False, "options": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "POST"},
                        {"name": "auth_type", "label": "Auth Type", "type": "select", "required": False, "options": ["none", "bearer", "basic", "api_key"]},
                        {"name": "auth_token", "label": "Auth Token/Key", "type": "password", "required": False},
                    ]
                },
                {
                    "type": "api_key",
                    "name": "Generic API",
                    "description": "Connect to any API with an API key",
                    "icon": "key",
                    "fields": [
                        {"name": "api_key", "label": "API Key", "type": "password", "required": True},
                        {"name": "base_url", "label": "Base URL", "type": "url", "required": False},
                    ]
                },
            ]
        }
    }

    return {
        "success": True,
        "categories": integration_catalog
    }
