"""
WebRTC Routes for Web/Mobile Voice Calls

Provides WebRTC-based voice calling endpoints for:
- Web browser calls (lowest latency)
- Mobile app calls (iOS/Android)

Benefits over WebSocket:
- 20-50ms latency vs 100-300ms with WebSocket
- Native browser audio handling
- UDP transport (no TCP head-of-line blocking)
- Adaptive bitrate

Note: Phone calls (PSTN via Twilio/FreJun) still use WebSocket.
"""

from fastapi import APIRouter, WebSocket, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketDisconnect
from bson import ObjectId
from typing import Dict, Any
import logging

from app.config.database import Database
from app.config.settings import settings
from app.utils.assistant_keys import resolve_provider_keys

# Lazy imports for WebRTC to avoid slowing down startup
_webrtc_module = None


def _get_webrtc_module():
    """Lazy load WebRTC module to speed up startup"""
    global _webrtc_module
    if _webrtc_module is None:
        from app.services import webrtc as webrtc_mod
        _webrtc_module = webrtc_mod
    return _webrtc_module


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=JSONResponse)
async def webrtc_index():
    """Health check for WebRTC service"""
    webrtc = _get_webrtc_module()
    return {
        "message": "WebRTC voice service is running",
        "active_sessions": webrtc.signaling_server.get_active_session_count()
    }


@router.get("/config", response_class=JSONResponse)
async def get_webrtc_config():
    """
    Get WebRTC configuration (ICE servers, audio constraints).

    Call this before establishing a WebRTC connection to get:
    - STUN/TURN server URLs
    - Audio constraints for optimal quality
    """
    webrtc = _get_webrtc_module()
    return {
        "rtcConfiguration": webrtc.get_rtc_configuration(),
        "audioConstraints": {
            "echoCancellation": True,
            "noiseSuppression": True,
            "autoGainControl": True,
            "sampleRate": 16000,
            "channelCount": 1
        },
        "iceTransportPolicy": "all"
    }


@router.websocket("/call/{assistant_id}")
async def handle_webrtc_voice_call(websocket: WebSocket, assistant_id: str, user_id: str = None):
    """
    WebRTC voice call endpoint.

    This is for web/mobile clients ONLY.
    Phone calls must use /api/inbound-calls/ endpoints.

    Flow:
    1. Client connects via WebSocket for signaling
    2. Server sends ICE configuration
    3. WebRTC peer connection established
    4. Audio flows via WebRTC data channel
    5. Server processes: ASR → LLM → TTS

    Args:
        websocket: WebSocket for signaling
        assistant_id: AI assistant ID
        user_id: Optional user ID (from query param or auth)
    """
    logger.info(f"[WEBRTC] New connection for assistant: {assistant_id}")

    # Accept WebSocket immediately so the browser doesn't time out
    # while we do DB lookups and pipeline initialization.
    await websocket.accept()

    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Validate assistant_id
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception as e:
            logger.error(f"[WEBRTC] Invalid assistant_id format: {e}")
            await websocket.close(code=1008, reason="Invalid assistant_id")
            return

        # Fetch assistant configuration
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})

        if not assistant:
            logger.error(f"[WEBRTC] Assistant not found: {assistant_id}")
            await websocket.close(code=1008, reason="Assistant not found")
            return

        logger.info(f"[WEBRTC] Assistant found: {assistant.get('name', 'Unknown')}")

        # Get user ID from assistant if not provided
        assistant_user_id = user_id or str(assistant.get('user_id', ''))
        if isinstance(assistant.get('user_id'), ObjectId):
            assistant_user_id = str(assistant.get('user_id'))

        # Resolve provider API keys
        provider_keys = resolve_provider_keys(db, assistant, assistant.get('user_id'))
        logger.info(f"[WEBRTC] Resolved provider keys: {list(provider_keys.keys())}")

        # Build assistant configuration
        assistant_config = build_assistant_config(assistant, db)

        # Handle WebRTC call (websocket already accepted)
        webrtc = _get_webrtc_module()
        await webrtc.handle_webrtc_call(
            websocket=websocket,
            assistant_id=assistant_id,
            user_id=assistant_user_id,
            assistant_config=assistant_config,
            provider_keys=provider_keys
        )

    except WebSocketDisconnect:
        logger.info(f"[WEBRTC] WebSocket disconnected for assistant {assistant_id}")
    except Exception as e:
        logger.error(f"[WEBRTC] Error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except:
            pass

    logger.info(f"[WEBRTC] Call ended for assistant {assistant_id}")


def build_assistant_config(assistant: Dict[str, Any], db) -> Dict[str, Any]:
    """Build assistant configuration for WebRTC handler"""

    # Get timezone
    timezone_hint = (
        assistant.get('timezone')
        or settings.default_timezone
        or "America/New_York"
    )

    # Calendar configuration
    calendar_enabled = False
    calendar_account_ids_list = []
    calendar_account_id_for_booking = None
    default_calendar_provider = "google"

    assistant_user_id = assistant.get('user_id')
    assistant_calendar_ids = assistant.get('calendar_account_ids', [])
    assistant_calendar_enabled = assistant.get('calendar_enabled', False)

    if assistant_calendar_ids and assistant_calendar_enabled and assistant_user_id:
        calendar_accounts_collection = db["calendar_accounts"]
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
            logger.info(f"[WEBRTC] Calendar enabled with {len(valid_calendar_ids)} calendar(s)")

    # Legacy single calendar support
    if not calendar_enabled and assistant.get('calendar_account_id'):
        assistant_calendar_id = assistant.get('calendar_account_id')
        account_doc = db["calendar_accounts"].find_one({"_id": assistant_calendar_id})
        if account_doc:
            calendar_enabled = True
            calendar_account_id_for_booking = assistant_calendar_id
            calendar_account_ids_list = [str(assistant_calendar_id)]
            default_calendar_provider = account_doc.get("provider", "google")

    # Build system message with calendar instructions
    system_message = assistant.get("system_message", "You are a helpful assistant.")
    if calendar_enabled:
        calendar_instructions = f"""

---
Calendar Scheduling Instructions:
You can schedule meetings and appointments during this call. When requested:
1. Ask for preferred date and time
2. Confirm meeting title/purpose
3. Confirm duration (default 30 minutes)
4. Confirm timezone
5. Let them know you'll schedule it

Default timezone: {timezone_hint}
"""
        system_message = f"{system_message}{calendar_instructions}"

    return {
        "assistant_id": str(assistant['_id']),
        "user_id": str(assistant_user_id) if assistant_user_id else None,
        "system_message": system_message,
        "greeting": assistant.get("call_greeting", "Hello! How can I help you today?"),
        "voice": assistant.get("voice", "alloy"),
        "tts_voice": assistant.get("tts_voice", assistant.get("voice", "alloy")),
        "temperature": assistant.get("temperature", 0.7),
        "asr_provider": assistant.get("asr_provider", "deepgram"),
        "asr_model": assistant.get("asr_model", "nova-2"),
        "asr_language": assistant.get("asr_language", "en"),
        "tts_provider": assistant.get("tts_provider", "elevenlabs"),
        "tts_model": assistant.get("tts_model", "eleven_flash_v2_5"),
        "llm_provider": assistant.get("llm_provider", "openai"),
        "llm_model": assistant.get("llm_model", "gpt-4-turbo"),
        "llm_max_tokens": assistant.get("llm_max_tokens", 150),
        "bot_language": assistant.get("bot_language", "en"),
        # Calendar config
        "calendar_enabled": calendar_enabled,
        "calendar_account_ids": calendar_account_ids_list,
        "calendar_account_id": str(calendar_account_id_for_booking) if calendar_account_id_for_booking else None,
        "calendar_provider": default_calendar_provider,
        "timezone": timezone_hint,
    }


@router.get("/sessions", response_class=JSONResponse)
async def get_active_sessions():
    """Get count of active WebRTC sessions"""
    webrtc = _get_webrtc_module()
    return {
        "active_sessions": webrtc.signaling_server.get_active_session_count()
    }


@router.get("/session/{session_id}", response_class=JSONResponse)
async def get_session_info(session_id: str):
    """Get info about a specific WebRTC session"""
    webrtc = _get_webrtc_module()
    session = webrtc.signaling_server.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    return {
        "session_id": session.session_id,
        "assistant_id": session.assistant_id,
        "user_id": session.user_id,
        "state": session.state,
        "created_at": session.created_at.isoformat(),
        "audio_packets_received": session.audio_packets_received,
        "audio_packets_sent": session.audio_packets_sent
    }
