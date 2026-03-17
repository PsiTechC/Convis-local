from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class PhoneNumberCapabilities(BaseModel):
    voice: bool = True
    sms: bool = True
    mms: bool = False


class ProviderCredentials(BaseModel):
    provider: str = Field(..., description="Provider name (twilio)")
    # Twilio/traditional providers
    account_sid: Optional[str] = Field(None, description="Provider account SID (Twilio)")
    auth_token: Optional[str] = Field(None, description="Provider auth token (Twilio)")
    user_id: str = Field(..., description="User ID")


class PhoneNumberResponse(BaseModel):
    id: str
    phone_number: str
    provider: str
    friendly_name: Optional[str] = None
    capabilities: PhoneNumberCapabilities
    status: str
    created_at: str
    assigned_assistant_id: Optional[str] = None
    assigned_assistant_name: Optional[str] = None
    webhook_url: Optional[str] = None


class PhoneNumberListResponse(BaseModel):
    phone_numbers: List[PhoneNumberResponse]
    total: int


class CallLogResponse(BaseModel):
    """Comprehensive call log with all Twilio call information"""
    # Basic Info
    id: str = Field(..., alias="sid", description="Twilio Call SID")
    from_number: str = Field(..., alias="from", description="Caller's phone number")
    to: str = Field(..., description="Recipient's phone number")
    direction: str = Field(..., description="'inbound', 'outbound-api', 'outbound-dial'")

    # Status & Timing
    status: str = Field(..., description="Call status: queued, ringing, in-progress, completed, busy, failed, no-answer, canceled")
    duration: Optional[int] = Field(None, description="Call duration in seconds (null if not completed)")
    start_time: Optional[str] = Field(None, description="When call started")
    end_time: Optional[str] = Field(None, description="When call ended")
    date_created: str = Field(..., description="When call was created")
    date_updated: Optional[str] = Field(None, description="Last update time")

    # Call Quality & Details
    answered_by: Optional[str] = Field(None, description="Who answered: human, machine, fax, unknown")
    caller_name: Optional[str] = Field(None, description="Caller ID name")
    forwarded_from: Optional[str] = Field(None, description="Original number if forwarded")
    parent_call_sid: Optional[str] = Field(None, description="Parent call SID if this is a child call")

    # Pricing & Cost
    price: Optional[str] = Field(None, description="Call cost (negative for charges)")
    price_unit: Optional[str] = Field(None, description="Currency (USD, EUR, etc.)")

    # Recording & Transcription
    recording_url: Optional[str] = Field(None, description="Recording URL if available")
    transcription_text: Optional[str] = Field(None, description="Call transcription if available")
    transcript: Optional[str] = Field(None, description="AI-generated call transcript")
    summary: Optional[str] = Field(None, description="AI-generated call summary")
    sentiment: Optional[str] = Field(None, description="Call sentiment: positive, neutral, negative")
    sentiment_score: Optional[float] = Field(None, description="Sentiment score from -1.0 to 1.0")

    # AI Assistant Info (Custom)
    assistant_id: Optional[str] = Field(None, description="AI assistant that handled the call")
    assistant_name: Optional[str] = Field(None, description="AI assistant name")

    # Queue Info
    queue_time: Optional[str] = Field(None, description="Time spent in queue")

    # Voice Provider Configuration (Custom)
    asr_provider: Optional[str] = Field(None, description="Speech-to-text provider used")
    asr_model: Optional[str] = Field(None, description="ASR model used")
    tts_provider: Optional[str] = Field(None, description="Text-to-speech provider used")
    tts_model: Optional[str] = Field(None, description="TTS model used")
    llm_provider: Optional[str] = Field(None, description="LLM provider used")
    llm_model: Optional[str] = Field(None, description="LLM model used")

    # Calculated Cost Fields
    cost_total: Optional[float] = Field(None, description="Total call cost including API + Twilio")
    cost_api: Optional[float] = Field(None, description="API costs (ASR + LLM + TTS or Realtime API)")
    cost_twilio: Optional[float] = Field(None, description="Twilio costs (calling + recording)")
    cost_currency: Optional[str] = Field(None, description="Currency for costs (USD or INR)")
    cost_calculated: Optional[bool] = Field(None, description="Whether cost has been calculated")
    is_realtime_api: Optional[bool] = Field(None, description="Whether OpenAI Realtime API was used")

    # Customer Data (extracted from conversation)
    customer_data: Optional[Dict[str, str]] = Field(None, description="Customer information extracted from call (name, email, location, appointment)")

    # Structured Conversation Log with timestamps
    conversation_log: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Structured conversation log with timestamps. Each entry: {role, text, timestamp, elapsed, is_interrupted, text_heard}"
    )

    class Config:
        populate_by_name = True
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "CA1234567890abcdef1234567890abcdef",
                "from_number": "+11234567890",
                "to": "+10987654321",
                "direction": "inbound",
                "status": "completed",
                "duration": 120,
                "start_time": "2025-10-14T12:00:00Z",
                "end_time": "2025-10-14T12:02:00Z",
                "date_created": "2025-10-14T11:59:55Z",
                "answered_by": "human",
                "price": "-0.0130",
                "price_unit": "USD",
                "assistant_id": "507f1f77bcf86cd799439011",
                "assistant_name": "Customer Support Bot"
            }
        }


class CallLogListResponse(BaseModel):
    call_logs: List[CallLogResponse]
    total: int


class ConnectProviderResponse(BaseModel):
    message: str
    phone_numbers: List[PhoneNumberResponse]
    provider: str


class AssignAssistantRequest(BaseModel):
    phone_number_id: str = Field(..., description="Phone number ID")
    assistant_id: str = Field(..., description="AI assistant ID to assign")


class AssignAssistantResponse(BaseModel):
    message: str
    phone_number: PhoneNumberResponse
    webhook_configured: bool = False


class ProviderConnectionStatus(BaseModel):
    provider: str
    is_connected: bool
    account_sid: Optional[str] = None
    connected_at: Optional[str] = None


class ProviderConnectionResponse(BaseModel):
    message: str
    connections: List[ProviderConnectionStatus]
