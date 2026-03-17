import os
import json
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
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
from app.services.calendar_service import CalendarService
from app.services.calendar_intent_service import CalendarIntentService
from app.utils.background_audio import BackgroundAudioMixer, create_mixer_from_assistant
from app.models.inbound_calls import InboundCallConfig, InboundCallResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

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

        # Route to optimized stream handler (Deepgram ASR + OpenAI LLM + ElevenLabs TTS)
        websocket_url = f'wss://{host}/api/inbound-calls/stream/custom/{assistant_id}'
        logger.info(f"[INBOUND] Stream URL: {websocket_url}")

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

        logger.info(f"[INBOUND_STREAM] Assistant: {assistant.get('name', 'Unknown')}")

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
            "voice": assistant.get("voice", "alloy"),
            "tts_voice": assistant.get("tts_voice", assistant.get("voice", "alloy")),
            "temperature": assistant.get("temperature", 0.7),
            "asr_provider": "deepgram",
            "asr_model": "nova-2",
            "asr_language": assistant.get("asr_language", "en"),
            "asr_keywords": assistant.get("asr_keywords", []),
            "tts_provider": "elevenlabs",
            "tts_model": "eleven_flash_v2_5",
            "tts_speed": assistant.get("tts_speed", 1.0),
            "llm_provider": "openai",
            "llm_model": "gpt-4-turbo",
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
