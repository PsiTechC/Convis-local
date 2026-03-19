import os
import json
import asyncio
import websockets
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from bson import ObjectId
from app.config.database import Database
from app.config.settings import settings
from app.utils.assistant_keys import resolve_assistant_api_key
from app.utils.twilio_helpers import decrypt_twilio_credentials
from app.utils import conversational_rag
from app.utils.openai_session import (
    send_session_update,
    send_mark,
    handle_interruption,
    inject_knowledge_base_context,
    LOG_EVENT_TYPES,
    transcript_has_hangup_intent,
    transcript_confirms_hangup,
    transcript_denies_hangup,
    request_call_end_confirmation,
    send_call_end_acknowledgement,
    send_call_continue_acknowledgement,
)
from app.services.calendar_service import CalendarService
from app.services.calendar_intent_service import CalendarIntentService
from app.utils.background_audio import BackgroundAudioMixer, create_mixer_from_assistant
from app.models.inbound_calls import InboundCallConfig, InboundCallResponse
from fastapi.responses import PlainTextResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Configuration for interruption handling
SHOW_TIMING_MATH = False

@router.get("/", response_class=JSONResponse)
async def inbound_calls_index():
    """Health check for inbound calls service"""
    return {"message": "Inbound calls service is running"}


@router.post("/connect/{assistant_id}")
async def twilio_connect_custom(assistant_id: str, request: Request):
    """
    Twilio webhook endpoint that returns TwiML to connect to custom provider WebSocket
    Bolna-style architecture: returns TwiML with WebSocket stream URL

    This is called by Twilio when a call comes in to a phone number assigned to this assistant
    """
    try:
        # Get request origin to construct WebSocket URL
        base_url = str(request.base_url).replace('http://', 'wss://').replace('https://', 'wss://')
        websocket_url = f"{base_url}api/inbound-calls/stream/custom/{assistant_id}"

        # Return TwiML that connects Twilio to our WebSocket
        response = VoiceResponse()
        connect = Connect()
        connect.stream(url=websocket_url)
        response.append(connect)  # CRITICAL: Append connect to response!

        logger.info(f"[CONNECT] Routing call to WebSocket: {websocket_url}")

        return PlainTextResponse(str(response), media_type='text/xml')

    except Exception as e:
        logger.error(f"[CONNECT] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config/{assistant_id}", response_model=InboundCallResponse, status_code=status.HTTP_200_OK)
async def get_inbound_call_config(assistant_id: str):
    """
    Get AI assistant configuration for inbound calls

    Args:
        assistant_id: The AI assistant ID to fetch configuration for

    Returns:
        InboundCallResponse: Configuration details

    Raises:
        HTTPException: If assistant not found or error occurs
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        logger.info(f"Fetching configuration for assistant: {assistant_id}")

        # Convert to ObjectId
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        # Fetch assistant configuration
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})

        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        config = InboundCallConfig(
            assistant_id=str(assistant['_id']),
            system_message=assistant['system_message'],
            voice=assistant['voice'],
            temperature=assistant['temperature']
        )

        return InboundCallResponse(
            message="Configuration retrieved successfully",
            config=config
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error fetching assistant configuration: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch assistant configuration: {str(error)}"
        )

@router.api_route("/incoming-call/{assistant_id}", methods=["GET", "POST"])
async def handle_incoming_call(assistant_id: str, request: Request):
    """
    Handle incoming call and return TwiML response to connect to Media Stream.
    Fetches configuration from MongoDB based on assistant_id.
    
    OPTIMIZED: Routes to optimized stream handler for custom provider mode.

    Args:
        assistant_id: The AI assistant ID to use for this call
        request: FastAPI request object

    Returns:
        HTMLResponse: TwiML XML response

    Raises:
        HTTPException: If assistant not found or error occurs
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        logger.info(f"Incoming call for assistant: {assistant_id}")

        # Convert to ObjectId
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        # Fetch assistant configuration
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})

        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        # Create TwiML response - connect directly to AI without artificial greetings
        response = VoiceResponse()

        # Use API_BASE_URL from settings if available
        if settings.api_base_url:
            # Extract hostname from API_BASE_URL (remove http:// or https://)
            host = settings.api_base_url.replace('https://', '').replace('http://', '')
        else:
            host = request.url.hostname

        # OPTIMIZED: Route to optimized stream for custom provider mode
        voice_mode = assistant.get('voice_mode', 'realtime')
        
        if voice_mode == 'custom':
            # Use optimized low-latency stream handler for custom providers (Deepgram/ElevenLabs/etc)
            websocket_url = f'wss://{host}/api/inbound-calls/stream/custom/{assistant_id}'
            logger.info(f"[OPTIMIZED] Using low-latency stream for custom provider: {websocket_url}")
        else:
            # Use OpenAI Realtime API stream for realtime mode
            websocket_url = f'wss://{host}/api/inbound-calls/media-stream/{assistant_id}'
            logger.info(f"WebSocket URL: {websocket_url}")

        connect = Connect()
        connect.stream(url=websocket_url)
        response.append(connect)

        # Enable call recording
        # Record both inbound and outbound audio, transcribe the call
        response.record(
            recording_status_callback=f'{settings.api_base_url or f"https://{host}"}/api/inbound-calls/recording-status',
            recording_status_callback_method='POST',
            transcribe=True,
            transcribe_callback=f'{settings.api_base_url or f"https://{host}"}/api/inbound-calls/transcription-status',
            max_length=3600,  # Max 1 hour
            timeout=5,
            play_beep=False
        )

        return HTMLResponse(content=str(response), media_type="application/xml")

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error handling incoming call: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to handle incoming call: {str(error)}"
        )

@router.websocket("/stream/custom/{assistant_id}")
async def handle_custom_stream(websocket: WebSocket, assistant_id: str):
    """
    OPTIMIZED: Low-latency WebSocket endpoint for custom provider mode
    Uses OptimizedStreamHandler for VAPI-like performance (~300-600ms response time)

    This endpoint is specifically for voice_mode='custom' assistants
    Includes calendar scheduling support (same as realtime API)
    """
    logger.info(f"[OPTIMIZED_STREAM] 📞 Incoming WebSocket connection for assistant: {assistant_id}")
    await websocket.accept()
    logger.info(f"[OPTIMIZED_STREAM] ✅ WebSocket connection accepted")

    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Fetch assistant configuration
        try:
            assistant_obj_id = ObjectId(assistant_id)
            logger.info(f"[OPTIMIZED_STREAM] Converted assistant_id to ObjectId: {assistant_obj_id}")
        except Exception as e:
            logger.error(f"[OPTIMIZED_STREAM] ❌ Invalid assistant_id format: {e}")
            await websocket.close(code=1008, reason="Invalid assistant_id")
            return

        logger.info(f"[OPTIMIZED_STREAM] 🔍 Fetching assistant from database...")
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})

        if not assistant:
            logger.error(f"[OPTIMIZED_STREAM] ❌ Assistant not found in database: {assistant_id}")
            await websocket.close(code=1008, reason="Assistant not found")
            return

        logger.info(f"[OPTIMIZED_STREAM] ✅ Assistant found: {assistant.get('name', 'Unknown')}")

        # Verify this is a custom provider assistant
        voice_mode = assistant.get('voice_mode', 'realtime')
        logger.info(f"[OPTIMIZED_STREAM] 🔧 Voice mode: {voice_mode}")

        if voice_mode != 'custom':
            logger.error(f"[OPTIMIZED_STREAM] ❌ Assistant {assistant_id} is not in custom mode (mode: {voice_mode})")
            await websocket.close(code=1008, reason="Assistant not configured for custom provider")
            return

        logger.info(f"[OPTIMIZED_STREAM] 🚀 Starting OPTIMIZED stream for '{assistant.get('name')}'")
        logger.info(f"[OPTIMIZED_STREAM] 📊 Config: ASR={assistant.get('asr_provider')}, TTS={assistant.get('tts_provider')}, LLM={assistant.get('llm_provider')}")

        # Import handlers
        from app.services.call_handlers.optimized_stream_handler import handle_optimized_stream
        from app.services.call_handlers.ultra_low_latency_handler import handle_ultra_low_latency_stream
        from app.utils.assistant_keys import resolve_provider_keys, resolve_assistant_api_key

        # Get user ID for API key resolution
        assistant_user_id = assistant.get('user_id')
        if isinstance(assistant_user_id, str):
            assistant_user_id = ObjectId(assistant_user_id)

        logger.info(f"[OPTIMIZED_STREAM] 🔑 Resolving API keys for user: {assistant_user_id}")

        # Resolve all provider keys
        provider_keys = resolve_provider_keys(db, assistant, assistant_user_id)
        logger.info(f"[OPTIMIZED_STREAM] ✅ Resolved provider keys: {list(provider_keys.keys())}")

        # ============ CALENDAR CONFIGURATION ============
        # Same calendar setup as realtime API for consistency
        timezone_hint = (
            assistant.get('timezone')
            or settings.default_timezone
            or "America/New_York"
        )

        calendar_enabled = False
        default_calendar_provider = "google"
        calendar_account_id_for_booking = None
        calendar_account_ids_list = []
        calendar_accounts_collection = db["calendar_accounts"]

        # Check for NEW multi-calendar support (calendar_account_ids)
        assistant_calendar_ids = assistant.get('calendar_account_ids', [])
        assistant_calendar_enabled = assistant.get('calendar_enabled', False)

        if assistant_calendar_ids and assistant_calendar_enabled and assistant_user_id:
            # Verify all calendar accounts exist and belong to the user
            valid_calendar_ids = []
            for cal_id in assistant_calendar_ids:
                calendar_account = calendar_accounts_collection.find_one({
                    "_id": cal_id,
                    "user_id": assistant_user_id
                })
                if calendar_account:
                    valid_calendar_ids.append(str(cal_id))

            if valid_calendar_ids:
                calendar_enabled = True
                calendar_account_ids_list = valid_calendar_ids
                logger.info(f"[OPTIMIZED_STREAM] 📅 Multi-calendar enabled with {len(valid_calendar_ids)} calendar(s)")

        # FALLBACK: Support legacy single calendar_account_id
        if not calendar_enabled and assistant.get('calendar_account_id'):
            assistant_calendar_id = assistant.get('calendar_account_id')
            account_doc = calendar_accounts_collection.find_one({"_id": assistant_calendar_id})
            if account_doc:
                calendar_enabled = True
                calendar_account_id_for_booking = assistant_calendar_id
                calendar_account_ids_list = [str(assistant_calendar_id)]
                default_calendar_provider = account_doc.get("provider", "google")
                logger.info(f"[OPTIMIZED_STREAM] 📅 Calendar enabled via legacy single account: {account_doc.get('email')}")

        # Add calendar instructions to system message if calendar is enabled
        system_message = assistant.get("system_message", "You are a helpful assistant.")
        if calendar_enabled:
            calendar_instructions = f"""

---
Calendar Scheduling Instructions:
You can schedule meetings and appointments during this call. When the person requests to schedule a meeting or appointment:

1. Ask for the preferred date and time
2. Confirm the meeting title/purpose
3. Confirm the duration (default to 30 minutes if not specified)
4. **IMPORTANT: Confirm their timezone** - Ask "What timezone are you in?" or "Just to confirm, you're in [timezone], correct?"
5. Let them know you'll schedule it

Default timezone (if they don't specify): {timezone_hint}

IMPORTANT:
- Always confirm the timezone before finalizing the appointment
- Be natural and conversational
- Don't mention "the system" or technical details
- If they mention a timezone, use it; otherwise use {timezone_hint}"""
            system_message = f"{system_message}{calendar_instructions}"
            logger.info(f"[OPTIMIZED_STREAM] 📅 Added calendar instructions to system message")

        # Build assistant config for optimized handler
        assistant_config = {
            "system_message": system_message,
            "greeting": assistant.get("call_greeting", "Hello! How can I help you today?"),
            "voice": assistant.get("voice", "shimmer"),
            "tts_voice": assistant.get("tts_voice", assistant.get("voice", "shimmer")),
            "temperature": assistant.get("temperature", 0.8),
            "asr_provider": assistant.get("asr_provider", "deepgram"),
            "asr_model": assistant.get("asr_model", "nova-3"),
            "asr_language": assistant.get("asr_language", "en"),
            "asr_keywords": assistant.get("asr_keywords", []),
            "tts_provider": assistant.get("tts_provider", "elevenlabs"),
            "tts_model": assistant.get("tts_model"),
            "tts_speed": assistant.get("tts_speed", 1.0),
            "llm_provider": assistant.get("llm_provider", "openai"),
            "llm_model": assistant.get("llm_model", "gpt-4o-mini"),
            "llm_max_tokens": assistant.get("llm_max_tokens", 150),
            "bot_language": assistant.get("bot_language", "en"),
            "enable_precise_transcript": assistant.get("enable_precise_transcript", False),
            "interruption_threshold": assistant.get("interruption_threshold", 2),
            "response_rate": assistant.get("response_rate", "balanced"),
            "check_user_online": assistant.get("check_user_online", True),
            "audio_buffer_size": assistant.get("audio_buffer_size", 200),
            "noise_suppression_level": assistant.get("noise_suppression_level", "medium"),
            "vad_threshold": assistant.get("vad_threshold", 0.5),
            "vad_prefix_padding_ms": assistant.get("vad_prefix_padding_ms", 300),
            "vad_silence_duration_ms": assistant.get("vad_silence_duration_ms", 500),
            # Ultra-low-latency settings (ElevenLabs WebSocket / Sarvam chunked)
            "streaming_mode": assistant.get("streaming_mode", "optimized"),
            "tts_stability": assistant.get("tts_stability", 0.5),
            "tts_similarity_boost": assistant.get("tts_similarity_boost", 0.75),
            "tts_style": assistant.get("tts_style", 0.0),
            "tts_pitch": assistant.get("tts_pitch", 0.0),
            "tts_loudness": assistant.get("tts_loudness", 1.0),
            # Calendar configuration for handlers
            "calendar_enabled": calendar_enabled,
            "calendar_account_ids": calendar_account_ids_list,
            "calendar_account_id": str(calendar_account_id_for_booking) if calendar_account_id_for_booking else None,
            "calendar_provider": default_calendar_provider,
            "timezone": timezone_hint,
            "assistant_id": assistant_id,
            "user_id": str(assistant_user_id) if assistant_user_id else None,
            # Real-time tool calling (Vapi-like functionality)
            "tools_enabled": assistant.get("tools_enabled", False),
            "tools": assistant.get("tools", []),
            "max_tool_calls_per_turn": assistant.get("max_tool_calls_per_turn", 5),
            "tool_execution_timeout": assistant.get("tool_execution_timeout", 30),
        }

        # Check streaming mode: "ultra" for word-by-word, "optimized" for sentence-by-sentence
        streaming_mode = assistant.get("streaming_mode", "optimized")
        tts_provider = assistant_config.get("tts_provider", "elevenlabs").lower()

        # Ultra-low-latency mode requires ElevenLabs or Sarvam TTS
        use_ultra_mode = (
            streaming_mode == "ultra" and
            tts_provider in ["elevenlabs", "sarvam"]
        )

        if use_ultra_mode:
            logger.info(f"[ULTRA_STREAM] ⚡ Using ULTRA-LOW-LATENCY pipeline (word-by-word)")
            logger.info(f"[ULTRA_STREAM] ▶️ Starting handle_ultra_low_latency_stream()")

            # Run ultra-low-latency handler (~100-200ms latency)
            await handle_ultra_low_latency_stream(websocket, assistant_config, provider_keys)

            logger.info(f"[ULTRA_STREAM] ✅ Ultra-low-latency stream completed")
        else:
            logger.info(f"[OPTIMIZED_STREAM] ⚡ Using OPTIMIZED low-latency pipeline (sentence-by-sentence)")
            logger.info(f"[OPTIMIZED_STREAM] ▶️ Starting handle_optimized_stream()")

            # Run optimized handler (VAPI-style streaming pipeline, ~300-600ms latency)
            await handle_optimized_stream(websocket, assistant_config, provider_keys)

            logger.info(f"[OPTIMIZED_STREAM] ✅ Optimized stream completed")

    except WebSocketDisconnect:
        logger.info(f"[OPTIMIZED_STREAM] WebSocket disconnected for assistant {assistant_id}")
    except Exception as e:
        logger.error(f"[OPTIMIZED_STREAM] Error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except:
            pass

    logger.info(f"[OPTIMIZED_STREAM] Stream ended for assistant {assistant_id}")


@router.websocket("/media-stream/{assistant_id}")
async def handle_media_stream(websocket: WebSocket, assistant_id: str):
    """
    Handle WebSocket connections between Twilio and OpenAI.
    Fetches configuration from MongoDB based on assistant_id.

    Args:
        websocket: WebSocket connection
        assistant_id: The AI assistant ID to use for this call
    """
    logger.info(f"Client connected for assistant: {assistant_id}")
    await websocket.accept()

    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Convert to ObjectId
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception as e:
            logger.error(f"Invalid assistant_id format: {e}")
            await websocket.close(code=1008, reason="Invalid assistant_id")
            return

        # Fetch assistant configuration
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})

        if not assistant:
            logger.error(f"Assistant not found: {assistant_id}")
            await websocket.close(code=1008, reason="Assistant not found")
            return

        provider_connections_collection = db['provider_connections']
        twilio_client = None
        assistant_user_id = assistant.get('user_id')
        try:
            twilio_connection = None
            if assistant_user_id:
                twilio_connection = provider_connections_collection.find_one({
                    "user_id": assistant_user_id,
                    "provider": "twilio"
                })
            account_sid = None
            auth_token = None
            if twilio_connection:
                account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
            if not account_sid:
                account_sid = settings.twilio_account_sid
            if not auth_token:
                auth_token = settings.twilio_auth_token
            if account_sid and auth_token:
                twilio_client = Client(account_sid, auth_token)
            else:
                logger.warning(
                    "Twilio credentials not available for assistant %s; hangup control will be limited",
                    assistant_id
                )
        except Exception as cred_error:
            logger.error(f"Failed to initialize Twilio client for assistant {assistant_id}: {cred_error}")
            twilio_client = None

        system_message = assistant['system_message']
        voice = assistant['voice']
        temperature = assistant['temperature']
        call_greeting = assistant.get('call_greeting')
        bot_language = assistant.get('bot_language', 'en')
        voice_mode = assistant.get('voice_mode', 'realtime')  # Get voice mode

        logger.info(f"[INBOUND] Voice mode: {voice_mode}")

        # Resolve OpenAI API key - try assistant's key first, then fall back to system env key
        openai_api_key = None
        try:
            openai_api_key, _ = resolve_assistant_api_key(db, assistant, required_provider="openai")
            logger.info(f"[INBOUND] Using assistant's OpenAI API key")
        except HTTPException as exc:
            logger.warning(f"[INBOUND] No assistant API key found: {exc.detail}")

        # Fallback to system OpenAI API key from environment
        if not openai_api_key:
            openai_api_key = settings.openai_api_key
            if openai_api_key:
                logger.info(f"[INBOUND] Using system OpenAI API key from environment")
            else:
                logger.error(f"[INBOUND] No OpenAI API key available (neither assistant nor system)")
                await websocket.close(code=1008, reason="No OpenAI API key configured")
                return

        # Route to appropriate handler based on voice mode
        if voice_mode == 'custom':
            # Use advanced streaming voice pipeline (WebSocket-based ASR -> LLM -> TTS)
            logger.info("[INBOUND] Using advanced streaming pipeline for custom provider mode")
            from app.voice_pipeline.pipeline import StreamProviderHandler
            from app.utils.assistant_keys import resolve_provider_keys

            # Get user ID for API key resolution
            assistant_user_id = assistant.get('user_id')
            if isinstance(assistant_user_id, str):
                from bson import ObjectId
                assistant_user_id = ObjectId(assistant_user_id)

            # Resolve API keys from database (user's stored keys) with environment fallback
            api_keys = resolve_provider_keys(db, assistant, assistant_user_id)

            logger.info(f"[INBOUND] Resolved API keys for providers: {list(api_keys.keys())}")

            # Add Azure region to assistant config if available
            import os
            if os.getenv('AZURE_SPEECH_REGION'):
                assistant['azure_region'] = os.getenv('AZURE_SPEECH_REGION')
            if os.getenv('AZURE_OPENAI_ENDPOINT'):
                assistant['azure_openai_endpoint'] = os.getenv('AZURE_OPENAI_ENDPOINT')

            # Initialize streaming handler with voice pipeline
            handler = StreamProviderHandler(websocket, assistant, api_keys, db=db)

            # Run handler with Bolna-style internal message loop
            try:
                await handler.run()
            except Exception as e:
                logger.error(f"[STREAM_PIPELINE_ERROR] {e}", exc_info=True)
            finally:
                await websocket.close()
            return

        # Continue with realtime API mode (default)
        logger.info("[INBOUND] Using OpenAI Realtime API mode")

        # Add language instruction to system message if not English
        if bot_language and bot_language != 'en':
            language_names = {
                'hi': 'Hindi',
                'es': 'Spanish',
                'fr': 'French',
                'de': 'German',
                'pt': 'Portuguese',
                'it': 'Italian',
                'ja': 'Japanese',
                'ko': 'Korean',
                'ar': 'Arabic',
                'ru': 'Russian',
                'zh': 'Chinese',
                'nl': 'Dutch',
                'pl': 'Polish',
                'tr': 'Turkish'
            }
            language_name = language_names.get(bot_language, bot_language.upper())
            system_message = f"{system_message}\n\nIMPORTANT: You MUST speak and respond ONLY in {language_name}. All your responses should be in {language_name} language."

        timezone_hint = (
            assistant.get('timezone')
            or settings.default_timezone
            or "America/New_York"
        )

        # Calendar integration state
        assistant_user_id = assistant.get('user_id')
        calendar_enabled = False
        default_calendar_provider = "google"
        calendar_service: Optional[CalendarService] = None
        calendar_intent_service: Optional[CalendarIntentService] = None
        conversation_history: List[Dict[str, str]] = []
        scheduling_task: Optional[asyncio.Task] = None
        appointment_scheduled = False
        appointment_metadata: Dict[str, Any] = {}
        calendar_account_id_for_booking = None
        calendar_account_ids_list = []

        # Check if assistant has calendar accounts assigned (new multi-calendar support)
        assistant_calendar_ids = assistant.get('calendar_account_ids', [])
        assistant_calendar_enabled = assistant.get('calendar_enabled', False)

        # NEW: Support multiple calendars
        if assistant_calendar_ids and assistant_calendar_enabled and assistant_user_id:
            calendar_accounts_collection = db["calendar_accounts"]
            # Verify all calendar accounts exist and belong to the user
            valid_calendar_ids = []
            for cal_id in assistant_calendar_ids:
                calendar_account = calendar_accounts_collection.find_one({
                    "_id": cal_id,
                    "user_id": assistant_user_id
                })
                if calendar_account:
                    valid_calendar_ids.append(str(cal_id))

            if valid_calendar_ids:
                calendar_enabled = True
                calendar_account_ids_list = valid_calendar_ids
                calendar_service = CalendarService()
                calendar_intent_service = CalendarIntentService()
                logger.info(f"[INBOUND] Multi-calendar enabled for assistant {assistant_id} with {len(valid_calendar_ids)} calendar(s)")

        # FALLBACK: Support legacy single calendar_account_id
        elif not calendar_enabled:
            assistant_calendar_id = assistant.get('calendar_account_id')
            if assistant_calendar_id and assistant_user_id:
                calendar_accounts_collection = db["calendar_accounts"]
                calendar_account = calendar_accounts_collection.find_one({
                    "_id": assistant_calendar_id,
                    "user_id": assistant_user_id
                })
                if calendar_account:
                    calendar_enabled = True
                    calendar_account_id_for_booking = assistant_calendar_id
                    calendar_account_ids_list = [str(assistant_calendar_id)]
                    default_calendar_provider = calendar_account.get("provider", "google")
                    calendar_service = CalendarService()
                    calendar_intent_service = CalendarIntentService()
                    logger.info(f"[INBOUND] Calendar enabled for assistant {assistant_id} using legacy single account {calendar_account.get('email')}")
                calendar_instructions = f"""

---
Calendar Scheduling Instructions:
You can schedule meetings and appointments during this call. When the person requests to schedule a meeting or appointment:

1. Ask for the preferred date and time
2. Confirm the meeting title/purpose
3. Confirm the duration (default to 30 minutes if not specified)
4. **IMPORTANT: Confirm their timezone** - Ask "What timezone are you in?" or "Just to confirm, you're in [timezone], correct?"
5. Let them know you'll schedule it

Default timezone (if they don't specify): {timezone_hint}

Example conversation:
Person: "Can we schedule a follow-up meeting?"
You: "Of course! When would you like to schedule the meeting? What date and time works best for you?"
Person: "How about next Tuesday at 2 PM?"
You: "Perfect! And just to confirm, what timezone are you in?"
Person: "I'm in India, IST timezone."
You: "Great! So I'll schedule a follow-up meeting for next Tuesday at 2 PM Indian Standard Time. It will be for 30 minutes. Is that correct?"
Person: "Yes, that works."
You: "Excellent! I've scheduled your meeting and it will be added to your calendar."

IMPORTANT:
- Always confirm the timezone before finalizing the appointment
- Be natural and conversational
- Don't mention "the system" or technical details
- If they mention a timezone, use it; otherwise use {timezone_hint}"""
                system_message = f"{system_message}{calendar_instructions}"

        async def maybe_schedule_from_conversation(trigger: str = "") -> None:
            """
            Analyze recent conversation context and create a calendar event if appropriate.
            Runs in the background so realtime audio is not blocked.
            """
            nonlocal scheduling_task, appointment_scheduled, appointment_metadata, call_sid

            logger.debug(f"[CALENDAR_CHECK] Trigger: {trigger}, Calendar enabled: {calendar_enabled}")

            if (
                not calendar_enabled
                or calendar_intent_service is None
                or calendar_service is None
                or appointment_scheduled
            ):
                logger.debug(f"[CALENDAR_CHECK] Early return - calendar_enabled={calendar_enabled}, appointment_scheduled={appointment_scheduled}")
                return

            if scheduling_task and not scheduling_task.done():
                logger.debug("[CALENDAR_CHECK] Scheduling task already running")
                return

            if not conversation_history or not assistant_user_id or not openai_api_key:
                logger.debug(f"[CALENDAR_CHECK] Missing requirements - history={len(conversation_history) if conversation_history else 0}, user_id={assistant_user_id is not None}, api_key={openai_api_key is not None}")
                return

            if not call_sid:
                logger.debug("[CALENDAR_CHECK] Call SID unavailable; delaying calendar analysis")
                return

            logger.info(f"[CALENDAR_CHECK] ✓ Starting calendar intent analysis with {len(conversation_history)} messages")

            async def _run_analysis() -> None:
                nonlocal appointment_scheduled, appointment_metadata
                try:
                    logger.info("[CALENDAR_ANALYSIS] Extracting calendar intent from conversation...")
                    result = await calendar_intent_service.extract_from_conversation(
                        conversation_history,
                        openai_api_key,
                        timezone_hint,
                    )
                    logger.info(f"[CALENDAR_ANALYSIS] Intent result: {result}")

                    if not result or not result.get("should_schedule"):
                        logger.info("[CALENDAR_ANALYSIS] No scheduling intent detected")
                        return

                    appointment = result.get("appointment") or {}
                    start_iso = appointment.get("start_iso")
                    end_iso = appointment.get("end_iso")
                    if not start_iso or not end_iso:
                        logger.warning(
                            "[CALENDAR_ANALYSIS] Appointment payload missing start/end. Payload: %s",
                            appointment,
                        )
                        return

                    logger.info(f"[CALENDAR_ANALYSIS] ✓ Valid appointment detected: {appointment.get('title')} at {start_iso}")

                    appointment.setdefault("timezone", timezone_hint)
                    appointment.setdefault("notes", result.get("reason"))
                    provider = appointment.get("provider") or default_calendar_provider

                    # Parse appointment times for availability checking
                    try:
                        start_time = datetime.fromisoformat(start_iso)
                        end_time = datetime.fromisoformat(end_iso)
                    except Exception as e:
                        logger.error(f"[CALENDAR_ANALYSIS] Error parsing appointment times: {e}")
                        return

                    # MULTI-CALENDAR AVAILABILITY CHECKING
                    if calendar_account_ids_list and len(calendar_account_ids_list) > 1:
                        logger.info(f"[CALENDAR_ANALYSIS] Checking availability across {len(calendar_account_ids_list)} calendars...")

                        # Check if ALL calendars are free
                        availability_result = await calendar_service.check_availability_across_calendars(
                            calendar_account_ids_list,
                            start_time,
                            end_time
                        )

                        if not availability_result.get("is_available"):
                            # CONFLICT DETECTED - Inform the AI agent
                            conflicts = availability_result.get("conflicts", [])
                            conflict_details = []
                            for conflict in conflicts:
                                calendar_email = conflict.get("calendar_email", "Unknown")
                                events = conflict.get("conflicting_events", [])
                                for event in events:
                                    conflict_details.append(f"{event.get('title')} at {event.get('start')}")

                            conflict_message = (
                                f"I'm sorry, but that time slot is already occupied in your calendar. "
                                f"There's a conflict with: {', '.join(conflict_details[:2])}. "
                                f"Could you please suggest an alternative time?"
                            )

                            logger.warning(f"[CALENDAR_ANALYSIS] Conflict detected: {conflict_message}")

                            # Send conflict notification to AI agent
                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "message",
                                            "role": "system",
                                            "content": [
                                                {
                                                    "type": "input_text",
                                                    "text": (
                                                        f"CALENDAR CONFLICT: The requested time slot is not available. "
                                                        f"Inform the caller: {conflict_message}"
                                                    ),
                                                }
                                            ],
                                        },
                                    }
                                )
                            )
                            await openai_ws.send(json.dumps({"type": "response.create"}))

                            logger.info("[CALENDAR_ANALYSIS] Conflict notification sent to AI agent")
                            return  # Don't book - wait for alternative time

                        # ALL CALENDARS ARE FREE - Use round-robin to select which calendar to book
                        logger.info("[CALENDAR_ANALYSIS] All calendars available - using round-robin selection")
                        selected_calendar_id = await calendar_service.get_next_available_calendar_round_robin(
                            assistant,
                            start_time,
                            end_time
                        )

                        if selected_calendar_id:
                            calendar_account_id_for_booking = selected_calendar_id
                            logger.info(f"[CALENDAR_ANALYSIS] Selected calendar {selected_calendar_id} via round-robin")
                        else:
                            logger.error("[CALENDAR_ANALYSIS] Round-robin selection failed")
                            return

                    # SINGLE CALENDAR - Just check if it's available
                    elif calendar_account_ids_list and len(calendar_account_ids_list) == 1:
                        logger.info(f"[CALENDAR_ANALYSIS] Checking availability for single calendar...")
                        availability_result = await calendar_service.check_availability_across_calendars(
                            calendar_account_ids_list,
                            start_time,
                            end_time
                        )

                        if not availability_result.get("is_available"):
                            conflicts = availability_result.get("conflicts", [])
                            conflict_message = (
                                "I'm sorry, but that time slot is already occupied in your calendar. "
                                "Could you please suggest an alternative time?"
                            )

                            logger.warning(f"[CALENDAR_ANALYSIS] Conflict detected in single calendar")

                            # Send conflict notification to AI agent
                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "message",
                                            "role": "system",
                                            "content": [
                                                {
                                                    "type": "input_text",
                                                    "text": (
                                                        f"CALENDAR CONFLICT: The requested time slot is not available. "
                                                        f"Inform the caller: {conflict_message}"
                                                    ),
                                                }
                                            ],
                                        },
                                    }
                                )
                            )
                            await openai_ws.send(json.dumps({"type": "response.create"}))

                            logger.info("[CALENDAR_ANALYSIS] Conflict notification sent to AI agent")
                            return  # Don't book - wait for alternative time

                        calendar_account_id_for_booking = calendar_account_ids_list[0]
                        logger.info(f"[CALENDAR_ANALYSIS] Single calendar {calendar_account_id_for_booking} is available")

                    # Book the appointment
                    event_id = await calendar_service.book_inbound_appointment(
                        call_sid=call_sid,
                        user_id=str(assistant_user_id),
                        assistant_id=assistant_id,
                        appointment=appointment,
                        provider=provider,
                        calendar_account_id=str(calendar_account_id_for_booking) if calendar_account_id_for_booking else None,
                    )
                    if not event_id:
                        logger.warning("Calendar booking returned no event ID; check calendar configuration")
                        return

                    appointment_scheduled = True
                    appointment_metadata = {**appointment, "event_id": event_id, "provider": provider}

                    try:
                        db["call_logs"].update_one(
                            {"call_sid": call_sid},
                            {
                                "$set": {
                                    "appointment_booked": True,
                                    "appointment_details": appointment_metadata,
                                    "calendar_event_id": event_id,
                                    "appointment_source": "realtime",
                                    "updated_at": datetime.utcnow(),
                                }
                            },
                        )
                    except Exception as dberr:
                        logger.error(f"Failed to update call log with appointment details: {dberr}")

                    confirmation_text = result.get("confirmation_text") or (
                        f"The meeting '{appointment.get('title', 'Meeting')}' was scheduled for "
                        f"{appointment.get('start_iso')} {appointment.get('timezone')}."
                    )
                    system_prompt = (
                        "Calendar event scheduled successfully. "
                        "Politely confirm the booking details with the caller. "
                        f"Suggested response: {confirmation_text}"
                    )

                    await openai_ws.send(
                        json.dumps(
                            {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": "system",
                                    "content": [{"type": "input_text", "text": system_prompt}],
                                },
                            }
                        )
                    )
                    await openai_ws.send(json.dumps({"type": "response.create"}))
                    logger.info(
                        "Realtime calendar event booked for call %s (event_id=%s)",
                        call_sid,
                        event_id,
                    )
                except Exception as exc:
                    logger.error(f"Calendar scheduling workflow failed: {exc}")

            scheduling_task = asyncio.create_task(_run_analysis())

            def _clear_task(_future: asyncio.Future) -> None:
                nonlocal scheduling_task
                scheduling_task = None

            scheduling_task.add_done_callback(_clear_task)

        # Determine if we should use OpenAI Realtime API or custom providers
        asr_provider = assistant.get('asr_provider', 'openai')
        tts_provider = assistant.get('tts_provider', 'openai')
        llm_provider = assistant.get('llm_provider', 'openai')

        # Check if using all OpenAI providers (eligible for Realtime API)
        # Accept both 'openai' and 'openai-realtime' as valid OpenAI Realtime providers
        use_openai_realtime = (
            asr_provider == 'openai' and
            tts_provider == 'openai' and
            (llm_provider == 'openai' or llm_provider == 'openai-realtime')
        )

        logger.info(f"[INBOUND] Provider Configuration: ASR={asr_provider}, TTS={tts_provider}, LLM={llm_provider}")
        logger.info(f"[INBOUND] Using OpenAI Realtime API: {use_openai_realtime}")

        # If using custom providers, delegate to custom provider handler
        if not use_openai_realtime:
            logger.info(f"[INBOUND] Routing to custom provider handler for assistant {assistant_id}")
            from app.services.call_handlers.custom_provider_stream import CustomProviderStreamHandler
            from app.utils.assistant_keys import resolve_provider_keys

            # Resolve all necessary API keys
            provider_keys = resolve_provider_keys(db, assistant, assistant_user_id)

            # Ensure we have a key for the configured LLM provider
            llm_api_key = provider_keys.get(llm_provider)
            if llm_provider in ('openai', 'openai-realtime') and not llm_api_key:
                llm_api_key = provider_keys.get('openai')

            if not llm_api_key:
                logger.error(f"No API key found for LLM provider: {llm_provider}")
                await websocket.close(code=1008, reason=f"No API key configured for {llm_provider}")
                return

            openai_api_key = provider_keys.get('openai')

            # Create assistant config for custom provider handler
            assistant_config = {
                'system_message': system_message,
                'voice': voice,
                'temperature': temperature,
                'greeting': call_greeting,
                'asr_provider': asr_provider,
                'tts_provider': tts_provider,
                'llm_provider': llm_provider,
                'asr_language': assistant.get('asr_language', 'en'),
                'asr_model': assistant.get('asr_model'),
                'asr_keywords': assistant.get('asr_keywords', []),
                'tts_model': assistant.get('tts_model'),
                'tts_speed': assistant.get('tts_speed', 1.0),
                'tts_voice': assistant.get('tts_voice'),
                'llm_model': assistant.get('llm_model'),
                'llm_max_tokens': assistant.get('llm_max_tokens', 150),
                'bot_language': assistant.get('bot_language', 'en'),
                'enable_precise_transcript': assistant.get('enable_precise_transcript', False),
                'interruption_threshold': assistant.get('interruption_threshold', 2),
                'response_rate': assistant.get('response_rate', 'balanced'),
                'check_user_online': assistant.get('check_user_online', True),
                'audio_buffer_size': assistant.get('audio_buffer_size', 200),
                'noise_suppression_level': assistant.get('noise_suppression_level', 'medium'),
                'vad_threshold': assistant.get('vad_threshold', 0.5),
                'vad_prefix_padding_ms': assistant.get('vad_prefix_padding_ms', 300),
                'vad_silence_duration_ms': assistant.get('vad_silence_duration_ms', 500),
                'provider_keys': provider_keys,
                # Real-time tool calling (Vapi-like functionality)
                'tools_enabled': assistant.get('tools_enabled', False),
                'tools': assistant.get('tools', []),
                'max_tool_calls_per_turn': assistant.get('max_tool_calls_per_turn', 5),
                'tool_execution_timeout': assistant.get('tool_execution_timeout', 30),
            }

            # Use custom provider stream handler (Twilio platform)
            handler = CustomProviderStreamHandler(
                websocket=websocket,
                assistant_config=assistant_config,
                openai_api_key=openai_api_key,
                call_id="twilio_inbound_custom_provider",
                platform="twilio",
                provider_keys=provider_keys
            )

            try:
                await handler.handle_stream()
            except Exception as e:
                logger.error(f"Error in custom provider handler: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                await websocket.close()
            return

        # OpenAI Realtime API path (existing code)
        # OpenAI Realtime API requires temperature >= 0.6
        if temperature < 0.6:
            logger.warning(f"Temperature {temperature} is below OpenAI minimum. Adjusting to 0.6")
            temperature = 0.6

        # Resolve OpenAI API key - try assistant's key first, then fall back to system env key
        openai_api_key = None
        try:
            openai_api_key, _ = resolve_assistant_api_key(db, assistant, required_provider="openai")
            logger.info(f"[OPENAI_REALTIME] Using assistant's OpenAI API key")
        except HTTPException as exc:
            logger.warning(f"[OPENAI_REALTIME] No assistant API key found: {exc.detail}")

        # Fallback to system OpenAI API key from environment
        if not openai_api_key:
            openai_api_key = settings.openai_api_key
            if openai_api_key:
                logger.info(f"[OPENAI_REALTIME] Using system OpenAI API key from environment")
            else:
                logger.error(f"[OPENAI_REALTIME] No OpenAI API key available (neither assistant nor system)")
                await websocket.close(code=1008, reason="No OpenAI API key configured")
                return

        # Determine if we should use OpenAI Realtime API or custom providers
        asr_provider = assistant.get('asr_provider', 'openai')
        tts_provider = assistant.get('tts_provider', 'openai')
        llm_provider = assistant.get('llm_provider', 'openai')

        # Check if using all OpenAI providers (eligible for Realtime API)
        # Accept both 'openai' and 'openai-realtime' as valid OpenAI Realtime providers
        use_openai_realtime = (
            asr_provider == 'openai' and
            tts_provider == 'openai' and
            (llm_provider == 'openai' or llm_provider == 'openai-realtime')
        )

        logger.info(f"[INBOUND] Provider Configuration: ASR={asr_provider}, TTS={tts_provider}, LLM={llm_provider}")
        logger.info(f"[INBOUND] Using OpenAI Realtime API: {use_openai_realtime}")

        # If using custom providers, delegate to custom provider handler
        if not use_openai_realtime:
            logger.info(f"[INBOUND] Routing to custom provider handler for assistant {assistant_id}")
            from app.services.call_handlers.custom_provider_stream import CustomProviderStreamHandler
            from app.utils.assistant_keys import resolve_provider_keys

            # Resolve all necessary API keys
            provider_keys = resolve_provider_keys(db, assistant, assistant_user_id)

            # Ensure we have a key for the configured LLM provider
            llm_api_key = provider_keys.get(llm_provider)
            if llm_provider in ('openai', 'openai-realtime') and not llm_api_key:
                llm_api_key = provider_keys.get('openai') or openai_api_key

            if not llm_api_key:
                logger.error(f"No API key found for LLM provider: {llm_provider}")
                await websocket.close(code=1008, reason=f"No API key configured for {llm_provider}")
                return

            # Create assistant config for custom provider handler
            assistant_config = {
                'system_message': system_message,
                'voice': voice,
                'temperature': temperature,
                'greeting': call_greeting,
                'asr_provider': asr_provider,
                'tts_provider': tts_provider,
                'llm_provider': llm_provider,
                'asr_language': assistant.get('asr_language', 'en'),
                'asr_model': assistant.get('asr_model'),
                'asr_keywords': assistant.get('asr_keywords', []),
                'tts_model': assistant.get('tts_model'),
                'tts_speed': assistant.get('tts_speed', 1.0),
                'tts_voice': assistant.get('tts_voice'),
                'llm_model': assistant.get('llm_model'),
                'llm_max_tokens': assistant.get('llm_max_tokens', 150),
                'bot_language': bot_language,
                'enable_precise_transcript': assistant.get('enable_precise_transcript', False),
                'interruption_threshold': assistant.get('interruption_threshold', 2),
                'response_rate': assistant.get('response_rate', 'balanced'),
                'check_user_online': assistant.get('check_user_online', True),
                'audio_buffer_size': assistant.get('audio_buffer_size', 200),
                'noise_suppression_level': assistant.get('noise_suppression_level', 'medium'),
                'vad_threshold': assistant.get('vad_threshold', 0.5),
                'vad_prefix_padding_ms': assistant.get('vad_prefix_padding_ms', 300),
                'vad_silence_duration_ms': assistant.get('vad_silence_duration_ms', 500),
                'provider_keys': provider_keys,  # Pass all resolved keys
                # Real-time tool calling (Vapi-like functionality)
                'tools_enabled': assistant.get('tools_enabled', False),
                'tools': assistant.get('tools', []),
                'max_tool_calls_per_turn': assistant.get('max_tool_calls_per_turn', 5),
                'tool_execution_timeout': assistant.get('tool_execution_timeout', 30),
            }

            # Use custom provider stream handler (Twilio platform for inbound)
            handler = CustomProviderStreamHandler(
                websocket=websocket,
                assistant_config=assistant_config,
                openai_api_key=llm_api_key,  # Use the resolved LLM key
                call_id="twilio_inbound_custom_provider",  # Twilio will provide call_sid via websocket
                platform="twilio",
                provider_keys=provider_keys
            )

            try:
                await handler.handle_stream()
            except Exception as e:
                logger.error(f"[INBOUND] Error in custom provider handler: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                await websocket.close()
            return

        # OpenAI Realtime API path (existing code)
        # Get the LLM model to use for OpenAI Realtime API
        llm_model = assistant.get('llm_model', 'gpt-4o-mini-realtime-preview')
        logger.info(f"[INBOUND] Using OpenAI Realtime API - Model: {llm_model}, Voice: {voice}, Temperature: {temperature}")

        # Connect to OpenAI WebSocket using the assistant's API key and selected model
        # Note: temperature is set via session.update, not in URL
        # Increased timeout to handle connection delays
        try:
            openai_ws = await websockets.connect(
                f"wss://api.openai.com/v1/realtime?model={llm_model}",
                additional_headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "OpenAI-Beta": "realtime=v1"
                },
                open_timeout=30,  # Increased from default 10s to 30s
                close_timeout=10,
                ping_interval=20,
                ping_timeout=20
            )
        except Exception as ws_error:
            logger.error(f"[OPENAI_REALTIME] Failed to connect to OpenAI Realtime API: {ws_error}")
            logger.error(f"[OPENAI_REALTIME] Model: {llm_model}, API Key prefix: {openai_api_key[:10]}...")
            await websocket.close(code=1008, reason=f"Failed to connect to OpenAI Realtime API: {str(ws_error)}")
            return

        try:
            # Initialize session with interruption handling enabled
            # NOTE: send_session_update now calls send_initial_conversation_item internally
            # This matches the original pattern from CallTack_IN_out/inbound_calls.py line 223

            # Get VAD settings from assistant config for noise suppression
            vad_threshold = assistant_config.get('vad_threshold', 0.5)
            vad_prefix_padding_ms = assistant_config.get('vad_prefix_padding_ms', 300)
            vad_silence_duration_ms = assistant_config.get('vad_silence_duration_ms', 500)

            await send_session_update(
                openai_ws,
                system_message,
                voice,
                temperature,
                enable_interruptions=True,
                greeting_text=call_greeting,
                max_response_output_tokens="inf",  # Allow unlimited response length for natural conversation
                vad_threshold=vad_threshold,  # Noise sensitivity control
                vad_prefix_padding_ms=vad_prefix_padding_ms,  # Speech start padding
                vad_silence_duration_ms=vad_silence_duration_ms  # Silence detection for noise handling
            )

            # Connection specific state
            stream_sid = None
            latest_media_timestamp = 0
            last_assistant_item = None
            mark_queue = []
            response_start_timestamp_twilio = None
            call_sid = None
            awaiting_hangup_confirmation = False
            pending_hangup_goodbye = False
            hangup_completed = False

            # Initialize background audio mixer from assistant config
            bg_audio_mixer = create_mixer_from_assistant(assistant)
            if bg_audio_mixer.enabled:
                logger.info(f"[INBOUND] Background audio enabled: type={bg_audio_mixer.audio_type}, volume={bg_audio_mixer.volume}")

            async def receive_from_twilio():
                """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
                nonlocal stream_sid, latest_media_timestamp, call_sid, hangup_completed
                try:
                    async for message in websocket.iter_text():
                        if hangup_completed:
                            logger.info("Hangup already completed; stopping Twilio receive loop")
                            break
                        data = json.loads(message)
                        if data['event'] == 'media' and openai_ws.state.name == 'OPEN':
                            latest_media_timestamp = int(data['media']['timestamp'])
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                        elif data['event'] == 'start':
                            start_info = data['start']
                            stream_sid = start_info.get('streamSid')
                            call_sid = start_info.get('callSid') or start_info.get('call_sid') or call_sid

                            # Extract caller and recipient information
                            caller_number = start_info.get('customParameters', {}).get('From') or start_info.get('from')
                            to_number = start_info.get('customParameters', {}).get('To') or start_info.get('to')
                            logger.info(f"Incoming stream started {stream_sid} from {caller_number} to {to_number}")

                            # Look up caller name from database (leads or contacts)
                            caller_name = None
                            if caller_number and assistant_user_id:
                                try:
                                    # Check leads collection
                                    lead = db['leads'].find_one({
                                        "user_id": assistant_user_id,
                                        "phone_number": caller_number
                                    })
                                    if lead:
                                        caller_name = lead.get('name') or lead.get('first_name')
                                        logger.info(f"Found caller in leads: {caller_name}")

                                    # If not found, check contacts
                                    if not caller_name:
                                        contact = db['contacts'].find_one({
                                            "user_id": assistant_user_id,
                                            "phone": caller_number
                                        })
                                        if contact:
                                            caller_name = contact.get('name')
                                            logger.info(f"Found caller in contacts: {caller_name}")
                                except Exception as e:
                                    logger.error(f"Error looking up caller: {e}")

                            # Update system message with caller info if available
                            if caller_name:
                                enhanced_system_message = f"{system_message}\n\nIMPORTANT: The caller is {caller_name}. Greet them by name and use their name naturally during the conversation."
                                # Send updated session with caller context
                                await send_session_update(
                                    openai_ws,
                                    enhanced_system_message,
                                    voice,
                                    temperature,
                                    enable_interruptions=True,
                                    greeting_text=f"Hello {caller_name}! {call_greeting.replace('Hello!', '').strip()}",
                                    max_response_output_tokens="inf",  # Allow unlimited response length
                                    vad_threshold=vad_threshold,
                                    vad_prefix_padding_ms=vad_prefix_padding_ms,
                                    vad_silence_duration_ms=vad_silence_duration_ms
                                )
                                logger.info(f"Updated greeting for {caller_name}")

                            response_start_timestamp_twilio = None
                            latest_media_timestamp = 0
                            last_assistant_item = None

                            # Create call log entry for this inbound call
                            if call_sid:
                                try:
                                    # Build voice configuration info
                                    voice_config = {
                                        "asr_provider": assistant.get('asr_provider', 'openai'),
                                        "asr_model": assistant.get('asr_model'),
                                        "asr_language": assistant.get('asr_language', 'en'),
                                        "tts_provider": assistant.get('tts_provider', 'openai'),
                                        "tts_model": assistant.get('tts_model'),
                                        "tts_voice": assistant.get('tts_voice'),
                                        "llm_provider": assistant.get('llm_provider', 'openai'),
                                        "llm_model": assistant.get('llm_model'),
                                        "llm_max_tokens": assistant.get('llm_max_tokens', 150)
                                    }

                                    call_log_entry = {
                                        "call_sid": call_sid,
                                        "stream_sid": stream_sid,
                                        "assistant_id": assistant_id,
                                        "user_id": assistant_user_id,
                                        "from_number": caller_number,
                                        "to_number": to_number,
                                        "direction": "inbound",
                                        "status": "in-progress",
                                        "call_type": "inbound",
                                        "call_status": "in-progress",
                                        "voice_config": voice_config,  # Add voice provider configuration
                                        "started_at": datetime.utcnow(),
                                        "created_at": datetime.utcnow()
                                    }
                                    db['call_logs'].insert_one(call_log_entry)
                                    logger.info(f"Created call log for inbound call {call_sid} with voice config")
                                except Exception as log_err:
                                    logger.error(f"Error creating call log: {log_err}")
                        elif data['event'] == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)
                except WebSocketDisconnect:
                    logger.info("Client disconnected.")
                    if openai_ws.state.name == 'OPEN':
                        await openai_ws.close()

            async def send_to_twilio():
                """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
                nonlocal awaiting_hangup_confirmation, pending_hangup_goodbye, hangup_completed
                nonlocal conversation_history, appointment_scheduled, scheduling_task

                response_transcript_buffers: Dict[str, str] = {}

                async def finalize_call():
                    nonlocal hangup_completed, pending_hangup_goodbye
                    if hangup_completed:
                        return
                    hangup_completed = True
                    pending_hangup_goodbye = False
                    if twilio_client and call_sid:
                        try:
                            twilio_client.calls(call_sid).update(status="completed")
                            logger.info(f"Requested Twilio to end call {call_sid}")
                        except TwilioRestException as twilio_error:
                            logger.error(f"Twilio error ending call {call_sid}: {twilio_error}")
                        except Exception as generic_error:
                            logger.error(f"Unexpected error ending call {call_sid}: {generic_error}")
                    else:
                        logger.warning("Cannot end call automatically - Twilio client or call SID missing")

                    try:
                        if openai_ws.state.name == 'OPEN':
                            await openai_ws.close()
                    except Exception as close_err:
                        logger.debug(f"Error closing OpenAI websocket: {close_err}")

                    try:
                        await websocket.close(code=1000, reason="Call ended by assistant confirmation")
                    except Exception as ws_err:
                        logger.debug(f"Error closing Twilio websocket: {ws_err}")

                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)

                        if response['type'] in LOG_EVENT_TYPES:
                            logger.info(f"Received event: {response['type']}")
                            # Log error details if it's an error
                            if response['type'] == 'error':
                                logger.error(f"OpenAI Error: {json.dumps(response, indent=2)}")
                            # Log response.done details for debugging
                            if response['type'] == 'response.done':
                                resp_data = response.get('response', {})
                                logger.info(f"Response done - Status: {resp_data.get('status')}, "
                                          f"Output items: {len(resp_data.get('output', []))}")

                                if pending_hangup_goodbye and resp_data.get('status') == 'completed':
                                    logger.info("Final goodbye response delivered; ending call now")
                                    await finalize_call()
                                    return

                        # Log ALL events for debugging audio issues
                        if response['type'] not in LOG_EVENT_TYPES:
                            logger.debug(f"Received event (not in LOG_EVENT_TYPES): {response['type']}")

                        # Handle response creation
                        if response.get('type') == 'response.created':
                            response_data = response.get('response', {})
                            logger.info(f"Response created: {response_data.get('id')}")
                            logger.info(f"Response modalities: {response_data.get('modalities', [])}")
                            logger.info(f"Response output: {list(response_data.get('output', []))[:2]}")  # First 2 items

                        # Handle audio delta (AI speaking)
                        if response.get('type') == 'response.audio.delta' and 'delta' in response:
                            audio_payload = response['delta']

                            # Mix background audio if enabled
                            if bg_audio_mixer.enabled:
                                audio_payload = bg_audio_mixer.mix_audio_base64(audio_payload)

                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            await websocket.send_json(audio_delta)

                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp
                                if SHOW_TIMING_MATH:
                                    logger.info(f"Setting start timestamp for new response: {response_start_timestamp_twilio}ms")

                            # Update last_assistant_item safely
                            if response.get('item_id'):
                                last_assistant_item = response['item_id']

                            await send_mark(websocket, stream_sid, mark_queue)

                        # Handle audio transcript for debugging
                        if response.get('type') == 'response.audio_transcript.delta':
                            delta_text = response.get('delta', '')
                            logger.info(f"AI transcript: {delta_text}")
                            resp_id = response.get('response_id')
                            if resp_id and delta_text:
                                response_transcript_buffers[resp_id] = (
                                    response_transcript_buffers.get(resp_id, "") + delta_text
                                )

                        if response.get('type') == 'response.audio_transcript.done':
                            resp_id = response.get('response_id')
                            transcript_text = ""
                            if resp_id and resp_id in response_transcript_buffers:
                                transcript_text = response_transcript_buffers.pop(resp_id)
                            transcript_text = transcript_text or response.get('transcript', '')
                            if transcript_text:
                                conversation_history.append({"role": "assistant", "text": transcript_text})
                                if len(conversation_history) > 30:
                                    conversation_history = conversation_history[-30:]

                                # Save real-time transcript to database
                                try:
                                    if call_sid:
                                        # Build full transcript from conversation history
                                        full_transcript = "\n\n".join([
                                            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['text']}"
                                            for msg in conversation_history
                                        ])

                                        db["call_logs"].update_one(
                                            {"call_sid": call_sid},
                                            {"$set": {
                                                "transcript": full_transcript,
                                                "transcript_updated_at": datetime.utcnow()
                                            }}
                                        )
                                except Exception as transcript_err:
                                    logger.error(f"Error saving assistant transcript: {transcript_err}")

                                await maybe_schedule_from_conversation("assistant_transcript")

                        # Handle interruption when user starts speaking
                        if response.get('type') == 'input_audio_buffer.speech_started':
                            logger.info("Speech started detected - handling interruption")
                            if last_assistant_item:
                                logger.info(f"Interrupting response with id: {last_assistant_item}")
                                last_assistant_item, response_start_timestamp_twilio = await handle_interruption(
                                    openai_ws,
                                    websocket,
                                    stream_sid,
                                    last_assistant_item,
                                    response_start_timestamp_twilio,
                                    latest_media_timestamp,
                                    mark_queue,
                                    SHOW_TIMING_MATH
                                )

                        # When user's speech is transcribed, check knowledge base
                        if response['type'] == 'conversation.item.created':
                            item = response.get('item', {})
                            # Check if this is a user message with transcript
                            if item.get('role') == 'user' and item.get('type') == 'message':
                                content_list = item.get('content', [])
                                for content in content_list:
                                    # Check for input_audio with transcript (new API format)
                                    if content.get('type') == 'input_audio':
                                        transcript = content.get('transcript', '')
                                        if transcript:
                                            logger.info(f"User said: {transcript}")
                                            hangup_handled = False
                                            if not hangup_completed:
                                                if awaiting_hangup_confirmation:
                                                    if transcript_confirms_hangup(transcript) or transcript_has_hangup_intent(transcript):
                                                        logger.info("Caller confirmed hangup request.")
                                                        awaiting_hangup_confirmation = False
                                                        pending_hangup_goodbye = True
                                                        await send_call_end_acknowledgement(openai_ws)
                                                        hangup_handled = True
                                                    elif transcript_denies_hangup(transcript):
                                                        logger.info("Caller declined hangup; continuing conversation.")
                                                        awaiting_hangup_confirmation = False
                                                        await send_call_continue_acknowledgement(openai_ws)
                                                        hangup_handled = True
                                                elif transcript_has_hangup_intent(transcript):
                                                    logger.info("Detected caller intent to end call; requesting confirmation.")
                                                    awaiting_hangup_confirmation = True
                                                    await request_call_end_confirmation(openai_ws)
                                                    hangup_handled = True

                                            if hangup_handled or pending_hangup_goodbye:
                                                continue

                                            conversation_history.append({"role": "user", "text": transcript})
                                            if len(conversation_history) > 30:
                                                conversation_history = conversation_history[-30:]

                                            # Save real-time transcript to database
                                            try:
                                                if call_sid:
                                                    # Build full transcript from conversation history
                                                    full_transcript = "\n\n".join([
                                                        f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['text']}"
                                                        for msg in conversation_history
                                                    ])

                                                    db["call_logs"].update_one(
                                                        {"call_sid": call_sid},
                                                        {"$set": {
                                                            "transcript": full_transcript,
                                                            "transcript_updated_at": datetime.utcnow()
                                                        }}
                                                    )
                                            except Exception as transcript_err:
                                                logger.error(f"Error saving transcript: {transcript_err}")

                                            await maybe_schedule_from_conversation("user_transcript")

                                            # Search knowledge base
                                            try:
                                                kb_context = conversational_rag.search_conversation_context(
                                                    assistant_id=assistant_id,
                                                    query=transcript,
                                                    api_key=openai_api_key,
                                                    top_k=3,
                                                    relevance_threshold=0.7
                                                )
                                                if kb_context:
                                                    logger.info("Found relevant knowledge base context")
                                                    await inject_knowledge_base_context(openai_ws, kb_context)
                                            except Exception as e:
                                                logger.error(f"Error searching knowledge base: {e}")

                except Exception as e:
                    logger.error(f"Error in send_to_twilio: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            await asyncio.gather(receive_from_twilio(), send_to_twilio())
        finally:
            # Close OpenAI WebSocket connection
            try:
                await openai_ws.close()
            except:
                pass

    except WebSocketDisconnect:
        logger.info(f"Client disconnected normally for assistant: {assistant_id}")
    except Exception as error:
        import traceback
        logger.error(f"Error in media stream for assistant {assistant_id}: {str(error)}")
        logger.error(traceback.format_exc())
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass  # WebSocket might already be closed
    finally:
        # Ensure cleanup happens
        logger.info(f"Cleaning up resources for assistant: {assistant_id}")
        # WebSocket and OpenAI connections will be closed by context managers


@router.api_route("/recording-status", methods=["GET", "POST"])
async def handle_recording_status(request: Request):
    """
    Callback endpoint for Twilio recording status updates.
    Saves recording URL to database when recording is completed.
    Triggers post-call processing for appointment booking.

    Twilio sends these parameters:
    - RecordingSid: Unique recording identifier
    - RecordingUrl: URL to download the recording
    - RecordingStatus: completed, in-progress, absent
    - RecordingDuration: Length of recording in seconds
    - CallSid: Call identifier
    - AccountSid: Twilio account SID
    """
    try:
        # Get form data from Twilio
        if request.method == "POST":
            form_data = await request.form()
        else:
            form_data = request.query_params

        recording_sid = form_data.get('RecordingSid')
        recording_url = form_data.get('RecordingUrl')
        recording_status = form_data.get('RecordingStatus')
        recording_duration = form_data.get('RecordingDuration')
        call_sid = form_data.get('CallSid')

        logger.info(f"Recording status: {recording_status} for call {call_sid}")
        logger.info(f"Recording URL: {recording_url}")

        if recording_status == 'completed' and call_sid:
            # Update call log with recording information
            db = Database.get_db()
            call_logs_collection = db['call_logs']

            update_data = {
                'recording_sid': recording_sid,
                'recording_url': recording_url,
                'recording_duration': int(recording_duration) if recording_duration else None,
                'recording_status': recording_status,
                'updated_at': datetime.utcnow()
            }

            result = call_logs_collection.update_one(
                {'call_sid': call_sid},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.info(f"Updated call log with recording URL for call {call_sid}")

                # Get the call log to find assistant and user info
                call_log = call_logs_collection.find_one({'call_sid': call_sid})

                if call_log and recording_url:
                    assistant_id = call_log.get('assistant_id')

                    if assistant_id:
                        # Trigger post-call processing for appointment booking (async optimized)
                        try:
                            from app.services.async_inbound_post_call_processor import AsyncInboundPostCallProcessor

                            processor = AsyncInboundPostCallProcessor()
                            # Process in background to avoid blocking the webhook response
                            asyncio.create_task(
                                processor.process_inbound_call(
                                    call_sid=call_sid,
                                    assistant_id=assistant_id,
                                    recording_url=recording_url
                                )
                            )
                            logger.info(f"Triggered async post-call processing for inbound call {call_sid}")
                        except ImportError as e:
                            logger.warning(f"Async post-call processor not available: {e}")
                        except Exception as e:
                            logger.error(f"Error triggering post-call processing: {e}")
            else:
                logger.warning(f"Call log not found for call_sid: {call_sid}")

        return {"status": "success", "message": "Recording status received"}

    except Exception as error:
        logger.error(f"Error handling recording status: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(error)}


@router.api_route("/transcription-status", methods=["GET", "POST"])
async def handle_transcription_status(request: Request):
    """
    Callback endpoint for Twilio transcription status updates.
    Saves transcription text to database when transcription is completed.

    Twilio sends these parameters:
    - TranscriptionSid: Unique transcription identifier
    - TranscriptionText: The full transcription
    - TranscriptionStatus: completed, in-progress, failed
    - RecordingSid: Associated recording SID
    - CallSid: Call identifier
    - TranscriptionUrl: URL to fetch transcription
    """
    try:
        # Get form data from Twilio
        if request.method == "POST":
            form_data = await request.form()
        else:
            form_data = request.query_params

        transcription_sid = form_data.get('TranscriptionSid')
        transcription_text = form_data.get('TranscriptionText')
        transcription_status = form_data.get('TranscriptionStatus')
        recording_sid = form_data.get('RecordingSid')
        call_sid = form_data.get('CallSid')
        transcription_url = form_data.get('TranscriptionUrl')

        logger.info(f"Transcription status: {transcription_status} for call {call_sid}")

        if transcription_status == 'completed' and call_sid and transcription_text:
            # Update call log with transcription
            db = Database.get_db()
            call_logs_collection = db['call_logs']

            update_data = {
                'transcription_sid': transcription_sid,
                'transcription_text': transcription_text,
                'transcription_url': transcription_url,
                'transcription_status': transcription_status,
                'updated_at': datetime.utcnow()
            }

            result = call_logs_collection.update_one(
                {'call_sid': call_sid},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.info(f"Updated call log with transcription for call {call_sid}")
                logger.info(f"Transcription preview: {transcription_text[:100]}...")
            else:
                logger.warning(f"Call log not found for call_sid: {call_sid}")

        return {"status": "success", "message": "Transcription status received"}

    except Exception as error:
        logger.error(f"Error handling transcription status: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(error)}
