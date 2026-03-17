"""
Integration Model
Stores user integration configurations for external services (Jira, HubSpot, Email, etc.)
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class IntegrationType(str, Enum):
    """Supported integration types"""
    # Project Management
    JIRA = "jira"
    ASANA = "asana"
    TRELLO = "trello"
    MONDAY = "monday"
    NOTION = "notion"
    LINEAR = "linear"
    CLICKUP = "clickup"
    GITHUB = "github"
    GITLAB = "gitlab"

    # CRM
    HUBSPOT = "hubspot"
    SALESFORCE = "salesforce"
    PIPEDRIVE = "pipedrive"
    ZOHO = "zoho"
    FRESHSALES = "freshsales"

    # Communication
    EMAIL = "email"
    GMAIL = "gmail"
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    TWILIO = "twilio"
    SENDGRID = "sendgrid"

    # Calendar
    GOOGLE_CALENDAR = "google_calendar"
    OUTLOOK_CALENDAR = "outlook_calendar"
    CALENDLY = "calendly"
    CALCOM = "calcom"

    # Database
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    SUPABASE = "supabase"
    FIREBASE = "firebase"
    AIRTABLE = "airtable"
    GOOGLE_SHEETS = "google_sheets"

    # AI
    OPENAI = "openai"
    ANTHROPIC = "anthropic"

    # Storage
    AWS_S3 = "aws_s3"
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"

    # Payment
    STRIPE = "stripe"
    PAYPAL = "paypal"

    # Generic
    WEBHOOK = "webhook"
    OAUTH2 = "oauth2"
    API_KEY = "api_key"


class IntegrationStatus(str, Enum):
    """Integration connection status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    TESTING = "testing"


class JiraCredentials(BaseModel):
    """Jira-specific credentials"""
    base_url: str = Field(..., description="Jira instance URL (e.g., https://yourcompany.atlassian.net)")
    email: str = Field(..., description="Jira user email")
    api_token: str = Field(..., description="Jira API token")
    default_project: Optional[str] = Field(None, description="Default project key")
    default_issue_type: Optional[str] = Field("Task", description="Default issue type")

    def __init__(self, **data):
        # Strip whitespace from credentials to avoid auth issues
        if 'base_url' in data and data['base_url']:
            data['base_url'] = data['base_url'].strip()
        if 'email' in data and data['email']:
            data['email'] = data['email'].strip()
        if 'api_token' in data and data['api_token']:
            data['api_token'] = data['api_token'].strip()
        super().__init__(**data)


class HubSpotCredentials(BaseModel):
    """HubSpot-specific credentials"""
    access_token: str = Field(..., description="HubSpot private app access token")
    portal_id: Optional[str] = Field(None, description="HubSpot portal ID")


class EmailCredentials(BaseModel):
    """Email SMTP credentials"""
    smtp_host: str = Field(..., description="SMTP server host")
    smtp_port: int = Field(587, description="SMTP server port")
    smtp_username: str = Field(..., description="SMTP username")
    smtp_password: str = Field(..., description="SMTP password")
    from_email: str = Field(..., description="From email address")
    from_name: Optional[str] = Field(None, description="From display name")
    use_tls: bool = Field(True, description="Use TLS encryption")


class SlackCredentials(BaseModel):
    """Slack webhook credentials"""
    webhook_url: str = Field(..., description="Slack webhook URL")
    default_channel: Optional[str] = Field(None, description="Default channel")


class WebhookCredentials(BaseModel):
    """Generic webhook credentials"""
    url: str = Field(..., description="Webhook endpoint URL")
    method: str = Field("POST", description="HTTP method")
    headers: Optional[Dict[str, str]] = Field(None, description="Custom headers")
    auth_type: Optional[str] = Field(None, description="Authentication type (bearer, basic, etc.)")
    auth_token: Optional[str] = Field(None, description="Authentication token")


class GoogleCredentials(BaseModel):
    """Google OAuth credentials (Calendar, Drive, Sheets)"""
    client_id: str = Field(..., description="Google OAuth client ID")
    client_secret: str = Field(..., description="Google OAuth client secret")
    refresh_token: str = Field(..., description="OAuth refresh token")
    access_token: Optional[str] = Field(None, description="Current access token")
    token_expiry: Optional[datetime] = Field(None, description="Token expiry time")


class OpenAICredentials(BaseModel):
    """OpenAI API credentials"""
    api_key: str = Field(..., description="OpenAI API key")
    organization_id: Optional[str] = Field(None, description="Organization ID")
    default_model: Optional[str] = Field("gpt-4o-mini", description="Default model")


class AnthropicCredentials(BaseModel):
    """Anthropic API credentials"""
    api_key: str = Field(..., description="Anthropic API key")
    default_model: Optional[str] = Field("claude-3-5-sonnet-20241022", description="Default model")


class TwilioCredentials(BaseModel):
    """Twilio credentials"""
    account_sid: str = Field(..., description="Twilio Account SID")
    auth_token: str = Field(..., description="Twilio Auth Token")
    phone_number: Optional[str] = Field(None, description="Default Twilio phone number")


class SendGridCredentials(BaseModel):
    """SendGrid API credentials"""
    api_key: str = Field(..., description="SendGrid API key")
    from_email: str = Field(..., description="Default sender email")
    from_name: Optional[str] = Field(None, description="Default sender name")


class StripeCredentials(BaseModel):
    """Stripe API credentials"""
    secret_key: str = Field(..., description="Stripe secret key")
    publishable_key: Optional[str] = Field(None, description="Stripe publishable key")
    webhook_secret: Optional[str] = Field(None, description="Webhook signing secret")


class DatabaseCredentials(BaseModel):
    """Generic database credentials"""
    host: str = Field(..., description="Database host")
    port: int = Field(..., description="Database port")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Database username")
    password: str = Field(..., description="Database password")
    ssl: bool = Field(False, description="Use SSL connection")
    connection_string: Optional[str] = Field(None, description="Full connection string (overrides other fields)")


class AirtableCredentials(BaseModel):
    """Airtable credentials"""
    api_key: str = Field(..., description="Airtable API key or Personal Access Token")
    base_id: Optional[str] = Field(None, description="Default base ID")


class NotionCredentials(BaseModel):
    """Notion credentials"""
    api_key: str = Field(..., description="Notion integration token")
    default_database_id: Optional[str] = Field(None, description="Default database ID")


class AsanaCredentials(BaseModel):
    """Asana credentials"""
    access_token: str = Field(..., description="Asana personal access token")
    default_workspace: Optional[str] = Field(None, description="Default workspace ID")
    default_project: Optional[str] = Field(None, description="Default project ID")


class TrelloCredentials(BaseModel):
    """Trello credentials"""
    api_key: str = Field(..., description="Trello API key")
    api_token: str = Field(..., description="Trello API token")
    default_board: Optional[str] = Field(None, description="Default board ID")


class GitHubCredentials(BaseModel):
    """GitHub credentials"""
    access_token: str = Field(..., description="GitHub personal access token")
    default_owner: Optional[str] = Field(None, description="Default repository owner")
    default_repo: Optional[str] = Field(None, description="Default repository name")


class SalesforceCredentials(BaseModel):
    """Salesforce credentials"""
    instance_url: str = Field(..., description="Salesforce instance URL")
    client_id: str = Field(..., description="Connected App client ID")
    client_secret: str = Field(..., description="Connected App client secret")
    refresh_token: str = Field(..., description="OAuth refresh token")
    access_token: Optional[str] = Field(None, description="Current access token")


class CalendlyCredentials(BaseModel):
    """Calendly credentials"""
    api_key: str = Field(..., description="Calendly API key")
    user_uri: Optional[str] = Field(None, description="Calendly user URI")


class DiscordCredentials(BaseModel):
    """Discord webhook credentials"""
    webhook_url: str = Field(..., description="Discord webhook URL")


class TeamsCredentials(BaseModel):
    """Microsoft Teams webhook credentials"""
    webhook_url: str = Field(..., description="Teams incoming webhook URL")


class GenericAPICredentials(BaseModel):
    """Generic API key credentials"""
    api_key: str = Field(..., description="API key")
    api_secret: Optional[str] = Field(None, description="API secret (if required)")
    base_url: Optional[str] = Field(None, description="API base URL")
    headers: Optional[Dict[str, str]] = Field(None, description="Additional headers")


# Mapping of integration types to their credential models
CREDENTIALS_MODEL_MAP = {
    IntegrationType.JIRA: JiraCredentials,
    IntegrationType.HUBSPOT: HubSpotCredentials,
    IntegrationType.EMAIL: EmailCredentials,
    IntegrationType.SLACK: SlackCredentials,
    IntegrationType.WEBHOOK: WebhookCredentials,
    IntegrationType.GOOGLE_CALENDAR: GoogleCredentials,
    IntegrationType.GOOGLE_DRIVE: GoogleCredentials,
    IntegrationType.GOOGLE_SHEETS: GoogleCredentials,
    IntegrationType.OPENAI: OpenAICredentials,
    IntegrationType.ANTHROPIC: AnthropicCredentials,
    IntegrationType.TWILIO: TwilioCredentials,
    IntegrationType.SENDGRID: SendGridCredentials,
    IntegrationType.STRIPE: StripeCredentials,
    IntegrationType.POSTGRESQL: DatabaseCredentials,
    IntegrationType.MYSQL: DatabaseCredentials,
    IntegrationType.MONGODB: DatabaseCredentials,
    IntegrationType.AIRTABLE: AirtableCredentials,
    IntegrationType.NOTION: NotionCredentials,
    IntegrationType.ASANA: AsanaCredentials,
    IntegrationType.TRELLO: TrelloCredentials,
    IntegrationType.GITHUB: GitHubCredentials,
    IntegrationType.GITLAB: GitHubCredentials,
    IntegrationType.SALESFORCE: SalesforceCredentials,
    IntegrationType.CALENDLY: CalendlyCredentials,
    IntegrationType.DISCORD: DiscordCredentials,
    IntegrationType.TEAMS: TeamsCredentials,
    IntegrationType.API_KEY: GenericAPICredentials,
}


class Integration(BaseModel):
    """User integration configuration"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(..., description="User ID who owns this integration")
    name: str = Field(..., description="Integration friendly name")
    type: IntegrationType = Field(..., description="Integration type")
    credentials: Dict[str, Any] = Field(..., description="Encrypted credentials (type-specific)")
    status: IntegrationStatus = Field(IntegrationStatus.ACTIVE, description="Integration status")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    last_tested_at: Optional[datetime] = Field(None, description="Last connection test timestamp")
    last_error: Optional[str] = Field(None, description="Last error message")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(True, description="Whether this integration is active")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IntegrationTest(BaseModel):
    """Integration connection test result"""
    integration_id: str
    success: bool
    message: str
    tested_at: datetime = Field(default_factory=datetime.utcnow)
    response_time_ms: Optional[float] = None
    error_details: Optional[Dict[str, Any]] = None


class IntegrationLog(BaseModel):
    """Log entry for integration actions"""
    id: Optional[str] = Field(None, alias="_id")
    integration_id: str
    workflow_execution_id: Optional[str] = Field(None, description="Related workflow execution")
    action: str = Field(..., description="Action performed (e.g., 'create_ticket', 'send_email')")
    status: str = Field(..., description="Success, failure, or error")
    request_data: Optional[Dict[str, Any]] = Field(None, description="Request payload")
    response_data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: Optional[float] = Field(None, description="Action duration in milliseconds")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
