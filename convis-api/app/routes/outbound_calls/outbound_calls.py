import os
import json
import asyncio
import re
import websockets
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketDisconnect
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
from app.models.outbound_calls import (
    OutboundCallRequest,
    OutboundCallResponse,
    CheckNumberResponse,
    OutboundCallConfig
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Note: Twilio credentials are now fetched per-user from the database
# This ensures proper security and multi-tenancy support

# Configuration for interruption handling
SHOW_TIMING_MATH = False

@router.get("/", response_class=JSONResponse)
async def outbound_calls_index():
    """Health check for outbound calls service"""
    return {
        "message": "Outbound calls service is running",
        "note": "Twilio credentials are fetched per-user from database"
    }

@router.get("/config/{assistant_id}", response_model=OutboundCallResponse, status_code=status.HTTP_200_OK)
async def get_outbound_call_config(assistant_id: str):
    """
    Get AI assistant configuration for outbound calls

    Args:
        assistant_id: The AI assistant ID to fetch configuration for

    Returns:
        OutboundCallResponse: Configuration details

    Raises:
        HTTPException: If assistant not found or error occurs
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']
        campaigns_collection = db['campaigns']

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

        return OutboundCallResponse(
            message="Configuration retrieved successfully",
            assistant_id=str(assistant['_id']),
            status="ready"
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

@router.get("/call-status/{call_sid}/{user_id}", status_code=status.HTTP_200_OK)
async def get_call_status(call_sid: str, user_id: str):
    """
    Get the current status of an active call from Twilio.

    Args:
        call_sid: Twilio Call SID
        user_id: User ID to fetch Twilio credentials

    Returns:
        Call status information (ringing, in-progress, completed, etc.)
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        provider_connections_collection = db['provider_connections']
        call_logs_collection = db['call_logs']

        # Validate user
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        user = users_collection.find_one({"_id": user_obj_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get Twilio connection
        twilio_connection = provider_connections_collection.find_one({
            "user_id": user_obj_id,
            "provider": "twilio"
        })

        if not twilio_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Twilio connection found"
            )

        # Initialize Twilio client
        account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
        if not account_sid or not auth_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Twilio credentials are missing or invalid. Please reconnect Twilio."
            )

        twilio_client = Client(account_sid, auth_token)

        # Fetch call status from Twilio
        call = twilio_client.calls(call_sid).fetch()

        # Update database with latest status
        call_logs_collection.update_one(
            {"call_sid": call_sid, "user_id": user_obj_id},
            {
                "$set": {
                    "status": call.status,
                    "duration": call.duration,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return {
            "call_sid": call.sid,
            "status": call.status,
            "direction": call.direction,
            "from": call.from_formatted,
            "to": call.to_formatted,
            "duration": call.duration,
            "start_time": call.start_time.isoformat() if call.start_time else None,
            "end_time": call.end_time.isoformat() if call.end_time else None
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error fetching call status: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch call status: {str(error)}"
        )


@router.post("/hangup/{call_sid}/{user_id}", status_code=status.HTTP_200_OK)
async def hangup_call(call_sid: str, user_id: str):
    """
    Hang up an active call.

    Args:
        call_sid: Twilio Call SID
        user_id: User ID to fetch Twilio credentials

    Returns:
        Success message
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        provider_connections_collection = db['provider_connections']
        call_logs_collection = db['call_logs']

        # Validate user
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        user = users_collection.find_one({"_id": user_obj_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get Twilio connection
        twilio_connection = provider_connections_collection.find_one({
            "user_id": user_obj_id,
            "provider": "twilio"
        })

        if not twilio_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Twilio connection found"
            )

        # Initialize Twilio client
        account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
        if not account_sid or not auth_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Twilio credentials are missing or invalid. Please reconnect Twilio."
            )

        twilio_client = Client(account_sid, auth_token)

        # Hang up the call
        call = twilio_client.calls(call_sid).update(status='completed')

        # Update database
        call_logs_collection.update_one(
            {"call_sid": call_sid, "user_id": user_obj_id},
            {
                "$set": {
                    "status": "completed",
                    "updated_at": datetime.utcnow()
                }
            }
        )

        logger.info(f"Call {call_sid} hung up successfully")

        return {
            "message": "Call ended successfully",
            "call_sid": call_sid,
            "status": call.status
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error hanging up call: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to hang up call: {str(error)}"
        )


@router.post("/check-number/{user_id}", response_model=CheckNumberResponse, status_code=status.HTTP_200_OK)
async def check_phone_number(user_id: str, phone_number: str):
    """
    Check if a phone number is allowed to be called.

    Validates against:
    - Twilio verified outgoing caller IDs
    - Twilio incoming phone numbers (owned numbers)

    Args:
        user_id: User ID to fetch Twilio credentials
        phone_number: Phone number in E.164 format (e.g., +1234567890)

    Returns:
        CheckNumberResponse: Validation result
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        provider_connections_collection = db['provider_connections']

        # Validate user
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        user = users_collection.find_one({"_id": user_obj_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get Twilio connection
        twilio_connection = provider_connections_collection.find_one({
            "user_id": user_obj_id,
            "provider": "twilio"
        })

        if not twilio_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Twilio connection found. Please connect Twilio first."
            )

        account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
        if not account_sid or not auth_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Twilio credentials are missing or invalid. Please reconnect Twilio."
            )

        # Initialize Twilio client with user's credentials
        twilio_client = Client(account_sid, auth_token)

        # Check if number is allowed
        is_allowed = await check_number_allowed(twilio_client, phone_number)

        return CheckNumberResponse(
            phone_number=phone_number,
            is_allowed=is_allowed,
            message="Number is allowed" if is_allowed else "Number is not verified or owned"
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error checking phone number: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check phone number: {str(error)}"
        )

@router.post("/make-call/{assistant_id}", response_model=OutboundCallResponse, status_code=status.HTTP_200_OK)
async def make_outbound_call(assistant_id: str, request: OutboundCallRequest):
    """
    Initiate an outbound call using the specified AI assistant.

    Args:
        assistant_id: The AI assistant ID to use for this call
        request: OutboundCallRequest with phone_number

    Returns:
        OutboundCallResponse: Call details including call_sid

    Raises:
        HTTPException: If validation fails or error occurs
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']
        users_collection = db['users']
        provider_connections_collection = db['provider_connections']

        logger.info(f"Initiating outbound call for assistant: {assistant_id}")

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

        # Get user_id from assistant
        user_obj_id = assistant.get('user_id')
        if not user_obj_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assistant is not associated with a user"
            )

        # Validate user exists
        user = users_collection.find_one({"_id": user_obj_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get Twilio connection for this user
        twilio_connection = provider_connections_collection.find_one({
            "user_id": user_obj_id,
            "provider": "twilio"
        })

        if not twilio_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Twilio connection found. Please connect Twilio in your account settings."
            )

        account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
        if not account_sid or not auth_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Twilio credentials are missing or invalid. Please reconnect Twilio."
            )

        # Initialize Twilio client with user's credentials
        twilio_client = Client(account_sid, auth_token)

        # Validate phone number format (basic E.164 check)
        phone_number = request.phone_number.strip()
        if not re.match(r'^\+[1-9]\d{1,14}$', phone_number):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid phone number format. Use E.164 format (e.g., +1234567890)"
            )

        # Check if number is allowed to be called
        is_allowed = await check_number_allowed(twilio_client, phone_number)
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"The number {phone_number} is not recognized as a valid outgoing number or caller ID. "
                    "Please verify the number in your Twilio console first."
                )
            )

        try:
            llm_provider = assistant.get('llm_provider', 'openai')
            openai_api_key, _ = resolve_assistant_api_key(db, assistant, required_provider=llm_provider)
        except HTTPException as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)

        # Get the phone number to call FROM (the one assigned to this assistant)
        phone_numbers_collection = db['phone_numbers']
        phone_number_doc = phone_numbers_collection.find_one({
            "assigned_assistant_id": assistant_obj_id,
            "user_id": user_obj_id,
            "status": "active"
        })

        if not phone_number_doc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No phone number assigned to this assistant"
            )

        phone_number_from = phone_number_doc["phone_number"]
        logger.info(f"Using assigned phone number: {phone_number_from}")

        # Ensure API_BASE_URL is configured
        if not settings.api_base_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API_BASE_URL not configured in .env file"
            )

        # Clean domain (remove protocols and trailing slashes)
        domain = re.sub(r'(^\w+:|^)\/\/|\/+$', '', settings.api_base_url)

        # Create TwiML to connect to media stream with custom parameters
        # Note: Recording with transcription is enabled via the record parameter in calls.create()
        # and will be handled by the recording_status_callback
        outbound_twiml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response>'
            f'<Connect>'
            f'<Stream url="wss://{domain}/api/outbound-calls/media-stream/{assistant_id}">'
            f'<Parameter name="to_number" value="{phone_number}" />'
            f'</Stream>'
            f'</Connect>'
            f'</Response>'
        )

        logger.info(f"Calling {phone_number} from {phone_number_from}")
        logger.info(f"WebSocket URL: wss://{domain}/api/outbound-calls/media-stream/{assistant_id}")

        # Make the call with recording enabled
        call = twilio_client.calls.create(
            from_=phone_number_from,
            to=phone_number,
            twiml=outbound_twiml,
            record=True,  # Enable call recording
            recording_status_callback=f'{settings.api_base_url}/api/outbound-calls/recording-status',
            recording_status_callback_method='POST',
            recording_status_callback_event=['completed']  # Get callback when recording is complete
            # Note: Transcription will be requested via Recordings API in the recording-status callback
        )

        logger.info(f"Call created with SID: {call.sid}")

        # Build voice configuration info for tracking
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

        # Store call in database for tracking
        call_logs_collection = db['call_logs']
        call_log = {
            "user_id": user_obj_id,
            "assistant_id": assistant_obj_id,
            "assistant_name": assistant.get("name"),
            "phone_number": phone_number_doc["_id"],
            "phone_number_value": phone_number_from,
            "call_sid": call.sid,
            "direction": "outbound",
            "from_number": phone_number_from,
            "to_number": phone_number,
            "status": "initiated",
            "voice_config": voice_config,  # Add voice provider configuration
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        call_logs_collection.insert_one(call_log)
        logger.info(f"Call log stored for SID: {call.sid} with voice config: {voice_config}")

        return OutboundCallResponse(
            message="Outbound call initiated successfully",
            call_sid=call.sid,
            status="initiated",
            assistant_id=assistant_id
        )

    except HTTPException:
        raise
    except TwilioRestException as e:
        logger.error(f"Twilio error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Twilio error: {e.msg}"
        )
    except Exception as error:
        import traceback
        logger.error(f"Error making outbound call: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to make outbound call: {str(error)}"
        )

@router.websocket("/media-stream/{assistant_id}")
async def handle_media_stream(websocket: WebSocket, assistant_id: str):
    """
    Handle WebSocket connections between Twilio and OpenAI for outbound calls.
    This is the same as inbound but triggered by outbound call initiation.

    Args:
        websocket: WebSocket connection
        assistant_id: The AI assistant ID to use for this call
    """
    logger.info(f"Outbound call media stream connected for assistant: {assistant_id}")
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

        logger.info(f"[OUTBOUND] Voice mode: {voice_mode}")

        # Resolve LLM API key for the assistant (needed for both modes)
        try:
            llm_provider = assistant.get('llm_provider', 'openai')
            openai_api_key, _ = resolve_assistant_api_key(db, assistant, required_provider=llm_provider)
        except HTTPException as exc:
            logger.error(f"Failed to resolve LLM API key: {exc.detail}")
            await websocket.close(code=1008, reason=f"API key configuration error: {exc.detail}")
            return

        # Route to appropriate handler based on voice mode
        if voice_mode == 'custom':
            # OPTIMIZED: Use low-latency streaming pipeline for custom provider mode
            # Supports both "optimized" (sentence-by-sentence) and "ultra" (word-by-word) modes
            logger.info("[OUTBOUND] ⚡ Using low-latency pipeline for custom provider mode")

            try:
                from app.services.call_handlers.optimized_stream_handler import handle_optimized_stream
                from app.services.call_handlers.ultra_low_latency_handler import handle_ultra_low_latency_stream
                from app.utils.assistant_keys import resolve_provider_keys

                # Resolve all provider keys
                provider_keys = resolve_provider_keys(db, assistant, assistant_user_id)
                logger.info(f"[OUTBOUND] ✅ Resolved provider keys: {list(provider_keys.keys())}")

                # ============ CALENDAR CONFIGURATION ============
                # Same calendar setup as realtime API for consistency
                timezone_hint = (
                    assistant.get('timezone')
                    or "America/New_York"
                )

                calendar_enabled = False
                default_calendar_provider = "google"
                calendar_account_id_for_booking = None
                calendar_account_ids_list = []
                calendar_accounts_collection = db["calendar_accounts"]

                # Check for NEW multi-calendar support
                assistant_calendar_ids = assistant.get('calendar_account_ids', [])
                assistant_calendar_enabled = assistant.get('calendar_enabled', False)

                if assistant_calendar_ids and assistant_calendar_enabled and assistant_user_id:
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
                        logger.info(f"[OUTBOUND] 📅 Multi-calendar enabled with {len(valid_calendar_ids)} calendar(s)")

                # FALLBACK: Support legacy single calendar_account_id
                if not calendar_enabled and assistant.get('calendar_account_id'):
                    assistant_calendar_id = assistant.get('calendar_account_id')
                    account_doc = calendar_accounts_collection.find_one({"_id": assistant_calendar_id})
                    if account_doc:
                        calendar_enabled = True
                        calendar_account_id_for_booking = assistant_calendar_id
                        calendar_account_ids_list = [str(assistant_calendar_id)]
                        default_calendar_provider = account_doc.get("provider", "google")
                        logger.info(f"[OUTBOUND] 📅 Calendar enabled via legacy single account")

                # Add calendar instructions to system message if enabled
                system_message = assistant.get("system_message", "You are a helpful assistant.")
                if calendar_enabled:
                    calendar_instructions = f"""

---
Calendar Scheduling Instructions:
You can schedule meetings during this call. When scheduling:
1. Ask for the preferred date and time
2. Confirm the meeting title/purpose
3. Confirm the duration (default to 30 minutes)
4. Confirm their timezone
5. Let them know you'll schedule it

Default timezone: {timezone_hint}"""
                    system_message = f"{system_message}{calendar_instructions}"
                    logger.info(f"[OUTBOUND] 📅 Added calendar instructions to system message")

                # Build optimized assistant config
                assistant_config = {
                    "system_message": system_message,
                    "greeting": assistant.get("call_greeting", "Hello! How can I help you today?"),
                    "voice": assistant.get("voice", "shimmer"),
                    "tts_voice": assistant.get("tts_voice", assistant.get("voice", "shimmer")),
                    "temperature": assistant.get("temperature", 0.8),
                    "asr_provider": assistant.get("asr_provider", "deepgram"),
                    "asr_model": assistant.get("asr_model", "nova-3"),
                    "asr_language": assistant.get("asr_language", "en"),
                    "tts_provider": assistant.get("tts_provider", "elevenlabs"),
                    "tts_model": assistant.get("tts_model"),
                    "tts_speed": assistant.get("tts_speed", 1.0),
                    "llm_provider": assistant.get("llm_provider", "openai"),
                    "llm_model": assistant.get("llm_model", "gpt-4o-mini"),
                    "llm_max_tokens": assistant.get("llm_max_tokens", 150),
                    "bot_language": assistant.get("bot_language", "en"),
                    # Ultra-low-latency settings (ElevenLabs WebSocket / Sarvam chunked)
                    "streaming_mode": assistant.get("streaming_mode", "optimized"),
                    "tts_stability": assistant.get("tts_stability", 0.5),
                    "tts_similarity_boost": assistant.get("tts_similarity_boost", 0.75),
                    "tts_style": assistant.get("tts_style", 0.0),
                    "tts_pitch": assistant.get("tts_pitch", 0.0),
                    "tts_loudness": assistant.get("tts_loudness", 1.0),
                    # Calendar configuration
                    "calendar_enabled": calendar_enabled,
                    "calendar_account_ids": calendar_account_ids_list,
                    "calendar_account_id": str(calendar_account_id_for_booking) if calendar_account_id_for_booking else None,
                    "calendar_provider": default_calendar_provider,
                    "timezone": timezone_hint,
                    "assistant_id": str(assistant.get("_id")),
                    "user_id": str(assistant_user_id) if assistant_user_id else None,
                    # Real-time tool calling (Vapi-like functionality)
                    "tools_enabled": assistant.get("tools_enabled", False),
                    "tools": assistant.get("tools", []),
                    "max_tool_calls_per_turn": assistant.get("max_tool_calls_per_turn", 5),
                    "tool_execution_timeout": assistant.get("tool_execution_timeout", 30),
                }

                # Sarvam ASR is handled by the general custom provider stream path.
                # The optimized handler currently supports Whisper offline ASR and
                # Deepgram-style streaming assumptions, so bypass it for Sarvam.
                asr_provider = assistant_config.get("asr_provider", "deepgram").lower()
                if asr_provider == "sarvam":
                    logger.info("[OUTBOUND] 🔀 Routing Sarvam ASR to CustomProviderStreamHandler")
                    from app.services.call_handlers.custom_provider_stream import CustomProviderStreamHandler

                    handler = CustomProviderStreamHandler(
                        websocket=websocket,
                        assistant_config=assistant_config,
                        openai_api_key=provider_keys.get("openai"),
                        call_id="twilio_custom_provider_call",
                        platform="twilio",
                        provider_keys=provider_keys
                    )
                    await handler.handle_stream()
                    logger.info("[OUTBOUND] ✅ Custom provider stream completed for Sarvam ASR")
                    return

                # Check streaming mode: "ultra" for word-by-word, "optimized" for sentence-by-sentence
                streaming_mode = assistant.get("streaming_mode", "optimized")
                tts_provider = assistant_config.get("tts_provider", "elevenlabs").lower()

                # Ultra-low-latency mode requires ElevenLabs or Sarvam TTS
                use_ultra_mode = (
                    streaming_mode == "ultra" and
                    tts_provider in ["elevenlabs", "sarvam"]
                )

                if use_ultra_mode:
                    logger.info(f"[OUTBOUND] ⚡ Using ULTRA-LOW-LATENCY pipeline (word-by-word, ~100-200ms)")
                    await handle_ultra_low_latency_stream(websocket, assistant_config, provider_keys)
                    logger.info(f"[OUTBOUND] ✅ Ultra-low-latency stream completed")
                else:
                    logger.info(f"[OUTBOUND] ⚡ Using OPTIMIZED pipeline (sentence-by-sentence, ~300-600ms)")
                    await handle_optimized_stream(websocket, assistant_config, provider_keys)
                    logger.info(f"[OUTBOUND] ✅ Optimized stream completed")
                
            except ImportError as e:
                # Fallback to old handler if optimized not available
                logger.warning(f"[OUTBOUND] ⚠️ Optimized handler not available, falling back to legacy: {e}")
                from app.voice_pipeline.pipeline import StreamProviderHandler
                import os
                
                # Include ALL provider API keys for full provider support
                api_keys = {
                    'openai': openai_api_key or os.getenv('OPENAI_API_KEY'),
                    'deepgram': os.getenv('DEEPGRAM_API_KEY'),
                    'elevenlabs': os.getenv('ELEVENLABS_API_KEY'),
                    'cartesia': os.getenv('CARTESIA_API_KEY'),
                    'sarvam': os.getenv('SARVAM_API_KEY'),
                    'google': os.getenv('GOOGLE_API_KEY'),
                    'groq': os.getenv('GROQ_API_KEY'),
                    'anthropic': os.getenv('ANTHROPIC_API_KEY'),
                    'azure': os.getenv('AZURE_API_KEY'),
                }
                api_keys = {k: v for k, v in api_keys.items() if v is not None}
                
                handler = StreamProviderHandler(websocket, assistant, api_keys, db=db)
                await handler.run()
            except Exception as e:
                logger.error(f"[OUTBOUND] ❌ Stream error: {e}", exc_info=True)
            finally:
                try:
                    await websocket.close()
                except:
                    pass
            return

        # Continue with realtime API mode (default)
        logger.info("[OUTBOUND] Using OpenAI Realtime API mode")

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

        calendar_enabled = False
        default_calendar_provider = "google"
        calendar_service: Optional[CalendarService] = None
        calendar_intent_service: Optional[CalendarIntentService] = None
        conversation_history: List[Dict[str, str]] = []
        scheduling_task: Optional[asyncio.Task] = None
        appointment_scheduled = False
        appointment_metadata: Dict[str, Any] = {}
        lead_id: Optional[str] = None
        campaign_id: Optional[str] = None

        campaign = None
        campaign_id_param = websocket.query_params.get("campaignId")
        lead_id_param = websocket.query_params.get("leadId")

        if lead_id_param:
            try:
                ObjectId(lead_id_param)
                lead_id = lead_id_param
            except Exception:
                logger.warning("Invalid leadId provided (%s); disabling realtime calendar scheduling", lead_id_param)
                lead_id = None

        if campaign_id_param:
            try:
                campaign_obj_id = ObjectId(campaign_id_param)
                campaign = campaigns_collection.find_one({"_id": campaign_obj_id})
                if campaign:
                    campaign_id = campaign_id_param
                    logger.info(f"Loaded campaign {campaign_id_param} for outbound media stream")
            except Exception as e:
                logger.error(f"Failed to load campaign {campaign_id_param}: {e}")

        if campaign and campaign.get("system_prompt_override"):
            override = campaign["system_prompt_override"]
            if override:
                system_message = f"{system_message}\n\n---\nCampaign Instructions:\n{override.strip()}"

        calendar_accounts_collection = db["calendar_accounts"]
        calendar_account_id_for_booking = None
        calendar_account_ids_list = []

        logger.info(f"[OUTBOUND_CALENDAR_CHECK] Assistant calendar_account_id: {assistant.get('calendar_account_id')}")
        logger.info(f"[OUTBOUND_CALENDAR_CHECK] Assistant calendar_account_ids: {assistant.get('calendar_account_ids', [])}")
        logger.info(f"[OUTBOUND_CALENDAR_CHECK] Campaign: {campaign is not None}, Lead ID: {lead_id}, Campaign ID: {campaign_id}")

        # Priority order for calendar account:
        # 1. Campaign calendar_account_id (if calendar_enabled on campaign)
        # 2. Assistant calendar_account_ids (new multi-calendar support)
        # 3. Assistant calendar_account_id (legacy single calendar fallback)

        if campaign and campaign.get("calendar_enabled") and lead_id and campaign_id:
            calendar_enabled = True
            calendar_service = CalendarService()
            calendar_intent_service = CalendarIntentService()
            working_window = campaign.get("working_window") or {}
            timezone_hint = working_window.get("timezone", timezone_hint)

            calendar_account_id = campaign.get("calendar_account_id")
            account_doc = None
            if calendar_account_id:
                account_doc = calendar_accounts_collection.find_one({"_id": calendar_account_id})
                if account_doc:
                    calendar_account_id_for_booking = calendar_account_id
                    calendar_account_ids_list = [str(calendar_account_id)]
                    logger.info(f"[OUTBOUND] Using campaign calendar account: {account_doc.get('email')}")

            # Fallback to assistant's calendar if campaign doesn't have one
            if not account_doc:
                assistant_calendar_id = assistant.get('calendar_account_id')
                if assistant_calendar_id:
                    account_doc = calendar_accounts_collection.find_one({"_id": assistant_calendar_id})
                    if account_doc:
                        calendar_account_id_for_booking = assistant_calendar_id
                        calendar_account_ids_list = [str(assistant_calendar_id)]
                        logger.info(f"[OUTBOUND] Using assistant calendar account (fallback): {account_doc.get('email')}")
                elif assistant_user_id:
                    account_doc = calendar_accounts_collection.find_one({"user_id": assistant_user_id})
                    if account_doc:
                        calendar_account_ids_list = [str(account_doc['_id'])]
                        logger.info(f"[OUTBOUND] Using user's first calendar account (legacy fallback): {account_doc.get('email')}")

            if account_doc:
                default_calendar_provider = account_doc.get("provider", "google")
        else:
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
                    calendar_service = CalendarService()
                    calendar_intent_service = CalendarIntentService()
                    logger.info(f"[OUTBOUND] Multi-calendar enabled for assistant {assistant_id} with {len(valid_calendar_ids)} calendar(s)")

            # FALLBACK: Support legacy single calendar_account_id
            if not calendar_enabled and assistant.get('calendar_account_id'):
                logger.info(f"[OUTBOUND_CALENDAR_CHECK] Entering legacy single calendar check block")
                assistant_calendar_id = assistant.get('calendar_account_id')
                account_doc = calendar_accounts_collection.find_one({"_id": assistant_calendar_id})
                if account_doc:
                    calendar_enabled = True
                    calendar_account_id_for_booking = assistant_calendar_id
                    calendar_account_ids_list = [str(assistant_calendar_id)]
                    calendar_service = CalendarService()
                    calendar_intent_service = CalendarIntentService()
                    default_calendar_provider = account_doc.get("provider", "google")
                    logger.info(f"[OUTBOUND] Calendar enabled via assistant using legacy single account: {account_doc.get('email')}")
                else:
                    logger.error(f"[OUTBOUND] ❌ Calendar account not found for ID: {assistant_calendar_id}")

        # Add calendar scheduling instructions if calendar is enabled
        logger.info(f"[OUTBOUND_CALENDAR_CHECK] Final calendar_enabled status: {calendar_enabled}")
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
            """Analyze recent conversation context and book a calendar event if appropriate."""
            nonlocal scheduling_task, appointment_scheduled, appointment_metadata, call_sid

            logger.debug(f"[CALENDAR_SCHEDULE_CHECK] Trigger: {trigger}, calendar_enabled={calendar_enabled}, campaign_id={campaign_id}, lead_id={lead_id}")

            if (
                not calendar_enabled
                or calendar_intent_service is None
                or calendar_service is None
                or appointment_scheduled
            ):
                logger.debug(f"[CALENDAR_SCHEDULE_CHECK] Early return - calendar_enabled={calendar_enabled}, appointment_scheduled={appointment_scheduled}")
                return

            # For campaign calls, require campaign_id and lead_id
            # For non-campaign calls, calendar scheduling should still work
            is_campaign_call = campaign_id and lead_id

            if not is_campaign_call:
                logger.debug("[CALENDAR_SCHEDULE_CHECK] Non-campaign call - calendar scheduling enabled without lead tracking")

            if scheduling_task and not scheduling_task.done():
                return

            if not conversation_history or not openai_api_key:
                return

            if not call_sid:
                logger.debug("Call SID unavailable; delaying calendar analysis")
                return

            async def _run_analysis() -> None:
                nonlocal appointment_scheduled, appointment_metadata
                try:
                    logger.info(f"[CALENDAR_ANALYSIS] Extracting intent from conversation with {len(conversation_history)} messages")
                    result = await calendar_intent_service.extract_from_conversation(
                        conversation_history,
                        openai_api_key,
                        timezone_hint,
                    )
                    logger.info(f"[CALENDAR_ANALYSIS] Intent result: should_schedule={result.get('should_schedule') if result else None}")

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

                    logger.info(f"[CALENDAR_ANALYSIS] ✓ Valid appointment: {appointment.get('title')} at {start_iso}")

                    appointment.setdefault("timezone", timezone_hint)
                    appointment.setdefault("notes", result.get("reason"))
                    provider = appointment.get("provider") or default_calendar_provider

                    # Parse appointment times for availability checking
                    try:
                        start_time = datetime.fromisoformat(start_iso.replace('Z', '+00:00') if start_iso.endswith('Z') else start_iso)
                        end_time = datetime.fromisoformat(end_iso.replace('Z', '+00:00') if end_iso.endswith('Z') else end_iso)
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
                                f"I'm sorry, but that time slot is already occupied in the calendar. "
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
                                "I'm sorry, but that time slot is already occupied in the calendar. "
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

                    # For campaign calls, use book_appointment (requires lead_id and campaign_id)
                    # For non-campaign calls, use book_inbound_appointment
                    if is_campaign_call:
                        logger.info(f"[CALENDAR_BOOKING] Campaign call - using book_appointment")
                        event_id = await calendar_service.book_appointment(
                            lead_id=lead_id,
                            campaign_id=campaign_id,
                            appointment_data=appointment,
                            provider=provider,
                            calendar_account_id_override=str(calendar_account_id_for_booking) if calendar_account_id_for_booking else None,
                        )
                    else:
                        logger.info(f"[CALENDAR_BOOKING] Non-campaign call - using book_inbound_appointment")
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

                    call_log_update: Dict[str, Any] = {
                        "appointment_booked": True,
                        "appointment_details": appointment_metadata,
                        "calendar_event_id": event_id,
                        "appointment_source": "realtime",
                        "updated_at": datetime.utcnow(),
                    }
                    if lead_id:
                        try:
                            call_log_update["lead_id"] = ObjectId(lead_id)
                        except Exception:
                            call_log_update["lead_id"] = lead_id
                    if campaign_id:
                        try:
                            call_log_update["campaign_id"] = ObjectId(campaign_id)
                        except Exception:
                            call_log_update["campaign_id"] = campaign_id

                    try:
                        db["call_logs"].update_one(
                            {"call_sid": call_sid},
                            {"$set": call_log_update},
                        )
                    except Exception as dberr:
                        logger.error(f"Failed to update call log with appointment details: {dberr}")

                    confirmation_text = result.get("confirmation_text") or (
                        f"The meeting '{appointment.get('title', 'Meeting')}' was scheduled for "
                        f"{appointment.get('start_iso')} {appointment.get('timezone')}."
                    )
                    system_prompt = (
                        "Calendar event scheduled successfully. "
                        "Politely confirm the booking details with the contact. "
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

        logger.info(f"[TWILIO] Provider Configuration: ASR={asr_provider}, TTS={tts_provider}, LLM={llm_provider}")
        logger.info(f"[TWILIO] Using OpenAI Realtime API: {use_openai_realtime}")

        # If using custom providers, delegate to custom provider handler
        if not use_openai_realtime:
            logger.info(f"[TWILIO] Routing to custom provider handler for assistant {assistant_id}")
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
                'provider_keys': provider_keys,  # Pass all resolved keys
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
                call_id="twilio_custom_provider_call",  # Twilio will provide call_sid via websocket
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

        # Get the LLM model to use for OpenAI Realtime API
        llm_model = assistant.get('llm_model', 'gpt-4o-mini-realtime-preview')
        logger.info(f"[TWILIO] Using OpenAI Realtime API - Model: {llm_model}, Voice: {voice}, Temperature: {temperature}")

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
            # Get VAD settings from assistant config for noise suppression
            vad_threshold = assistant.get('vad_threshold', 0.5)
            vad_prefix_padding_ms = assistant.get('vad_prefix_padding_ms', 300)
            vad_silence_duration_ms = assistant.get('vad_silence_duration_ms', 500)

            # Initialize session with interruption handling enabled
            # NOTE: send_session_update now calls send_initial_conversation_item internally
            # This matches the original pattern from CallTack_IN_out/outbound_call.py
            await send_session_update(
                openai_ws,
                system_message,
                voice,
                temperature,
                enable_interruptions=True,
                greeting_text=call_greeting,
                max_response_output_tokens="inf",  # Allow unlimited response length for natural conversation
                vad_threshold=vad_threshold,
                vad_prefix_padding_ms=vad_prefix_padding_ms,
                vad_silence_duration_ms=vad_silence_duration_ms
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
                logger.info(f"[OUTBOUND] Background audio enabled: type={bg_audio_mixer.audio_type}, volume={bg_audio_mixer.volume}")

            async def receive_from_twilio():
                """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
                nonlocal stream_sid, latest_media_timestamp, call_sid, hangup_completed
                try:
                    async for message in websocket.iter_text():
                        if hangup_completed:
                            logger.info("Hangup already completed; stopping outbound receive loop")
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

                            # Extract recipient number from custom parameters
                            recipient_number = start_info.get('customParameters', {}).get('to_number')
                            logger.info(f"Outbound stream started {stream_sid} to {recipient_number}")

                            # Look up recipient name from database (leads or contacts)
                            recipient_name = None
                            if recipient_number and assistant_user_id:
                                try:
                                    # Check leads collection
                                    lead = db['leads'].find_one({
                                        "user_id": assistant_user_id,
                                        "phone_number": recipient_number
                                    })
                                    if lead:
                                        recipient_name = lead.get('name') or lead.get('first_name')
                                        logger.info(f"Found recipient in leads: {recipient_name}")

                                    # If not found, check contacts
                                    if not recipient_name:
                                        contact = db['contacts'].find_one({
                                            "user_id": assistant_user_id,
                                            "phone": recipient_number
                                        })
                                        if contact:
                                            recipient_name = contact.get('name')
                                            logger.info(f"Found recipient in contacts: {recipient_name}")
                                except Exception as e:
                                    logger.error(f"Error looking up recipient: {e}")

                            # Update system message with recipient info if available
                            if recipient_name:
                                enhanced_system_message = f"{system_message}\n\nIMPORTANT: You are calling {recipient_name}. Greet them by name and use their name naturally during the conversation."
                                # Send updated session with recipient context
                                await send_session_update(
                                    openai_ws,
                                    enhanced_system_message,
                                    voice,
                                    temperature,
                                    enable_interruptions=True,
                                    greeting_text=f"Hello {recipient_name}! {call_greeting.replace('Hello!', '').strip()}",
                                    max_response_output_tokens="inf",
                                    vad_threshold=vad_threshold,
                                    vad_prefix_padding_ms=vad_prefix_padding_ms,
                                    vad_silence_duration_ms=vad_silence_duration_ms
                                )
                                logger.info(f"Updated greeting for outbound call to {recipient_name}")

                            response_start_timestamp_twilio = None
                            latest_media_timestamp = 0
                            last_assistant_item = None
                        elif data['event'] == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)
                except WebSocketDisconnect:
                    logger.info("Client disconnected from outbound call.")
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
                            logger.info(f"Requested Twilio to end outbound call {call_sid}")
                        except TwilioRestException as twilio_error:
                            logger.error(f"Twilio error ending outbound call {call_sid}: {twilio_error}")
                        except Exception as generic_error:
                            logger.error(f"Unexpected error ending outbound call {call_sid}: {generic_error}")
                    else:
                        logger.warning("Cannot end outbound call automatically - missing Twilio client or call SID")

                    # CRITICAL FIX: Trigger next call IMMEDIATELY when call ends
                    # This runs right when the call finishes, ensuring instant sequential dialing
                    if campaign_id and lead_id:
                        logger.info(f"[FINALIZE_CALL] Call ended - triggering next call for campaign {campaign_id}")

                        async def trigger_next_call_immediate():
                            try:
                                from app.services.async_campaign_dialer import AsyncCampaignDialer
                                from app.config.async_database import AsyncDatabase
                                dialer = AsyncCampaignDialer()

                                # Mark current lead as completed (async)
                                db = await AsyncDatabase.get_db()
                                leads_collection = db["leads"]
                                campaigns_collection = db["campaigns"]

                                lead = await leads_collection.find_one({"_id": ObjectId(lead_id)})
                                campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})

                                if lead and campaign:
                                    # Update lead status to completed
                                    await leads_collection.update_one(
                                        {"_id": ObjectId(lead_id)},
                                        {
                                            "$set": {
                                                "status": "completed",
                                                "last_outcome": "completed",
                                                "updated_at": datetime.utcnow()
                                            }
                                        }
                                    )
                                    logger.info(f"[FINALIZE_CALL] Marked lead {lead_id} as completed")

                                    # Only trigger next call if campaign is still running
                                    if campaign.get("status") == "running":
                                        next_lead = await dialer.get_next_lead(campaign_id, ignore_window=False)
                                        if next_lead:
                                            logger.info(f"[FINALIZE_CALL] Found next lead: {next_lead.get('name')} ({next_lead.get('e164')})")
                                            next_call_sid = await dialer.place_call(campaign_id, str(next_lead["_id"]))
                                            if next_call_sid:
                                                logger.info(f"[FINALIZE_CALL] Next call placed successfully: {next_call_sid}")
                                            else:
                                                logger.warning(f"[FINALIZE_CALL] Failed to place next call: {dialer.last_error}")
                                        else:
                                            logger.info(f"[FINALIZE_CALL] No more leads available for campaign {campaign_id}")
                                    else:
                                        logger.info(f"[FINALIZE_CALL] Campaign {campaign_id} is not running, skipping next call")
                            except Exception as next_error:
                                logger.error(f"[FINALIZE_CALL] Error triggering next call: {next_error}")
                                import traceback
                                logger.error(traceback.format_exc())

                        # Run as async task (better than threading)
                        import asyncio
                        asyncio.create_task(trigger_next_call_immediate())
                        logger.info(f"[FINALIZE_CALL] Async task started for next call")

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
                                    logger.info("Final goodbye response delivered on outbound call; ending now")
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
                            try:
                                audio_payload = response['delta']

                                # CRITICAL: Ensure audio_payload is not empty
                                if not audio_payload:
                                    logger.warning("⚠️ Received empty audio payload from OpenAI")
                                    continue

                                # Log first audio chunk for debugging
                                if response_start_timestamp_twilio is None:
                                    logger.info(f"🔊 FIRST AUDIO CHUNK - Length: {len(audio_payload)} bytes, stream_sid: {stream_sid}")

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

                                # Send audio immediately without any delays
                                await websocket.send_json(audio_delta)
                                logger.debug(f"✅ Sent audio chunk to Twilio: {len(audio_payload)} bytes")

                                if response_start_timestamp_twilio is None:
                                    response_start_timestamp_twilio = latest_media_timestamp
                                    if SHOW_TIMING_MATH:
                                        logger.info(f"Setting start timestamp for new response: {response_start_timestamp_twilio}ms")

                                # Update last_assistant_item safely
                                if response.get('item_id'):
                                    last_assistant_item = response['item_id']

                                # Send mark after audio for synchronization
                                await send_mark(websocket, stream_sid, mark_queue)

                            except Exception as audio_err:
                                logger.error(f"❌ Error sending audio delta to Twilio: {audio_err}")
                                import traceback
                                logger.error(traceback.format_exc())

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
                                    if content.get('type') == 'input_audio':
                                        transcript = content.get('transcript', '')
                                        if transcript:
                                            logger.info(f"User said: {transcript}")
                                            hangup_handled = False
                                            if not hangup_completed:
                                                if awaiting_hangup_confirmation:
                                                    if transcript_confirms_hangup(transcript) or transcript_has_hangup_intent(transcript):
                                                        logger.info("Caller confirmed hangup on outbound call.")
                                                        awaiting_hangup_confirmation = False
                                                        pending_hangup_goodbye = True
                                                        await send_call_end_acknowledgement(openai_ws)
                                                        hangup_handled = True
                                                    elif transcript_denies_hangup(transcript):
                                                        logger.info("Caller declined hangup on outbound call; continuing.")
                                                        awaiting_hangup_confirmation = False
                                                        await send_call_continue_acknowledgement(openai_ws)
                                                        hangup_handled = True
                                                elif transcript_has_hangup_intent(transcript):
                                                    logger.info("Detected caller intent to end outbound call; requesting confirmation.")
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
        logger.info(f"Client disconnected normally from outbound call for assistant: {assistant_id}")
    except Exception as error:
        import traceback
        logger.error(f"Error in outbound media stream for assistant {assistant_id}: {str(error)}")
        logger.error(traceback.format_exc())
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass  # WebSocket might already be closed
    finally:
        # Ensure cleanup happens
        logger.info(f"Cleaning up outbound call resources for assistant: {assistant_id}")
        # Note: Instant dial trigger now happens in finalize_call() for better timing
        # WebSocket and OpenAI connections will be closed by context managers

# Helper functions

async def check_number_allowed(twilio_client: Client, phone_number: str) -> bool:
    """
    Check if a number is allowed to be called.

    Checks against:
    - Twilio verified outgoing caller IDs
    - Twilio incoming phone numbers (owned by account)

    Args:
        twilio_client: Twilio client instance for the user
        phone_number: Phone number to check

    Returns:
        bool: True if allowed, False otherwise
    """
    try:
        # Check if it's one of our incoming phone numbers
        incoming_numbers = twilio_client.incoming_phone_numbers.list(phone_number=phone_number)
        if incoming_numbers:
            logger.info(f"{phone_number} is an owned incoming number")
            return True

        # Check if it's a verified outgoing caller ID
        outgoing_caller_ids = twilio_client.outgoing_caller_ids.list(phone_number=phone_number)
        if outgoing_caller_ids:
            logger.info(f"{phone_number} is a verified caller ID")
            return True

        logger.warning(f"{phone_number} is not verified or owned")
        return False
    except Exception as e:
        logger.error(f"Error checking phone number: {e}")
        return False

@router.api_route("/recording-status", methods=["GET", "POST"])
async def handle_outbound_recording_status(request: Request):
    """
    Callback endpoint for Twilio outbound call recording status updates.
    Updates call log with recording URL when recording is completed.
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

        logger.info(f"Outbound recording status: {recording_status} for call {call_sid}")
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
                logger.info(f"Updated outbound call log with recording URL for call {call_sid}")

                # Trigger automatic transcription for outbound calls
                # Note: Twilio native transcription is NOT available with <Stream> verb
                # We use OpenAI Whisper for all call transcriptions (both custom provider and realtime modes)
                # OPTIMIZED: Now uses async processor for non-blocking operations
                try:
                    from app.services.async_post_call_processor import AsyncPostCallProcessor
                    import asyncio

                    processor = AsyncPostCallProcessor()
                    logger.info(f"Triggering automatic transcription for outbound call: {call_sid}")
                    asyncio.create_task(processor.transcribe_and_update_call(call_sid, recording_url))
                except Exception as e:
                    logger.error(f"Error triggering transcription for outbound call {call_sid}: {e}")
            else:
                logger.warning(f"Outbound call log not found for call_sid: {call_sid}")

        return {"status": "success", "message": "Recording status received"}

    except Exception as error:
        logger.error(f"Error handling outbound recording status: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(error)}


@router.api_route("/transcription-status", methods=["GET", "POST"])
async def handle_outbound_transcription_status(request: Request):
    """
    Callback endpoint for Twilio outbound call transcription status updates.
    Saves transcription text to database when transcription is completed.
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

        logger.info(f"Outbound transcription status: {transcription_status} for call {call_sid}")

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
                logger.info(f"Updated outbound call log with transcription for call {call_sid}")
                logger.info(f"Transcription preview: {transcription_text[:100]}...")
            else:
                logger.warning(f"Outbound call log not found for call_sid: {call_sid}")

        return {"status": "success", "message": "Transcription status received"}

    except Exception as error:
        logger.error(f"Error handling outbound transcription status: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(error)}


async def get_twilio_phone_number(twilio_client: Client) -> str:
    """
    Get the first available Twilio phone number from the account.

    Args:
        twilio_client: Twilio client instance for the user

    Returns:
        str: Phone number in E.164 format, or None if no numbers available
    """
    try:
        incoming_numbers = twilio_client.incoming_phone_numbers.list(limit=1)
        if incoming_numbers:
            phone_number = incoming_numbers[0].phone_number
            logger.info(f"Using Twilio phone number: {phone_number}")
            return phone_number

        logger.error("No Twilio phone numbers found in account")
        return None
    except Exception as e:
        logger.error(f"Error fetching Twilio phone number: {e}")
        return None
