import os
import json
import asyncio
import re
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
            openai_api_key, _ = resolve_assistant_api_key(db, assistant, required_provider="openai")
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
            "asr_provider": "deepgram",
            "asr_model": "nova-2",
            "asr_language": assistant.get('asr_language', 'en'),
            "tts_provider": "elevenlabs",
            "tts_model": "eleven_flash_v2_5",
            "tts_voice": assistant.get('tts_voice'),
            "llm_provider": "openai",
            "llm_model": "gpt-4-turbo",
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
        # Resolve API keys
        from app.services.call_handlers.optimized_stream_handler import handle_optimized_stream
        from app.services.call_handlers.ultra_low_latency_handler import handle_ultra_low_latency_stream
        from app.utils.assistant_keys import resolve_provider_keys

        provider_keys = resolve_provider_keys(db, assistant, assistant_user_id)
        logger.info(f"[OUTBOUND] Resolved provider keys: {list(provider_keys.keys())}")

        try:

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
                "voice": assistant.get("voice", "alloy"),
                "tts_voice": assistant.get("tts_voice", assistant.get("voice", "alloy")),
                "temperature": assistant.get("temperature", 0.7),
                "asr_provider": "deepgram",
                "asr_model": "nova-2",
                "asr_language": assistant.get("asr_language", "en"),
                "tts_provider": "elevenlabs",
                "tts_model": "eleven_flash_v2_5",
                "tts_speed": assistant.get("tts_speed", 1.0),
                "llm_provider": "openai",
                "llm_model": "gpt-4-turbo",
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

        except Exception as e:
            logger.error(f"[OUTBOUND] Stream error: {e}", exc_info=True)
        finally:
            try:
                await websocket.close()
            except:
                pass

    except Exception as e:
        logger.error(f"[OUTBOUND] Fatal error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass

    logger.info(f"[OUTBOUND] Stream ended for assistant {assistant_id}")


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
