"""
WhatsApp Integration Models
Pydantic models for WhatsApp Business API integration
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
import re


class WhatsAppCredentialCreate(BaseModel):
    """Model for creating new WhatsApp Business credentials (Railway API)"""
    label: str = Field(..., min_length=1, max_length=100, description="Friendly name for this WhatsApp account")
    api_key: str = Field(..., description="x-api-key for Railway WhatsApp API")
    bearer_token: str = Field(..., description="Bearer token for Railway WhatsApp API")
    api_url: Optional[str] = Field(
        default="https://whatsapp-api-backend-production.up.railway.app",
        description="Railway API base URL (optional, has default)"
    )

    @validator('label')
    def validate_label(cls, v):
        if not v.strip():
            raise ValueError('Label cannot be empty')
        return v.strip()

    @validator('api_key')
    def validate_api_key(cls, v):
        if len(v) < 10:
            raise ValueError('Invalid API key format')
        return v

    @validator('bearer_token')
    def validate_bearer_token(cls, v):
        if len(v) < 10:
            raise ValueError('Invalid bearer token format')
        return v


class WhatsAppCredentialUpdate(BaseModel):
    """Model for updating WhatsApp credentials"""
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    api_key: Optional[str] = None
    bearer_token: Optional[str] = None
    api_url: Optional[str] = None


class WhatsAppCredentialResponse(BaseModel):
    """Model for WhatsApp credential response"""
    id: str
    user_id: str
    label: str
    last_four: str
    api_url_masked: str
    status: Literal["active", "disconnected", "error"]
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "user_id": "507f191e810c19729de860ea",
                "label": "My Business WhatsApp",
                "last_four": "b172",
                "api_url_masked": "railway.app",
                "status": "active",
                "created_at": "2025-01-10T10:30:00Z"
            }
        }


class WhatsAppMessageTemplate(BaseModel):
    """Model for WhatsApp message template"""
    name: str
    language: str = "en_US"
    components: List[Dict[str, Any]] = []


class WhatsAppMessageSend(BaseModel):
    """Model for sending WhatsApp message"""
    credential_id: str = Field(..., description="WhatsApp credential ID to use")
    to: str = Field(..., description="Recipient phone number with country code")
    message_type: Literal["text", "template"] = Field(default="text")
    text: Optional[str] = Field(None, description="Text message content (for type=text)")
    template_name: Optional[str] = Field(None, description="Template name (for type=template)")
    template_params: Optional[List[str]] = Field(default=[], description="Template parameters")

    @validator('to')
    def validate_phone(cls, v):
        # Remove spaces and check format
        phone = v.replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            raise ValueError('Phone number must start with + and country code')
        if not re.match(r'^\+\d{10,15}$', phone):
            raise ValueError('Invalid phone number format')
        return phone

    @validator('text')
    def validate_text_message(cls, v, values):
        if values.get('message_type') == 'text' and not v:
            raise ValueError('Text is required for text message type')
        return v

    @validator('template_name')
    def validate_template_message(cls, v, values):
        if values.get('message_type') == 'template' and not v:
            raise ValueError('Template name is required for template message type')
        return v


class WhatsAppMessageBulkSend(BaseModel):
    """Model for bulk sending WhatsApp messages"""
    credential_id: str
    recipients: List[str] = Field(..., min_items=1, max_items=1000)
    message_type: Literal["text", "template"] = Field(default="template")
    text: Optional[str] = None
    template_name: Optional[str] = None
    template_params: Optional[List[str]] = []


class WhatsAppMessageResponse(BaseModel):
    """Model for WhatsApp message response"""
    id: str
    message_id: Optional[str] = None
    to: str
    status: Literal["queued", "sent", "delivered", "read", "failed"]
    message_type: str
    sent_at: str
    error: Optional[str] = None


class WhatsAppWebhookVerification(BaseModel):
    """Model for webhook verification"""
    mode: str = Field(..., alias="hub.mode")
    token: str = Field(..., alias="hub.verify_token")
    challenge: str = Field(..., alias="hub.challenge")

    class Config:
        populate_by_name = True


class WhatsAppWebhookMessage(BaseModel):
    """Model for incoming webhook message"""
    object: str
    entry: List[Dict[str, Any]]


class WhatsAppStats(BaseModel):
    """Model for WhatsApp statistics"""
    total_messages: int
    sent: int
    delivered: int
    read: int
    failed: int
    credentials_count: int
    active_credentials: int


class WhatsAppTemplateResponse(BaseModel):
    """Model for WhatsApp template response"""
    id: str
    name: str
    status: str
    category: str
    language: str
    components: List[Dict[str, Any]]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "template_123",
                "name": "user_call_confirm_v1",
                "status": "APPROVED",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {
                        "type": "BODY",
                        "text": "Hello! {{1}} wants to confirm your call."
                    }
                ]
            }
        }


class WhatsAppConnectionTest(BaseModel):
    """Model for testing WhatsApp connection (Railway API)"""
    api_key: str
    bearer_token: str
    api_url: Optional[str] = "https://whatsapp-api-backend-production.up.railway.app"


class WhatsAppConnectionTestResponse(BaseModel):
    """Response for connection test"""
    success: bool
    message: str
    templates_count: Optional[int] = None
    api_accessible: Optional[bool] = None
