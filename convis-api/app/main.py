import os
import sys
import logging
import asyncio
import time

# CRITICAL: Print to stdout immediately for Cloud Run logging
print(f"[STARTUP] main.py loading... PORT={os.environ.get('PORT', 'not set')}", flush=True)
_startup_time = time.time()

from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.errors import RateLimitExceeded
import json

print(f"[STARTUP] FastAPI imported at {time.time()-_startup_time:.2f}s", flush=True)

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from app.routes.register import registration_router, verify_email_router, check_user_router
from app.routes.forgot_password import send_otp_router, verify_otp_router, reset_password_router
from app.routes.access import login_router, logout_router
from app.routes.user import update_profile_router
from app.routes.api_keys import router as api_keys_router
from app.routes.ai_assistant import assistants_router
from app.routes.ai_assistant import knowledge_base as knowledge_base_router
from app.routes.ai_assistant import database as database_router
from app.routes.ai_assistant import email_settings as email_settings_router
from app.routes.ai_assistant import email_attachments as email_attachments_router
from app.routes.inbound_calls import inbound_calls_router
from app.routes.outbound_calls import outbound_calls_router
from app.routes.phone_numbers import phone_numbers_router, twilio_management_router, subaccounts_router, messaging_services_router
from app.routes.calendar import router as calendar_router
from app.routes.campaigns import router as campaigns_router
from app.routes.twilio_webhooks import router as twilio_webhooks_router
from app.routes.campaign_twilio_callbacks import router as campaign_twilio_router
from app.routes.dashboard import router as dashboard_router
from app.routes.whatsapp import credentials_router, messages_router, webhooks_router
from app.routes.transcription import transcription_router
from app.routes.voices import router as voices_router
from app.routes.integrations.integrations import router as integrations_router
from app.routes.integrations.workflows import router as workflows_router
from app.routes.integrations.n8n import router as n8n_router
from app.routes.notifications import router as notifications_router
from app.routes.webrtc import router as webrtc_router
from app.routes.call_quality import router as call_quality_router
from app.routes.ollama import router as ollama_router
from app.config.database import Database
from app.config.settings import settings
from app.services.campaign_scheduler import campaign_scheduler
from app.middleware.rate_limiter import limiter, custom_rate_limit_exceeded_handler
from app.middleware.request_id import RequestIDMiddleware, get_request_id
from app.middleware.error_handler import (
    validation_exception_handler,
    http_exception_handler,
    starlette_exception_handler,
    general_exception_handler
)
from app.utils.cache import get_redis_client, close_redis
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

print(f"[STARTUP] All imports complete at {time.time()-_startup_time:.2f}s", flush=True)

# Configure structured logging for production
log_level = logging.DEBUG if settings.environment != "production" else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

# Enable DEBUG logging for campaign_scheduler to troubleshoot dispatcher issues
logging.getLogger('app.services.campaign_scheduler').setLevel(logging.DEBUG)

# Store environment in app state for error handling
app_state_initialized = False

# Create FastAPI app
app = FastAPI(
    title="Convis Labs Registration API",
    description="Python backend for user registration with OTP verification",
    version="1.0.0"
)

print(f"[STARTUP] FastAPI app created at {time.time()-_startup_time:.2f}s", flush=True)

# Store app configuration in state
app.state.environment = settings.environment
app.state.limiter = limiter

# Add middleware for high concurrency support
# 1. Request ID for tracing (must be first)
app.add_middleware(RequestIDMiddleware)

# 2. Response compression (reduces bandwidth for 1000s of users)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)

# Configure CORS
# Build list of allowed origins from environment
allowed_origins = []

# Add localhost origins for development (always allow for local development)
if settings.environment != "production":
    allowed_origins.extend([
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
    ])

# Add frontend URL from settings
if settings.frontend_url:
    allowed_origins.append(settings.frontend_url)

# Add any additional origins from CORS_ORIGINS env var (comma-separated)
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env:
    additional_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
    allowed_origins.extend(additional_origins)

# Always include production URLs
production_origins = [
    "https://webapp.convis.ai",
    "https://api.convis.ai",
    "https://convis-web-1035304851064.europe-west1.run.app",  # Cloud Run frontend
]
for origin in production_origins:
    if origin not in allowed_origins:
        allowed_origins.append(origin)

logging.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(registration_router, prefix="/api/register", tags=["Registration"])
app.include_router(verify_email_router, prefix="/api/register", tags=["Registration"])
app.include_router(check_user_router, prefix="/api/register", tags=["Registration"])

# Forgot password routers
app.include_router(send_otp_router, prefix="/api/forgot_password", tags=["Forgot Password"])
app.include_router(verify_otp_router, prefix="/api/forgot_password", tags=["Forgot Password"])
app.include_router(reset_password_router, prefix="/api/forgot_password", tags=["Forgot Password"])

# Access routers
app.include_router(login_router, prefix="/api/access", tags=["Access"])
app.include_router(logout_router, prefix="/api/access", tags=["Access"])

# User routers
app.include_router(update_profile_router, prefix="/api/users", tags=["Users"])
app.include_router(api_keys_router, prefix="/api/ai-keys", tags=["AI API Keys"])
app.include_router(campaigns_router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])

# AI Assistant routers
app.include_router(assistants_router, prefix="/api/ai-assistants", tags=["AI Assistants"])
app.include_router(knowledge_base_router.router, prefix="/api/ai-assistants/knowledge-base", tags=["Knowledge Base"])
app.include_router(database_router.router, prefix="/api/ai-assistants/database", tags=["Database Integration"])
app.include_router(email_settings_router.router, prefix="/api/ai-assistants", tags=["Email Settings"])
app.include_router(email_attachments_router.router, prefix="/api/ai-assistants", tags=["Email Attachments"])

# Inbound Calls routers
app.include_router(inbound_calls_router, prefix="/api/inbound-calls", tags=["Inbound Calls"])

# Outbound Calls routers
app.include_router(outbound_calls_router, prefix="/api/outbound-calls", tags=["Outbound Calls"])

# Phone Numbers routers
app.include_router(phone_numbers_router, prefix="/api/phone-numbers", tags=["Phone Numbers"])
app.include_router(twilio_management_router, prefix="/api/phone-numbers/twilio", tags=["Twilio Management"])
app.include_router(subaccounts_router, prefix="/api/phone-numbers/subaccounts", tags=["Subaccounts"])
app.include_router(messaging_services_router, prefix="/api/phone-numbers/messaging-services", tags=["Messaging Services"])
app.include_router(calendar_router, prefix="/api/calendar", tags=["Calendar"])

# Twilio Webhooks (dynamic routing)
app.include_router(twilio_webhooks_router, prefix="/api/twilio-webhooks", tags=["Twilio Webhooks"])
app.include_router(campaign_twilio_router, tags=["Campaign Webhooks"])

# WhatsApp Integration
app.include_router(credentials_router, prefix="/api/whatsapp", tags=["WhatsApp"])
app.include_router(messages_router, prefix="/api/whatsapp", tags=["WhatsApp"])
app.include_router(webhooks_router, prefix="/api/whatsapp", tags=["WhatsApp Webhooks"])

# Transcription Management
app.include_router(transcription_router, prefix="/api/transcription", tags=["Transcription"])

# Voice Library and Preferences
app.include_router(voices_router, prefix="/api/voices", tags=["Voices"])

# Integration System (Jira, HubSpot, Email, Workflows)
app.include_router(integrations_router, prefix="/api/integrations", tags=["Integrations"])
app.include_router(workflows_router, prefix="/api/workflows", tags=["Workflows"])
app.include_router(n8n_router, prefix="/api/n8n", tags=["n8n Workflows"])

# Notifications
app.include_router(notifications_router, tags=["Notifications"])

# WebRTC Voice Calls (for web/mobile clients - lower latency than WebSocket)
app.include_router(webrtc_router, prefix="/api/webrtc", tags=["WebRTC Voice"])

# Call Quality Monitoring
app.include_router(call_quality_router, prefix="/api/call-quality", tags=["Call Quality"])
app.include_router(ollama_router, prefix="/api/ollama", tags=["Ollama"])


async def transcribe_existing_recordings():
    """Background task to transcribe all existing recordings on startup"""
    import asyncio
    await asyncio.sleep(10)  # Wait 10 seconds for server to fully start

    try:
        from app.services.post_call_processor import PostCallProcessor

        db = Database.get_db()
        call_logs = db['call_logs']

        # Find calls with recordings but no transcripts (or failed transcriptions)
        query = {
            'recording_url': {'$ne': None, '$exists': True},
            '$or': [
                {'transcript': {'$exists': False}},
                {'transcript': None},
                {'transcript': ''},
                {'transcript': '[Transcription unavailable]'}
            ]
        }

        calls_to_transcribe = list(call_logs.find(query).limit(50))  # Limit to 50 at a time

        if len(calls_to_transcribe) > 0:
            logging.info(f"🎙️  Found {len(calls_to_transcribe)} calls to transcribe - starting background transcription...")

            processor = PostCallProcessor()
            for call in calls_to_transcribe:
                try:
                    await processor.transcribe_and_update_call(
                        call['call_sid'],
                        call['recording_url']
                    )
                    logging.info(f"✓ Transcribed {call['call_sid']}")
                    await asyncio.sleep(2)  # Rate limiting
                except Exception as e:
                    logging.error(f"Failed to transcribe {call.get('call_sid')}: {e}")

            logging.info(f"✓ Background transcription complete!")
    except Exception as e:
        logging.error(f"Error in background transcription: {e}")


@app.on_event("startup")
async def startup_event():
    """
    Initialize all services on startup - optimized for Cloud Run.

    CRITICAL: This function MUST complete in <1 second to pass Cloud Run startup probes.
    ALL heavy operations are deferred to background tasks.
    """
    logger = logging.getLogger(__name__)
    logger.info("🚀 Application starting - deferring all heavy initialization to background...")

    # ALL initialization is done in background to ensure fast startup
    async def initialize_services():
        """Background task to initialize all services after startup."""
        await asyncio.sleep(1)  # Let the server start first

        # 1. Connect to MongoDB
        try:
            Database.connect()
            logger.info("✅ Connected to MongoDB")
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")

        # 2. Create database indexes
        try:
            from app.services.database_indexes import create_all_indexes
            create_all_indexes()
            logger.info("✅ Database indexes created/verified")
        except Exception as e:
            logger.warning(f"⚠️ Failed to create database indexes: {e}")

        # 3. Initialize Redis cache
        try:
            redis_client = await get_redis_client()
            if redis_client:
                await asyncio.wait_for(redis_client.ping(), timeout=5.0)
                logger.info("✅ Redis cache initialized")
            else:
                logger.warning("⚠️ Redis cache not available")
        except Exception as e:
            logger.warning(f"⚠️ Redis initialization failed: {e}")

        # 4. Start campaign scheduler
        try:
            await campaign_scheduler.start()
            logger.info("✅ Campaign scheduler started")
        except Exception as e:
            logger.warning(f"⚠️ Campaign scheduler failed to start: {e}")

        logger.info("✅ All background services initialized")

    # Launch all initialization in background - don't wait
    asyncio.create_task(initialize_services())

    logger.info("🚀 Application startup complete - ready for health checks")

@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully shutdown all services"""
    logger = logging.getLogger(__name__)
    
    try:
        # Shutdown campaign scheduler
        await campaign_scheduler.shutdown()
        logger.info("✅ Campaign scheduler shut down")
        
        # Close Redis connections
        await close_redis()
        logger.info("✅ Redis connections closed")
        
        # Close database connections
        Database.close()
        logger.info("✅ MongoDB connections closed")
        
        logger.info("✅ Application shutdown complete")
    except Exception as e:
        logger.error(f"⚠️ Shutdown error: {e}", exc_info=True)

@app.get("/health")
async def health_check():
    """
    Simple health check endpoint for Cloud Run startup/liveness probes.
    This endpoint MUST respond quickly without any external dependencies.

    For Cloud Run, this is critical - the startup probe will fail if this
    endpoint takes too long or depends on slow external services.
    """
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/health/ready")
async def readiness_check(request: Request):
    """
    Comprehensive readiness check for monitoring and load balancers.
    Use this endpoint for readiness probes after the container is started.
    """
    request_id = get_request_id(request)
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "request_id": request_id,
        "checks": {}
    }

    overall_healthy = True

    # Check database connection
    try:
        db = Database.get_db()
        db.command('ping')
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    # Check Redis cache
    try:
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.ping()
            health_status["checks"]["redis"] = "healthy"
        else:
            health_status["checks"]["redis"] = "unavailable"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        # Redis is not critical, don't mark overall as unhealthy

    # Set overall status
    health_status["status"] = "healthy" if overall_healthy else "degraded"

    # Return appropriate status code
    status_code = 200 if overall_healthy else 503
    return health_status

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "running",
        "message": "Convis Labs Registration API",
        "version": "1.0.0",
        "environment": settings.environment
    }
