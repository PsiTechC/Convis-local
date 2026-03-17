from datetime import datetime
from typing import List, Optional, Dict, Any, Literal

from pydantic import BaseModel, Field, validator


class WorkingWindow(BaseModel):
    timezone: str = Field(..., description="IANA timezone, e.g. America/New_York")
    start: str = Field(..., description="Start time in HH:MM (24h) format")
    end: str = Field(..., description="End time in HH:MM (24h) format")
    days: List[int] = Field(..., description="List of weekdays allowed (0=Mon .. 6=Sun)")

    @validator("start", "end")
    def validate_time(cls, value: str) -> str:
        if len(value) != 5 or value[2] != ":":
            raise ValueError("Time must be HH:MM")
        hour, minute = value.split(":")
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError("Time must contain digits")
        h, m = int(hour), int(minute)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Time out of range")
        return value

    @validator("days")
    def validate_days(cls, value: List[int]) -> List[int]:
        if not value:
            raise ValueError("At least one day must be selected")
        for day in value:
            if day < 0 or day > 6:
                raise ValueError("Day values must be between 0 and 6")
        return value


class RetryPolicy(BaseModel):
    max_attempts: int = Field(3, ge=1, le=10)
    retry_after_minutes: List[int] = Field(default_factory=lambda: [15, 60, 1440])


class AttemptBackoff(BaseModel):
    """
    Defines how retries should be scheduled.

    Supported formats:
        {"type": "fixed", "seconds": 60}
        {"type": "exponential", "initial": 60, "base": 2}
        {"type": "mixed", "schedule": ["immediate", "+300s", "next_day_start"]}
    """

    type: Literal["fixed", "exponential", "mixed", "daily"] = "mixed"
    seconds: Optional[int] = Field(
        default=60,
        description="Used for fixed/daily policies; number of seconds before retry"
    )
    initial: Optional[int] = Field(
        default=120,
        description="Initial delay (seconds) for exponential policies"
    )
    base: Optional[int] = Field(
        default=2,
        description="Base multiplier for exponential policies"
    )
    schedule: List[str] = Field(
        default_factory=lambda: ["immediate", "+300s", "next_day_start"],
        description="Mixed schedule tokens"
    )

    @classmethod
    def default(cls) -> "AttemptBackoff":
        return cls()

    @validator("schedule")
    def validate_tokens(cls, tokens: List[str]) -> List[str]:
        seen = []
        for token in tokens:
            if token not in {"immediate", "next_day_start"} and not token.startswith("+"):
                raise ValueError(
                    f"Invalid schedule token '{token}'. "
                    "Use 'immediate', 'next_day_start', or expressions such as '+300s' / '+5m'."
                )
            seen.append(token)
        return seen


class Pacing(BaseModel):
    calls_per_minute: int = Field(1, ge=1, le=30)
    max_concurrent: int = Field(1, ge=1, le=10)


class CampaignDatabaseConfig(BaseModel):
    enabled: bool = False
    type: str = "postgresql"
    host: str = ""
    port: str = "5432"
    database: str = ""
    username: str = ""
    password: str = ""
    table_name: str = ""
    search_columns: List[str] = Field(default_factory=list)


class CampaignBase(BaseModel):
    name: str
    country: str = Field(..., description="ISO country code, e.g. US")
    working_window: WorkingWindow
    caller_id: str = Field(..., description="Phone number (E.164)")
    assistant_id: Optional[str] = Field(None, description="Assigned AI assistant ID")
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    pacing: Pacing = Field(default_factory=Pacing)
    start_at: Optional[datetime] = None
    stop_at: Optional[datetime] = None
    calendar_enabled: bool = False
    calendar_account_id: Optional[str] = Field(None, description="ID of the calendar account to use for booking")
    system_prompt_override: Optional[str] = None
    database_config: Optional[CampaignDatabaseConfig] = None
    lines: int = Field(1, ge=1, le=20, description="Max simultaneous lines for the campaign")
    attempts_per_number: int = Field(3, ge=1, le=10)
    attempt_backoff: AttemptBackoff = Field(default_factory=AttemptBackoff.default)
    priority: str = Field(default="standard", description="standard|fallback-first|new-first")


class CampaignCreate(CampaignBase):
    user_id: str = Field(..., description="User ID / tenant ID")


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    caller_id: Optional[str] = None
    assistant_id: Optional[str] = None
    working_window: Optional[WorkingWindow] = None
    retry_policy: Optional[RetryPolicy] = None
    pacing: Optional[Pacing] = None
    start_at: Optional[datetime] = None
    stop_at: Optional[datetime] = None
    calendar_enabled: Optional[bool] = None
    calendar_account_id: Optional[str] = None
    system_prompt_override: Optional[str] = None
    database_config: Optional[CampaignDatabaseConfig] = None


class CampaignResponse(CampaignBase):
    id: str = Field(..., alias="_id")
    user_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    next_index: int = 0
    stats: Optional[Dict[str, Any]] = None
    calendar_enabled: bool = False
    calendar_account_id: Optional[str] = None
    system_prompt_override: Optional[str] = None
    database_config: Optional[CampaignDatabaseConfig] = None

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id": "64f1b7caa4c123456789abcd",
                "user_id": "64f1b6d2a4c123456789ab12",
                "name": "US Morning Outreach",
                "country": "US",
                "working_window": {
                    "timezone": "America/New_York",
                    "start": "09:00",
                    "end": "17:00",
                    "days": [0, 1, 2, 3, 4]
                },
                "caller_id": "+12135550123",
                "assistant_id": "64f1b6a2a4c123456789a001",
                "retry_policy": {
                    "max_attempts": 3,
                    "retry_after_minutes": [15, 60, 1440]
                },
                "pacing": {
                    "calls_per_minute": 1,
                    "max_concurrent": 1
                },
                "start_at": None,
                "stop_at": None,
                "calendar_enabled": False,
                "system_prompt_override": None,
                "database_config": None,
                "status": "draft",
                "created_at": "2025-01-01T13:00:00Z",
                "updated_at": "2025-01-01T13:00:00Z",
                "next_index": 0
            }
        }


class CampaignListResponse(BaseModel):
    campaigns: List[CampaignResponse]
    total: int


# ===== LEAD MODELS =====
class LeadBase(BaseModel):
    raw_number: str = Field(..., description="Original phone number from CSV")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    batch_name: Optional[str] = Field(default=None, description="Optional batch label supplied during CSV upload")
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict)


class LeadCreate(LeadBase):
    campaign_id: str


class SentimentAnalysis(BaseModel):
    label: str = Field(..., description="positive|neutral|negative")
    score: float = Field(..., ge=-1.0, le=1.0)


class LeadResponse(LeadBase):
    id: str = Field(..., alias="_id")
    campaign_id: str
    e164: Optional[str] = None
    timezone: Optional[str] = None
    status: str = Field(default="queued")  # queued|calling|completed|failed|no-answer|busy
    attempts: int = Field(default=0)
    last_call_sid: Optional[str] = None
    retry_on: Optional[str] = None  # "tomorrow" or None
    sentiment: Optional[SentimentAnalysis] = None
    summary: Optional[str] = None
    calendar_booked: bool = False
    order_index: Optional[int] = Field(default=None, description="Zero-based ordering from original upload")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class LeadUploadResponse(BaseModel):
    total: int
    valid: int
    invalid: int
    mismatches: int
    message: str


class ManualRetryRequest(BaseModel):
    lead_ids: List[str]
    reason: Optional[str] = Field(default=None, description="Optional reason for retrying")


# ===== CALL ATTEMPT MODELS =====
class CallAttemptAnalysis(BaseModel):
    sentiment: str
    sentiment_score: float
    summary: str
    appointment: Optional[Dict[str, Any]] = None  # {title, start_iso, end_iso, timezone}


class CallAttemptResponse(BaseModel):
    id: str = Field(..., alias="_id")
    campaign_id: str
    lead_id: str
    attempt: int
    call_sid: str
    status: str  # initiated|ringing|in-progress|completed|busy|no-answer|failed|canceled
    recording_url: Optional[str] = None
    transcript: Optional[str] = None
    analysis: Optional[CallAttemptAnalysis] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration: Optional[int] = None  # seconds

    class Config:
        populate_by_name = True


# ===== CALENDAR MODELS =====
class CalendarAccountBase(BaseModel):
    provider: str = Field(..., description="google or microsoft")
    email: str


class CalendarAccountCreate(CalendarAccountBase):
    user_id: str
    oauth_data: Dict[str, Any] = Field(..., description="Contains accessToken, refreshToken, expiry, etc.")


class CalendarAccountResponse(CalendarAccountBase):
    id: str = Field(..., alias="_id")
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class AppointmentCreate(BaseModel):
    user_id: str
    lead_id: str
    campaign_id: str
    provider: str  # google|microsoft
    provider_event_id: str
    title: str
    start: datetime
    end: datetime
    timezone: str


class AppointmentResponse(BaseModel):
    id: str = Field(..., alias="_id")
    user_id: str
    lead_id: str
    campaign_id: str
    provider: str
    provider_event_id: str
    title: str
    start: datetime
    end: datetime
    timezone: str
    created_at: datetime

    class Config:
        populate_by_name = True


# ===== CAMPAIGN CONTROL =====
class CampaignStatusUpdate(BaseModel):
    status: str = Field(..., description="running|paused|stopped|completed")


# ===== REPORTING MODELS =====
class CampaignStats(BaseModel):
    total_leads: int
    queued: int
    completed: int
    failed: int
    no_answer: int
    busy: int
    calling: int
    avg_sentiment_score: Optional[float] = None
    calendar_bookings: int
    total_calls: int
    avg_call_duration: Optional[float] = None
