from pydantic_settings import BaseSettings
from typing import Optional
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Print early for Cloud Run debugging
print(f"[SETTINGS] Loading settings module...", flush=True)

# Get the project root directory (two levels up from this file)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

class Settings(BaseSettings):
    # MongoDB Configuration
    mongodb_uri: str
    database_name: str

    # Email Configuration
    email_user: str
    email_pass: str
    smtp_host: str = "p1432.use1.mysecurecloudhost.com"
    smtp_port: int = 465
    smtp_use_ssl: bool = True

    # Application Configuration
    frontend_url: str = "https://webapp.convis.ai"
    jwt_secret: str = "default_secret_change_in_production"

    # TTS Provider API Keys
    openai_api_key: Optional[str] = None
    sarvam_api_key: Optional[str] = None
    cartesia_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None

    # ASR Provider API Keys
    deepgram_api_key: Optional[str] = None

    # Encryption Configuration (for production)
    encryption_key: Optional[str] = None

    # Environment
    environment: str = "development"  # development, staging, production

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: Optional[str] = None  # For webhook URLs in production
    base_url: Optional[str] = None  # Alias for api_base_url

    # Twilio Configuration (optional defaults)
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None

    # Redis Configuration
    redis_url: str = "redis://localhost:6379"

    # Campaign defaults
    default_timezone: str = "America/New_York"
    default_max_attempts: int = 3

    # Feature flags
    enable_calendar_booking: bool = True
    enable_post_call_ai: bool = True
    enable_auto_retry: bool = True

    # Campaign scheduler (reduced to 1 second for ultra-fast call progression)
    campaign_dispatch_interval_seconds: int = 1

    # Google Calendar
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # Microsoft Calendar
    microsoft_client_id: Optional[str] = None
    microsoft_client_secret: Optional[str] = None
    microsoft_tenant_id: Optional[str] = None
    microsoft_redirect_uri: Optional[str] = None

    model_config = {
        "env_file": str(ENV_FILE),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }

    def validate_production_settings(self):
        """Validate critical settings for production environment"""
        if self.environment == "production":
            errors = []

            if self.jwt_secret == "default_secret_change_in_production":
                errors.append("JWT_SECRET must be changed for production")

            if not self.encryption_key:
                errors.append("ENCRYPTION_KEY is required for production")

            if not self.openai_api_key:
                logger.warning("OPENAI_API_KEY not set - inbound calls will not work")

            if not self.api_base_url:
                errors.append("API_BASE_URL is required for production (webhook URLs)")

            if "localhost" in self.frontend_url:
                logger.warning("FRONTEND_URL still set to localhost - update for production")

            if errors:
                raise ValueError(f"Production configuration errors: {', '.join(errors)}")

        logger.info(f"Running in {self.environment} mode")

try:
    settings = Settings()
    print(f"[SETTINGS] Settings loaded successfully. Environment: {settings.environment}", flush=True)
except Exception as e:
    print(f"[SETTINGS] FATAL: Failed to load settings: {e}", flush=True)
    print(f"[SETTINGS] Required env vars: MONGODB_URI, DATABASE_NAME, EMAIL_USER, EMAIL_PASS", flush=True)
    print(f"[SETTINGS] Current env vars: {list(os.environ.keys())}", flush=True)
    raise

# Validate settings on startup
try:
    settings.validate_production_settings()
except ValueError as e:
    print(f"[SETTINGS] Configuration validation failed: {e}", flush=True)
    logger.error(f"Configuration validation failed: {e}")
    if settings.environment == "production":
        raise
