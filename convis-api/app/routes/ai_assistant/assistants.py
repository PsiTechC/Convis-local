from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import Response
from app.middleware.rate_limiter import limiter, get_rate_limit
from app.models.ai_assistant import (
    AIAssistantCreate,
    AIAssistantUpdate,
    AIAssistantResponse,
    AIAssistantListResponse,
    DeleteResponse,
    KnowledgeBaseFile
)
from app.config.database import Database
from app.constants import DEFAULT_CALL_GREETING
from app.utils.encryption import encryption_service
from bson import ObjectId
from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, validator
import logging
import os
import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Voices currently supported by OpenAI's text-to-speech API (tts-1 model)
SUPPORTED_TTS_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "marin",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
}

# Backward compatibility voices that were available in earlier releases
LEGACY_TTS_VOICES = {
    "cedar",  # keep for existing assistants even if OpenAI rejects it later
}

TTS1_VOICES = {"alloy", "verse"}
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"


def resolve_tts_model_and_voice(requested_voice: str) -> tuple[str, str]:
    """Return the preferred OpenAI TTS model and the voice id to pass to it."""

    normalized = requested_voice.lower()

    if normalized in TTS1_VOICES:
        return "tts-1", normalized

    if normalized in LEGACY_TTS_VOICES:
        # Legacy voices are no longer supported; quietly fall back to Alloy so the demo still works
        return DEFAULT_TTS_MODEL, "alloy"

    # All other voices map to the GPT-4o mini TTS model which exposes the richer catalogue
    return DEFAULT_TTS_MODEL, normalized


class VoiceDemoRequest(BaseModel):
    voice: Literal[
        "alloy",
        "ash",
        "ballad",
        "coral",
        "echo",
        "fable",
        "marin",
        "nova",
        "onyx",
        "sage",
        "shimmer",
        "verse",
        "cedar",
    ]
    user_id: str
    api_key_id: Optional[str] = None
    text: str = "Hello! This is a sample of my voice. I'm here to assist you with your conversations."

    @validator("voice", pre=True)
    def normalize_voice(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Voice must be a string identifier.")

        lower_value = value.lower()
        if lower_value in SUPPORTED_TTS_VOICES or lower_value in LEGACY_TTS_VOICES:
            return lower_value

        raise ValueError(
            f"Unsupported voice '{value}'. Supported voices are: "
            f"{', '.join(sorted(SUPPORTED_TTS_VOICES | LEGACY_TTS_VOICES))}"
        )

def resolve_api_key_metadata(api_keys_collection, key_identifier) -> Optional[Dict[str, Any]]:
    """
    Retrieve metadata for a stored API key without exposing the raw secret.
    """
    if not key_identifier:
        return None

    try:
        key_obj_id = key_identifier if isinstance(key_identifier, ObjectId) else ObjectId(key_identifier)
    except Exception:
        return None

    doc = api_keys_collection.find_one({"_id": key_obj_id})
    if not doc:
        return None

    return {
        "id": str(doc['_id']),
        "label": doc['label'],
        "provider": doc['provider'],
    }

def assistant_has_api_key(assistant: dict) -> bool:
    """
    Check if API key is available for this assistant.
    Since deployment uses environment variables, we check if the required
    provider keys are set in environment variables.
    """
    import os
    
    # Get providers used by this assistant
    asr_provider = assistant.get('asr_provider', 'openai').lower()
    tts_provider = assistant.get('tts_provider', 'openai').lower()
    llm_provider = assistant.get('llm_provider', 'openai').lower()
    
    # Check for 'openai-realtime' in voice_mode (uses OpenAI API key)
    voice_mode = assistant.get('voice_mode', 'realtime').lower()
    if voice_mode == 'realtime' or 'realtime' in llm_provider:
        llm_provider = 'openai'  # Realtime API uses OpenAI key
    
    # Map providers to environment variables
    env_var_map = {
        'openai': 'OPENAI_API_KEY',
        'openai-realtime': 'OPENAI_API_KEY',
        'deepgram': 'DEEPGRAM_API_KEY',
        'sarvam': 'SARVAM_API_KEY',
        'google': 'GOOGLE_API_KEY',
        'cartesia': 'CARTESIA_API_KEY',
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'groq': 'GROQ_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY'
    }
    
    # Check if all required provider keys are in environment
    required_providers = set([asr_provider, tts_provider, llm_provider])
    
    for provider in required_providers:
        env_var = env_var_map.get(provider)
        if env_var:
            if os.getenv(env_var):
                return True  # At least one required key is available
    
    # If using custom providers but keys not in env, check old method as fallback
    # (for backwards compatibility)
    if assistant.get('api_key_id') or assistant.get('openai_api_key'):
        return True
    
    # For realtime mode, OpenAI key is always needed
    if voice_mode == 'realtime':
        return bool(os.getenv('OPENAI_API_KEY'))
    
    return False

def resolve_calendar_account_metadata(calendar_accounts_collection, calendar_account_id) -> Optional[Dict[str, Any]]:
    """
    Retrieve metadata for a calendar account.
    """
    if not calendar_account_id:
        return None

    try:
        calendar_obj_id = calendar_account_id if isinstance(calendar_account_id, ObjectId) else ObjectId(calendar_account_id)
    except Exception:
        return None

    doc = calendar_accounts_collection.find_one({"_id": calendar_obj_id})
    if not doc:
        return None

    return {
        "id": str(doc['_id']),
        "email": doc.get('email'),
        "provider": doc.get('provider'),
    }

@router.post("/", response_model=AIAssistantResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_rate_limit("assistant_create"))
async def create_assistant(request: Request, assistant_data: AIAssistantCreate):
    """
    Create a new AI assistant for a user

    Args:
        assistant_data: AI assistant configuration

    Returns:
        AIAssistantResponse: Created assistant details

    Raises:
        HTTPException: If user not found or error occurs
    """
    try:
        db = Database.get_db()
        users_collection = db['users']
        assistants_collection = db['assistants']
        api_keys_collection = db['api_keys']
        api_keys_collection = db['api_keys']

        logger.info(f"Creating AI assistant for user: {assistant_data.user_id}")

        # Verify user exists
        try:
            user_obj_id = ObjectId(assistant_data.user_id)
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

        # API keys are no longer required - system uses .env OPENAI_API_KEY
        # Keep these for backwards compatibility but don't validate
        selected_key_doc = None
        encrypted_api_key: Optional[str] = None
        api_key_obj_id: Optional[ObjectId] = None

        logger.info("[ASSISTANT] Using system OpenAI API key from environment")

        # Resolve greeting text (default if empty)
        call_greeting = (assistant_data.call_greeting or DEFAULT_CALL_GREETING).strip()
        if not call_greeting:
            call_greeting = DEFAULT_CALL_GREETING

        # Validate calendar_account_id if provided (legacy support)
        calendar_account_obj_id = None
        calendar_account_email = None
        if assistant_data.calendar_account_id:
            try:
                calendar_account_obj_id = ObjectId(assistant_data.calendar_account_id)
                calendar_accounts_collection = db['calendar_accounts']
                calendar_account = calendar_accounts_collection.find_one({
                    "_id": calendar_account_obj_id,
                    "user_id": user_obj_id
                })
                if not calendar_account:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Calendar account not found or does not belong to user"
                    )
                calendar_account_email = calendar_account.get("email")
            except Exception as e:
                if isinstance(e, HTTPException):
                    raise
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid calendar_account_id format"
                )

        # Validate calendar_account_ids if provided (new multi-calendar support)
        calendar_account_obj_ids = []
        if assistant_data.calendar_account_ids:
            calendar_accounts_collection = db['calendar_accounts']
            for cal_id in assistant_data.calendar_account_ids:
                try:
                    cal_obj_id = ObjectId(cal_id)
                    calendar_account = calendar_accounts_collection.find_one({
                        "_id": cal_obj_id,
                        "user_id": user_obj_id
                    })
                    if not calendar_account:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Calendar account {cal_id} not found or does not belong to user"
                        )
                    calendar_account_obj_ids.append(cal_obj_id)
                except Exception as e:
                    if isinstance(e, HTTPException):
                        raise
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid calendar_account_id format: {cal_id}"
                    )

        # Determine requested voice mode (defaults to realtime)
        requested_voice_mode = (assistant_data.voice_mode or "realtime").lower()
        if requested_voice_mode not in ("realtime", "custom"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="voice_mode must be either 'realtime' or 'custom'"
            )

        # Create assistant document
        now = datetime.utcnow()

        assistant_doc = {
            "user_id": user_obj_id,
            "name": assistant_data.name,
            "system_message": assistant_data.system_message,
            "voice": assistant_data.voice,
            "temperature": assistant_data.temperature,
            "call_greeting": call_greeting,
            "calendar_account_id": calendar_account_obj_id,
            "calendar_account_ids": calendar_account_obj_ids,
            "calendar_enabled": assistant_data.calendar_enabled if assistant_data.calendar_enabled is not None else False,
            "last_calendar_used_index": -1,
            "voice_mode": requested_voice_mode,
            "asr_provider": assistant_data.asr_provider or "openai",
            "tts_provider": assistant_data.tts_provider or "openai",
            # ASR Configuration
            "asr_language": assistant_data.asr_language or "en",
            "asr_model": assistant_data.asr_model,
            "asr_keywords": assistant_data.asr_keywords or [],
            # TTS Configuration
            "tts_model": assistant_data.tts_model,
            "tts_voice": assistant_data.tts_voice or assistant_data.voice,
            "tts_speed": assistant_data.tts_speed if assistant_data.tts_speed is not None else 1.0,
            # Transcription & Interruptions
            "enable_precise_transcript": assistant_data.enable_precise_transcript if assistant_data.enable_precise_transcript is not None else False,
            "interruption_threshold": assistant_data.interruption_threshold if assistant_data.interruption_threshold is not None else 2,
            # Voice Response Rate
            "response_rate": assistant_data.response_rate or "balanced",
            # User Online Detection
            "check_user_online": assistant_data.check_user_online if assistant_data.check_user_online is not None else True,
            # Buffer & Latency Settings
            "audio_buffer_size": assistant_data.audio_buffer_size if assistant_data.audio_buffer_size is not None else 200,
            # LLM Configuration
            "llm_provider": assistant_data.llm_provider or "openai",
            "llm_model": assistant_data.llm_model,
            "llm_max_tokens": assistant_data.llm_max_tokens if assistant_data.llm_max_tokens is not None else 150,
            # Language Configuration
            "bot_language": assistant_data.bot_language or "en",
            # VAD & Noise Suppression Configuration
            "noise_suppression_level": assistant_data.noise_suppression_level or "medium",
            "vad_threshold": assistant_data.vad_threshold if assistant_data.vad_threshold is not None else 0.4,
            "vad_prefix_padding_ms": assistant_data.vad_prefix_padding_ms if assistant_data.vad_prefix_padding_ms is not None else 300,
            "vad_silence_duration_ms": assistant_data.vad_silence_duration_ms if assistant_data.vad_silence_duration_ms is not None else 500,
            "vad_min_speech_ms": assistant_data.vad_min_speech_ms if assistant_data.vad_min_speech_ms is not None else 150,
            "vad_min_silence_ms": assistant_data.vad_min_silence_ms if assistant_data.vad_min_silence_ms is not None else 200,
            # Real-time Interruption & Streaming Mode
            "enable_interruption": assistant_data.enable_interruption if assistant_data.enable_interruption is not None else True,
            "interruption_probability_threshold": assistant_data.interruption_probability_threshold if assistant_data.interruption_probability_threshold is not None else 0.6,
            "interruption_min_chunks": assistant_data.interruption_min_chunks if assistant_data.interruption_min_chunks is not None else 2,
            "use_streaming_mode": assistant_data.use_streaming_mode if assistant_data.use_streaming_mode is not None else False,
            # Background Audio Configuration
            "background_audio_enabled": assistant_data.background_audio_enabled if assistant_data.background_audio_enabled is not None else False,
            "background_audio_type": "custom",  # Always use custom audio
            "background_audio_volume": assistant_data.background_audio_volume if assistant_data.background_audio_volume is not None else 0.25,
            # Workflow Integration
            "assigned_workflows": assistant_data.assigned_workflows or [],
            "workflow_trigger_events": assistant_data.workflow_trigger_events or ["CALL_COMPLETED"],
            "created_at": now,
            "updated_at": now
        }

        # Don't store API keys - system uses .env key
        # Legacy fields kept as None for backwards compatibility
        assistant_doc["api_key_id"] = None
        assistant_doc["openai_api_key"] = None

        result = assistants_collection.insert_one(assistant_doc)
        logger.info(f"AI assistant created with ID: {result.inserted_id} (using system API key)")

        # No API key metadata since we're using system key
        api_key_metadata = None
        has_api_key_value = True  # Always true since system key is always available

        return AIAssistantResponse(
            id=str(result.inserted_id),
            user_id=str(assistant_data.user_id),
            name=assistant_data.name,
            system_message=assistant_data.system_message,
            voice=assistant_data.voice,
            temperature=assistant_data.temperature,
            call_greeting=call_greeting,
            has_api_key=has_api_key_value,
            api_key_id=None,  # No user API key - system key used
            api_key_label="System API Key",  # Indicate system key is being used
            api_key_provider="openai",  # Always OpenAI from .env
            knowledge_base_files=[],  # New assistants start with no knowledge base
            has_knowledge_base=False,
            calendar_account_id=str(calendar_account_obj_id) if calendar_account_obj_id else None,
            calendar_account_email=calendar_account_email,
            calendar_account_ids=[str(obj_id) for obj_id in calendar_account_obj_ids],
            calendar_enabled=assistant_data.calendar_enabled if assistant_data.calendar_enabled is not None else False,
            last_calendar_used_index=-1,
            voice_mode=requested_voice_mode,
            asr_provider=assistant_data.asr_provider or "openai",
            tts_provider=assistant_data.tts_provider or "openai",
            # ASR Configuration
            asr_language=assistant_data.asr_language or "en",
            asr_model=assistant_data.asr_model,
            asr_keywords=assistant_data.asr_keywords or [],
            # TTS Configuration
            tts_model=assistant_data.tts_model,
            tts_speed=assistant_data.tts_speed if assistant_data.tts_speed is not None else 1.0,
            tts_voice=assistant_data.tts_voice or assistant_data.voice,
            # Transcription & Interruptions
            enable_precise_transcript=assistant_data.enable_precise_transcript if assistant_data.enable_precise_transcript is not None else False,
            interruption_threshold=assistant_data.interruption_threshold if assistant_data.interruption_threshold is not None else 2,
            # Voice Response Rate
            response_rate=assistant_data.response_rate or "balanced",
            # User Online Detection
            check_user_online=assistant_data.check_user_online if assistant_data.check_user_online is not None else True,
            # Buffer & Latency Settings
            audio_buffer_size=assistant_data.audio_buffer_size if assistant_data.audio_buffer_size is not None else 200,
            # LLM Configuration
            llm_provider=assistant_data.llm_provider or "openai",
            llm_model=assistant_data.llm_model,
            llm_max_tokens=assistant_data.llm_max_tokens if assistant_data.llm_max_tokens is not None else 150,
            # Language Configuration
            bot_language=assistant_data.bot_language or "en",
            # VAD & Noise Suppression Configuration
            noise_suppression_level=assistant_data.noise_suppression_level or "medium",
            vad_threshold=assistant_data.vad_threshold if assistant_data.vad_threshold is not None else 0.4,
            vad_prefix_padding_ms=assistant_data.vad_prefix_padding_ms if assistant_data.vad_prefix_padding_ms is not None else 300,
            vad_silence_duration_ms=assistant_data.vad_silence_duration_ms if assistant_data.vad_silence_duration_ms is not None else 500,
            vad_min_speech_ms=assistant_data.vad_min_speech_ms if assistant_data.vad_min_speech_ms is not None else 150,
            vad_min_silence_ms=assistant_data.vad_min_silence_ms if assistant_data.vad_min_silence_ms is not None else 200,
            # Real-time Interruption & Streaming Mode
            enable_interruption=assistant_data.enable_interruption if assistant_data.enable_interruption is not None else True,
            interruption_probability_threshold=assistant_data.interruption_probability_threshold if assistant_data.interruption_probability_threshold is not None else 0.6,
            interruption_min_chunks=assistant_data.interruption_min_chunks if assistant_data.interruption_min_chunks is not None else 2,
            use_streaming_mode=assistant_data.use_streaming_mode if assistant_data.use_streaming_mode is not None else False,
            # Background Audio Configuration
            background_audio_enabled=assistant_data.background_audio_enabled if assistant_data.background_audio_enabled is not None else False,
            background_audio_type="custom",  # Always use custom audio
            background_audio_volume=assistant_data.background_audio_volume if assistant_data.background_audio_volume is not None else 0.25,
            # Workflow Integration
            assigned_workflows=assistant_data.assigned_workflows or [],
            workflow_trigger_events=assistant_data.workflow_trigger_events or ["CALL_COMPLETED"],
            created_at=now.isoformat() + "Z",
            updated_at=now.isoformat() + "Z"
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error creating AI assistant: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create AI assistant: {str(error)}"
        )

@router.get("/user/{user_id}", response_model=AIAssistantListResponse, status_code=status.HTTP_200_OK)
async def get_user_assistants(user_id: str):
    """
    Get all AI assistants for a specific user
    Cached for 10 seconds to handle high concurrency and blazing fast page loads

    Args:
        user_id: User ID

    Returns:
        AIAssistantListResponse: List of user's assistants

    Raises:
        HTTPException: If user not found or error occurs
    """
    try:
        # Check cache first (10s cache for blazing fast loads)
        from app.utils.cache import get_from_cache, set_to_cache, generate_cache_key
        cache_key = generate_cache_key("assistants:user", user_id)
        cached_result = await get_from_cache(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for assistants: {user_id}")
            return cached_result
        db = Database.get_db()
        assistants_collection = db['assistants']
        api_keys_collection = db['api_keys']
        api_keys_collection = db['api_keys']
        api_keys_collection = db['api_keys']

        logger.info(f"Fetching AI assistants for user: {user_id}")

        # Convert user_id to ObjectId
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        # Find all assistants for this user
        assistants_cursor = assistants_collection.find({"user_id": user_obj_id})
        api_keys_collection = db['api_keys']
        calendar_accounts_collection = db['calendar_accounts']
        api_key_cache: Dict[str, Optional[Dict[str, str]]] = {}
        calendar_cache: Dict[str, Optional[Dict[str, str]]] = {}
        assistants = []

        for assistant in assistants_cursor:
            # Get knowledge base files
            kb_files = []
            for file_data in assistant.get('knowledge_base_files', []):
                kb_files.append(KnowledgeBaseFile(
                    filename=file_data['filename'],
                    file_type=file_data['file_type'],
                    file_size=file_data['file_size'],
                    uploaded_at=file_data['uploaded_at'].isoformat() + "Z",
                    file_path=file_data['file_path']
                ))

            # Resolve API key metadata - check environment variables first (deployment mode)
            api_key_metadata = None
            import os
            
            # Get providers used by this assistant
            asr_provider = assistant.get('asr_provider', 'openai').lower()
            tts_provider = assistant.get('tts_provider', 'openai').lower()
            llm_provider = assistant.get('llm_provider', 'openai').lower()
            voice_mode = assistant.get('voice_mode', 'realtime').lower()
            
            # Check if system API keys are available in environment (deployment mode)
            has_system_key = False
            system_provider = None
            
            # Map providers to environment variables
            env_var_map = {
                'openai': 'OPENAI_API_KEY',
                'openai-realtime': 'OPENAI_API_KEY',
                'deepgram': 'DEEPGRAM_API_KEY',
                'sarvam': 'SARVAM_API_KEY',
                'cartesia': 'CARTESIA_API_KEY',
                'elevenlabs': 'ELEVENLABS_API_KEY',
                'groq': 'GROQ_API_KEY',
                'anthropic': 'ANTHROPIC_API_KEY'
            }
            
            # Check for OpenAI key first (most common, used by realtime mode)
            if voice_mode == 'realtime' or 'realtime' in llm_provider:
                if os.getenv('OPENAI_API_KEY'):
                    has_system_key = True
                    system_provider = 'openai'
            else:
                # Check custom providers
                for provider in [asr_provider, tts_provider, llm_provider]:
                    env_var = env_var_map.get(provider)
                    if env_var and os.getenv(env_var):
                        has_system_key = True
                        system_provider = provider
                        break
            
            if has_system_key:
                # System API key from environment (deployment mode)
                api_key_metadata = {
                    "id": None,
                    "label": "System API Key",
                    "provider": system_provider or 'openai'
                }
            else:
                # Fallback to database keys (for backwards compatibility)
                key_identifier = assistant.get('api_key_id')
                if key_identifier:
                    cache_key = str(key_identifier)
                    if cache_key not in api_key_cache:
                        api_key_cache[cache_key] = resolve_api_key_metadata(api_keys_collection, key_identifier)
                    api_key_metadata = api_key_cache.get(cache_key)
                elif assistant.get('openai_api_key'):
                    api_key_metadata = {
                        "id": None,
                        "label": "Direct key",
                        "provider": "openai"
                    }

            call_greeting = assistant.get('call_greeting') or DEFAULT_CALL_GREETING
            if isinstance(call_greeting, str):
                call_greeting = call_greeting.strip()
            if not call_greeting:
                call_greeting = DEFAULT_CALL_GREETING

            # Resolve calendar account metadata
            calendar_metadata = None
            calendar_id = assistant.get('calendar_account_id')
            if calendar_id:
                cache_key = str(calendar_id)
                if cache_key not in calendar_cache:
                    calendar_cache[cache_key] = resolve_calendar_account_metadata(calendar_accounts_collection, calendar_id)
                calendar_metadata = calendar_cache.get(cache_key)

            assistants.append(AIAssistantResponse(
                id=str(assistant['_id']),
                user_id=str(assistant['user_id']),
                name=assistant['name'],
                system_message=assistant['system_message'],
                voice=assistant['voice'],
                temperature=assistant['temperature'],
                call_greeting=call_greeting,
                has_api_key=assistant_has_api_key(assistant),
                api_key_id=api_key_metadata.get("id") if api_key_metadata else None,
                api_key_label=api_key_metadata.get("label") if api_key_metadata else None,
                api_key_provider=api_key_metadata.get("provider") if api_key_metadata else None,
                knowledge_base_files=kb_files,
                has_knowledge_base=len(kb_files) > 0,
                calendar_account_id=calendar_metadata.get("id") if calendar_metadata else None,
                calendar_account_email=calendar_metadata.get("email") if calendar_metadata else None,
                voice_mode=assistant.get('voice_mode', 'realtime'),
                asr_provider=assistant.get('asr_provider', 'openai'),
                tts_provider=assistant.get('tts_provider', 'openai'),
                # ASR Configuration
                asr_language=assistant.get('asr_language', 'en'),
                asr_model=assistant.get('asr_model'),
                asr_keywords=assistant.get('asr_keywords', []),
                # TTS Configuration
                tts_model=assistant.get('tts_model'),
                tts_speed=assistant.get('tts_speed', 1.0),
                tts_voice=assistant.get('tts_voice') or assistant.get('voice'),
                # Transcription & Interruptions
                enable_precise_transcript=assistant.get('enable_precise_transcript', False),
                interruption_threshold=assistant.get('interruption_threshold', 2),
                # Voice Response Rate
                response_rate=assistant.get('response_rate', 'balanced'),
                # User Online Detection
                check_user_online=assistant.get('check_user_online', True),
                # Buffer & Latency Settings
                audio_buffer_size=assistant.get('audio_buffer_size', 200),
                # LLM Configuration
                llm_provider=assistant.get('llm_provider', 'openai'),
                llm_model=assistant.get('llm_model'),
                llm_max_tokens=assistant.get('llm_max_tokens', 150),
                # Language Configuration
                bot_language=assistant.get('bot_language', 'en'),
                # VAD & Noise Suppression Configuration
                noise_suppression_level=assistant.get('noise_suppression_level', 'medium'),
                vad_threshold=assistant.get('vad_threshold', 0.4),
                vad_prefix_padding_ms=assistant.get('vad_prefix_padding_ms', 300),
                vad_silence_duration_ms=assistant.get('vad_silence_duration_ms', 500),
                vad_min_speech_ms=assistant.get('vad_min_speech_ms', 150),
                vad_min_silence_ms=assistant.get('vad_min_silence_ms', 200),
                # Real-time Interruption & Streaming Mode
                enable_interruption=assistant.get('enable_interruption', True),
                interruption_probability_threshold=assistant.get('interruption_probability_threshold', 0.6),
                interruption_min_chunks=assistant.get('interruption_min_chunks', 2),
                use_streaming_mode=assistant.get('use_streaming_mode', False),
                # Background Audio Configuration
                background_audio_enabled=assistant.get('background_audio_enabled', False),
                background_audio_type="custom",  # Always use custom audio
                background_audio_volume=assistant.get('background_audio_volume', 0.25),
                calendar_account_ids=[str(obj_id) for obj_id in assistant.get('calendar_account_ids', [])],
                calendar_enabled=assistant.get('calendar_enabled', False),
                last_calendar_used_index=assistant.get('last_calendar_used_index', -1),
                # Workflow Integration
                assigned_workflows=assistant.get('assigned_workflows', []),
                workflow_trigger_events=assistant.get('workflow_trigger_events', ['CALL_COMPLETED']),
                created_at=assistant['created_at'].isoformat() + "Z",
                updated_at=assistant['updated_at'].isoformat() + "Z"
            ))

        logger.info(f"Found {len(assistants)} assistants for user {user_id}")

        result = AIAssistantListResponse(
            assistants=assistants,
            total=len(assistants)
        )
        
        # Cache the result for 10 seconds (blazing fast page loads)
        from app.utils.cache import set_to_cache, generate_cache_key
        cache_key = generate_cache_key("assistants:user", user_id)
        await set_to_cache(cache_key, result.dict(), expire=10)
        
        return result

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error fetching AI assistants: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch AI assistants: {str(error)}"
        )

@router.get("/{assistant_id}", response_model=AIAssistantResponse, status_code=status.HTTP_200_OK)
async def get_assistant(assistant_id: str):
    """
    Get a specific AI assistant by ID

    Args:
        assistant_id: Assistant ID

    Returns:
        AIAssistantResponse: Assistant details

    Raises:
        HTTPException: If assistant not found or error occurs
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        logger.info(f"Fetching AI assistant: {assistant_id}")

        # Convert to ObjectId
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        assistant = assistants_collection.find_one({"_id": assistant_obj_id})

        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        kb_files = []
        for file_data in assistant.get('knowledge_base_files', []):
            kb_files.append(KnowledgeBaseFile(
                filename=file_data['filename'],
                file_type=file_data['file_type'],
                file_size=file_data['file_size'],
                uploaded_at=file_data['uploaded_at'].isoformat() + "Z",
                file_path=file_data['file_path']
            ))

        # Resolve API key metadata - check environment variables first (deployment mode)
        api_key_metadata = None
        api_keys_collection = db['api_keys']
        import os
        
        # Get providers used by this assistant
        asr_provider = assistant.get('asr_provider', 'openai').lower()
        tts_provider = assistant.get('tts_provider', 'openai').lower()
        llm_provider = assistant.get('llm_provider', 'openai').lower()
        voice_mode = assistant.get('voice_mode', 'realtime').lower()
        
        # Check if system API keys are available in environment (deployment mode)
        has_system_key = False
        system_provider = None
        
        # Map providers to environment variables
        env_var_map = {
            'openai': 'OPENAI_API_KEY',
            'openai-realtime': 'OPENAI_API_KEY',
            'deepgram': 'DEEPGRAM_API_KEY',
            'sarvam': 'SARVAM_API_KEY',
            'cartesia': 'CARTESIA_API_KEY',
            'elevenlabs': 'ELEVENLABS_API_KEY',
            'groq': 'GROQ_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY'
        }
        
        # Check for OpenAI key first (most common, used by realtime mode)
        if voice_mode == 'realtime' or 'realtime' in llm_provider:
            if os.getenv('OPENAI_API_KEY'):
                has_system_key = True
                system_provider = 'openai'
        else:
            # Check custom providers
            for provider in [asr_provider, tts_provider, llm_provider]:
                env_var = env_var_map.get(provider)
                if env_var and os.getenv(env_var):
                    has_system_key = True
                    system_provider = provider
                    break
        
        if has_system_key:
            # System API key from environment (deployment mode)
            api_key_metadata = {
                "id": None,
                "label": "System API Key",
                "provider": system_provider or 'openai'
            }
        else:
            # Fallback to database keys (for backwards compatibility)
            if assistant.get('api_key_id'):
                api_key_metadata = resolve_api_key_metadata(api_keys_collection, assistant.get('api_key_id'))
            elif assistant.get('openai_api_key'):
                api_key_metadata = {
                    "id": None,
                    "label": "Direct key",
                    "provider": "openai"
                }

        call_greeting = assistant.get('call_greeting') or DEFAULT_CALL_GREETING
        if isinstance(call_greeting, str):
            call_greeting = call_greeting.strip()
        if not call_greeting:
            call_greeting = DEFAULT_CALL_GREETING

        # Resolve calendar account metadata
        calendar_metadata = None
        calendar_accounts_collection = db['calendar_accounts']
        if assistant.get('calendar_account_id'):
            calendar_metadata = resolve_calendar_account_metadata(
                calendar_accounts_collection,
                assistant.get('calendar_account_id')
            )

        return AIAssistantResponse(
            id=str(assistant['_id']),
            user_id=str(assistant['user_id']),
            name=assistant['name'],
            system_message=assistant['system_message'],
            voice=assistant['voice'],
            temperature=assistant['temperature'],
            call_greeting=call_greeting,
            has_api_key=assistant_has_api_key(assistant),
            api_key_id=api_key_metadata.get("id") if api_key_metadata else None,
            api_key_label=api_key_metadata.get("label") if api_key_metadata else None,
            api_key_provider=api_key_metadata.get("provider") if api_key_metadata else None,
            knowledge_base_files=kb_files,
            has_knowledge_base=len(kb_files) > 0,
            calendar_account_id=calendar_metadata.get("id") if calendar_metadata else None,
            calendar_account_email=calendar_metadata.get("email") if calendar_metadata else None,
            calendar_account_ids=[str(obj_id) for obj_id in assistant.get('calendar_account_ids', [])],
            calendar_enabled=assistant.get('calendar_enabled', False),
            last_calendar_used_index=assistant.get('last_calendar_used_index', -1),
            voice_mode=assistant.get('voice_mode', 'realtime'),
            asr_provider=assistant.get('asr_provider', 'openai'),
            tts_provider=assistant.get('tts_provider', 'openai'),
            # ASR Configuration
            asr_language=assistant.get('asr_language', 'en'),
            asr_model=assistant.get('asr_model'),
            asr_keywords=assistant.get('asr_keywords', []),
            # TTS Configuration
            tts_model=assistant.get('tts_model'),
            tts_speed=assistant.get('tts_speed', 1.0),
            tts_voice=assistant.get('tts_voice') or assistant.get('voice'),
            # Transcription & Interruptions
            enable_precise_transcript=assistant.get('enable_precise_transcript', False),
            interruption_threshold=assistant.get('interruption_threshold', 2),
            # Voice Response Rate
            response_rate=assistant.get('response_rate', 'balanced'),
            # User Online Detection
            check_user_online=assistant.get('check_user_online', True),
            # Buffer & Latency Settings
            audio_buffer_size=assistant.get('audio_buffer_size', 200),
            # LLM Configuration
            llm_provider=assistant.get('llm_provider', 'openai'),
            llm_model=assistant.get('llm_model'),
            llm_max_tokens=assistant.get('llm_max_tokens', 150),
            # Language Configuration
            bot_language=assistant.get('bot_language', 'en'),
            # VAD & Noise Suppression Configuration
            noise_suppression_level=assistant.get('noise_suppression_level', 'medium'),
            vad_threshold=assistant.get('vad_threshold', 0.4),
            vad_prefix_padding_ms=assistant.get('vad_prefix_padding_ms', 300),
            vad_silence_duration_ms=assistant.get('vad_silence_duration_ms', 500),
            vad_min_speech_ms=assistant.get('vad_min_speech_ms', 150),
            vad_min_silence_ms=assistant.get('vad_min_silence_ms', 200),
            # Real-time Interruption & Streaming Mode
            enable_interruption=assistant.get('enable_interruption', True),
            interruption_probability_threshold=assistant.get('interruption_probability_threshold', 0.6),
            interruption_min_chunks=assistant.get('interruption_min_chunks', 2),
            use_streaming_mode=assistant.get('use_streaming_mode', False),
            # Background Audio Configuration
            background_audio_enabled=assistant.get('background_audio_enabled', False),
            background_audio_type="custom",  # Always use custom audio
            background_audio_volume=assistant.get('background_audio_volume', 0.25),
            # Workflow Integration
            assigned_workflows=assistant.get('assigned_workflows', []),
            workflow_trigger_events=assistant.get('workflow_trigger_events', ['CALL_COMPLETED']),
            created_at=assistant['created_at'].isoformat() + "Z",
            updated_at=assistant['updated_at'].isoformat() + "Z"
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error fetching AI assistant: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch AI assistant: {str(error)}"
        )

@router.put("/{assistant_id}", response_model=AIAssistantResponse, status_code=status.HTTP_200_OK)
async def update_assistant(assistant_id: str, update_data: AIAssistantUpdate):
    """
    Update an existing AI assistant

    Args:
        assistant_id: Assistant ID
        update_data: Fields to update

    Returns:
        AIAssistantResponse: Updated assistant details

    Raises:
        HTTPException: If assistant not found or error occurs
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']
        api_keys_collection = db['api_keys']

        logger.info(f"Updating AI assistant: {assistant_id}")

        # Convert to ObjectId
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        # Check if assistant exists
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        # Build update document
        update_doc = {"updated_at": datetime.utcnow()}

        if update_data.voice_mode is not None:
            normalized_voice_mode = (update_data.voice_mode or "realtime").lower()
            if normalized_voice_mode not in ("realtime", "custom"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="voice_mode must be either 'realtime' or 'custom'"
                )
            update_doc["voice_mode"] = normalized_voice_mode

        if update_data.name is not None:
            update_doc["name"] = update_data.name
        if update_data.system_message is not None:
            update_doc["system_message"] = update_data.system_message
        if update_data.voice is not None:
            update_doc["voice"] = update_data.voice
        if update_data.temperature is not None:
            update_doc["temperature"] = update_data.temperature
        if update_data.call_greeting is not None:
            greeting_value = update_data.call_greeting.strip() if isinstance(update_data.call_greeting, str) else ""
            update_doc["call_greeting"] = greeting_value or DEFAULT_CALL_GREETING

        # API keys are ignored - system uses .env OPENAI_API_KEY
        # Keep fields as None for backwards compatibility
        if update_data.api_key_id is not None or update_data.openai_api_key is not None:
            logger.info("[ASSISTANT] API key update ignored - using system API key from environment")
            update_doc["api_key_id"] = None
            update_doc["openai_api_key"] = None

        # Handle provider updates
        if update_data.asr_provider is not None:
            update_doc["asr_provider"] = update_data.asr_provider
        if update_data.tts_provider is not None:
            update_doc["tts_provider"] = update_data.tts_provider
        if update_data.asr_language is not None:
            update_doc["asr_language"] = update_data.asr_language
        if update_data.asr_model is not None:
            update_doc["asr_model"] = update_data.asr_model
        if update_data.asr_keywords is not None:
            update_doc["asr_keywords"] = update_data.asr_keywords
        if update_data.tts_model is not None:
            update_doc["tts_model"] = update_data.tts_model
        if update_data.tts_speed is not None:
            update_doc["tts_speed"] = update_data.tts_speed
        if update_data.tts_voice is not None:
            update_doc["tts_voice"] = update_data.tts_voice
        if update_data.enable_precise_transcript is not None:
            update_doc["enable_precise_transcript"] = update_data.enable_precise_transcript
        if update_data.interruption_threshold is not None:
            update_doc["interruption_threshold"] = update_data.interruption_threshold
        if update_data.response_rate is not None:
            update_doc["response_rate"] = update_data.response_rate
        if update_data.check_user_online is not None:
            update_doc["check_user_online"] = update_data.check_user_online
        if update_data.audio_buffer_size is not None:
            update_doc["audio_buffer_size"] = update_data.audio_buffer_size
        if update_data.llm_provider is not None:
            update_doc["llm_provider"] = update_data.llm_provider
        if update_data.llm_model is not None:
            update_doc["llm_model"] = update_data.llm_model
        if update_data.llm_max_tokens is not None:
            update_doc["llm_max_tokens"] = update_data.llm_max_tokens
        if update_data.bot_language is not None:
            update_doc["bot_language"] = update_data.bot_language

        # Handle VAD & Noise Suppression updates
        if update_data.noise_suppression_level is not None:
            update_doc["noise_suppression_level"] = update_data.noise_suppression_level
        if update_data.vad_threshold is not None:
            update_doc["vad_threshold"] = update_data.vad_threshold
        if update_data.vad_prefix_padding_ms is not None:
            update_doc["vad_prefix_padding_ms"] = update_data.vad_prefix_padding_ms
        if update_data.vad_silence_duration_ms is not None:
            update_doc["vad_silence_duration_ms"] = update_data.vad_silence_duration_ms
        if update_data.vad_min_speech_ms is not None:
            update_doc["vad_min_speech_ms"] = update_data.vad_min_speech_ms
        if update_data.vad_min_silence_ms is not None:
            update_doc["vad_min_silence_ms"] = update_data.vad_min_silence_ms

        # Handle Real-time Interruption & Streaming Mode updates
        if update_data.enable_interruption is not None:
            update_doc["enable_interruption"] = update_data.enable_interruption
        if update_data.interruption_probability_threshold is not None:
            update_doc["interruption_probability_threshold"] = update_data.interruption_probability_threshold
        if update_data.interruption_min_chunks is not None:
            update_doc["interruption_min_chunks"] = update_data.interruption_min_chunks
        if update_data.use_streaming_mode is not None:
            update_doc["use_streaming_mode"] = update_data.use_streaming_mode

        # Handle Background Audio updates
        if update_data.background_audio_enabled is not None:
            update_doc["background_audio_enabled"] = update_data.background_audio_enabled
        if update_data.background_audio_type is not None:
            update_doc["background_audio_type"] = update_data.background_audio_type
        if update_data.background_audio_volume is not None:
            update_doc["background_audio_volume"] = update_data.background_audio_volume

        # Handle calendar_account_id update (legacy support)
        if update_data.calendar_account_id is not None:
            if update_data.calendar_account_id == "":
                update_doc["calendar_account_id"] = None
            else:
                try:
                    calendar_account_obj_id = ObjectId(update_data.calendar_account_id)
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid calendar_account_id format"
                    )
                calendar_accounts_collection = db['calendar_accounts']
                calendar_account = calendar_accounts_collection.find_one({
                    "_id": calendar_account_obj_id,
                    "user_id": assistant['user_id']
                })
                if not calendar_account:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Calendar account not found or does not belong to user"
                    )
                update_doc["calendar_account_id"] = calendar_account_obj_id

        # Handle calendar_account_ids update (new multi-calendar support)
        if update_data.calendar_account_ids is not None:
            calendar_accounts_collection = db['calendar_accounts']
            calendar_account_obj_ids = []
            for cal_id in update_data.calendar_account_ids:
                try:
                    cal_obj_id = ObjectId(cal_id)
                    calendar_account = calendar_accounts_collection.find_one({
                        "_id": cal_obj_id,
                        "user_id": assistant['user_id']
                    })
                    if not calendar_account:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Calendar account {cal_id} not found or does not belong to user"
                        )
                    calendar_account_obj_ids.append(cal_obj_id)
                except Exception as e:
                    if isinstance(e, HTTPException):
                        raise
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid calendar_account_id format: {cal_id}"
                    )
            update_doc["calendar_account_ids"] = calendar_account_obj_ids

        # Handle calendar_enabled update
        if update_data.calendar_enabled is not None:
            update_doc["calendar_enabled"] = update_data.calendar_enabled

        # Handle workflow assignment update
        if update_data.assigned_workflows is not None:
            # Validate workflows exist and belong to user
            workflows_collection = db['workflows']
            valid_workflow_ids = []
            # Convert assistant's user_id to string for comparison (workflows store user_id as string)
            assistant_user_id_str = str(assistant['user_id'])
            for wf_id in update_data.assigned_workflows:
                try:
                    wf_obj_id = ObjectId(wf_id)
                    workflow = workflows_collection.find_one({
                        "_id": wf_obj_id,
                        "user_id": assistant_user_id_str
                    })
                    if workflow:
                        valid_workflow_ids.append(wf_id)
                    else:
                        logger.warning(f"Workflow {wf_id} not found or doesn't belong to user {assistant_user_id_str}")
                except Exception as e:
                    logger.warning(f"Invalid workflow ID format: {wf_id} - {e}")
            update_doc["assigned_workflows"] = valid_workflow_ids
            logger.info(f"Assigned {len(valid_workflow_ids)} workflows to assistant {assistant_id}")

        if update_data.workflow_trigger_events is not None:
            # Validate trigger events are valid
            valid_events = ["CALL_COMPLETED", "CALL_FAILED", "CALL_NO_ANSWER", "CALL_BUSY", "CALL_VOICEMAIL"]
            update_doc["workflow_trigger_events"] = [e for e in update_data.workflow_trigger_events if e in valid_events]

        # Update the assistant
        assistants_collection.update_one(
            {"_id": assistant_obj_id},
            {"$set": update_doc}
        )

        # Fetch updated assistant
        updated_assistant = assistants_collection.find_one({"_id": assistant_obj_id})

        # Invalidate cache for this user's assistants
        try:
            from app.utils.cache import delete_from_cache, generate_cache_key
            user_id = str(assistant['user_id'])
            cache_key = generate_cache_key("assistants:user", user_id)
            await delete_from_cache(cache_key)
            logger.debug(f"Invalidated assistants cache for user {user_id}")
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate cache: {cache_error}")

        logger.info(f"AI assistant {assistant_id} updated successfully")

        # Get knowledge base files
        kb_files = []
        for file_data in updated_assistant.get('knowledge_base_files', []):
            kb_files.append(KnowledgeBaseFile(
                filename=file_data['filename'],
                file_type=file_data['file_type'],
                file_size=file_data['file_size'],
                uploaded_at=file_data['uploaded_at'].isoformat() + "Z",
                file_path=file_data['file_path']
            ))

        # Resolve API key metadata - check environment variables first (deployment mode)
        api_key_metadata = None
        import os
        
        # Get providers used by this assistant
        asr_provider = updated_assistant.get('asr_provider', 'openai').lower()
        tts_provider = updated_assistant.get('tts_provider', 'openai').lower()
        llm_provider = updated_assistant.get('llm_provider', 'openai').lower()
        voice_mode = updated_assistant.get('voice_mode', 'realtime').lower()
        
        # Check if system API keys are available in environment (deployment mode)
        has_system_key = False
        system_provider = None
        
        # Map providers to environment variables
        env_var_map = {
            'openai': 'OPENAI_API_KEY',
            'openai-realtime': 'OPENAI_API_KEY',
            'deepgram': 'DEEPGRAM_API_KEY',
            'sarvam': 'SARVAM_API_KEY',
            'cartesia': 'CARTESIA_API_KEY',
            'elevenlabs': 'ELEVENLABS_API_KEY',
            'groq': 'GROQ_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY'
        }
        
        # Check for OpenAI key first (most common, used by realtime mode)
        if voice_mode == 'realtime' or 'realtime' in llm_provider:
            if os.getenv('OPENAI_API_KEY'):
                has_system_key = True
                system_provider = 'openai'
        else:
            # Check custom providers
            for provider in [asr_provider, tts_provider, llm_provider]:
                env_var = env_var_map.get(provider)
                if env_var and os.getenv(env_var):
                    has_system_key = True
                    system_provider = provider
                    break
        
        if has_system_key:
            # System API key from environment (deployment mode)
            api_key_metadata = {
                "id": None,
                "label": "System API Key",
                "provider": system_provider or 'openai'
            }
        else:
            # Fallback to database keys (for backwards compatibility)
            if updated_assistant.get('api_key_id'):
                api_key_metadata = resolve_api_key_metadata(api_keys_collection, updated_assistant.get('api_key_id'))
            elif updated_assistant.get('openai_api_key'):
                api_key_metadata = {
                    "id": None,
                    "label": "Direct key",
                    "provider": "openai"
                }

        call_greeting = updated_assistant.get('call_greeting') or DEFAULT_CALL_GREETING
        if isinstance(call_greeting, str):
            call_greeting = call_greeting.strip()
        if not call_greeting:
            call_greeting = DEFAULT_CALL_GREETING

        # Resolve calendar account metadata
        calendar_metadata = None
        calendar_accounts_collection = db['calendar_accounts']
        if updated_assistant.get('calendar_account_id'):
            calendar_metadata = resolve_calendar_account_metadata(
                calendar_accounts_collection,
                updated_assistant.get('calendar_account_id')
            )

        return AIAssistantResponse(
            id=str(updated_assistant['_id']),
            user_id=str(updated_assistant['user_id']),
            name=updated_assistant['name'],
            system_message=updated_assistant['system_message'],
            voice=updated_assistant['voice'],
            temperature=updated_assistant['temperature'],
            call_greeting=call_greeting,
            has_api_key=assistant_has_api_key(updated_assistant),
            api_key_id=api_key_metadata.get("id") if api_key_metadata else None,
            api_key_label=api_key_metadata.get("label") if api_key_metadata else None,
            api_key_provider=api_key_metadata.get("provider") if api_key_metadata else None,
            knowledge_base_files=kb_files,
            has_knowledge_base=len(kb_files) > 0,
            calendar_account_id=calendar_metadata.get("id") if calendar_metadata else None,
            calendar_account_email=calendar_metadata.get("email") if calendar_metadata else None,
            calendar_account_ids=[str(obj_id) for obj_id in updated_assistant.get('calendar_account_ids', [])],
            calendar_enabled=updated_assistant.get('calendar_enabled', False),
            last_calendar_used_index=updated_assistant.get('last_calendar_used_index', -1),
            voice_mode=updated_assistant.get('voice_mode', 'realtime'),
            asr_provider=updated_assistant.get('asr_provider', 'openai'),
            tts_provider=updated_assistant.get('tts_provider', 'openai'),
            # ASR Configuration
            asr_language=updated_assistant.get('asr_language', 'en'),
            asr_model=updated_assistant.get('asr_model'),
            asr_keywords=updated_assistant.get('asr_keywords', []),
            # TTS Configuration
            tts_model=updated_assistant.get('tts_model'),
            tts_speed=updated_assistant.get('tts_speed', 1.0),
            tts_voice=updated_assistant.get('tts_voice') or updated_assistant.get('voice'),
            # Transcription & Interruptions
            enable_precise_transcript=updated_assistant.get('enable_precise_transcript', False),
            interruption_threshold=updated_assistant.get('interruption_threshold', 2),
            # Voice Response Rate
            response_rate=updated_assistant.get('response_rate', 'balanced'),
            # User Online Detection
            check_user_online=updated_assistant.get('check_user_online', True),
            # Buffer & Latency Settings
            audio_buffer_size=updated_assistant.get('audio_buffer_size', 200),
            # LLM Configuration
            llm_provider=updated_assistant.get('llm_provider', 'openai'),
            llm_model=updated_assistant.get('llm_model'),
            llm_max_tokens=updated_assistant.get('llm_max_tokens', 150),
            # Language Configuration
            bot_language=updated_assistant.get('bot_language', 'en'),
            # VAD & Noise Suppression Configuration
            noise_suppression_level=updated_assistant.get('noise_suppression_level', 'medium'),
            vad_threshold=updated_assistant.get('vad_threshold', 0.4),
            vad_prefix_padding_ms=updated_assistant.get('vad_prefix_padding_ms', 300),
            vad_silence_duration_ms=updated_assistant.get('vad_silence_duration_ms', 500),
            vad_min_speech_ms=updated_assistant.get('vad_min_speech_ms', 150),
            vad_min_silence_ms=updated_assistant.get('vad_min_silence_ms', 200),
            # Real-time Interruption & Streaming Mode
            enable_interruption=updated_assistant.get('enable_interruption', True),
            interruption_probability_threshold=updated_assistant.get('interruption_probability_threshold', 0.6),
            interruption_min_chunks=updated_assistant.get('interruption_min_chunks', 2),
            use_streaming_mode=updated_assistant.get('use_streaming_mode', False),
            # Background Audio Configuration
            background_audio_enabled=updated_assistant.get('background_audio_enabled', False),
            background_audio_type="custom",  # Always use custom audio
            background_audio_volume=updated_assistant.get('background_audio_volume', 0.25),
            # Workflow Integration
            assigned_workflows=updated_assistant.get('assigned_workflows', []),
            workflow_trigger_events=updated_assistant.get('workflow_trigger_events', ['CALL_COMPLETED']),
            created_at=updated_assistant['created_at'].isoformat() + "Z",
            updated_at=updated_assistant['updated_at'].isoformat() + "Z"
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error updating AI assistant: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update AI assistant: {str(error)}"
        )

@router.delete("/{assistant_id}", response_model=DeleteResponse, status_code=status.HTTP_200_OK)
async def delete_assistant(assistant_id: str):
    """
    Delete an AI assistant

    Args:
        assistant_id: Assistant ID

    Returns:
        DeleteResponse: Success message

    Raises:
        HTTPException: If assistant not found or error occurs
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        logger.info(f"Deleting AI assistant: {assistant_id}")

        # Convert to ObjectId
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        # Delete the assistant
        result = assistants_collection.delete_one({"_id": assistant_obj_id})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        logger.info(f"AI assistant {assistant_id} deleted successfully")

        return DeleteResponse(message="AI assistant deleted successfully")

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error deleting AI assistant: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete AI assistant: {str(error)}"
        )

@router.post("/voice-demo", status_code=status.HTTP_200_OK)
async def generate_voice_demo(request: VoiceDemoRequest):
    """
    Generate a voice demo using OpenAI's TTS API with user's saved API key

    Args:
        request: Voice demo request with voice ID, user ID, and text

    Returns:
        Audio file (mp3) as streaming response

    Raises:
        HTTPException: If API key not found or error occurs
    """
    try:
        logger.info(f"Generating voice demo for voice: {request.voice}, user: {request.user_id}")

        db = Database.get_db()
        api_keys_collection = db['api_keys']

        # Validate user_id
        try:
            user_obj_id = ObjectId(request.user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        api_key_doc = None

        if request.api_key_id:
            try:
                api_key_obj_id = ObjectId(request.api_key_id)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid api_key_id format"
                )

            api_key_doc = api_keys_collection.find_one({
                "_id": api_key_obj_id,
                "user_id": user_obj_id,
            })

            if not api_key_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API key not found for this user"
                )

            if api_key_doc.get("provider") != "openai":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Voice previews currently require an OpenAI API key."
                )
        else:
            api_key_doc = api_keys_collection.find_one({
                "user_id": user_obj_id,
                "provider": "openai"
            })

            if not api_key_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No OpenAI API key found. Please add an OpenAI API key in Settings."
                )

        # Decrypt the API key
        try:
            openai_api_key = encryption_service.decrypt(api_key_doc['key'])
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt API key"
            )

        voice_to_use = request.voice
        model_name, resolved_voice = resolve_tts_model_and_voice(voice_to_use)
        if resolved_voice != voice_to_use:
            logger.info(
                "Using fallback voice '%s' (requested '%s') for demo",
                resolved_voice,
                voice_to_use,
            )

        # Call OpenAI TTS API
        async with httpx.AsyncClient() as client:
            async def request_tts(model: str, voice: str):
                return await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "input": request.text,
                        "voice": voice,
                        "response_format": "mp3"
                    },
                    timeout=30.0
                )

            response = await request_tts(model_name, resolved_voice)

            # If OpenAI rejects the requested voice, retry once with Alloy so the UI demo still plays something
            if response.status_code != 200:
                error_detail = "Failed to generate voice sample"
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error_detail = error_json['error'].get('message', error_detail)
                except Exception:
                    error_json = None

                logger.warning(
                    "Voice demo request failed (voice=%s, model=%s): %s",
                    resolved_voice,
                    model_name,
                    error_detail,
                )

                if resolved_voice != "alloy":
                    logger.info("Retrying voice demo with Alloy fallback")
                    fallback_response = await request_tts(DEFAULT_TTS_MODEL, "alloy")
                    if fallback_response.status_code == 200:
                        response = fallback_response
                        resolved_voice = "alloy"
                    else:
                        # Prefer original error message for transparency
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=error_detail
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=error_detail
                    )

            # Return audio as response
            return Response(
                content=response.content,
                media_type="audio/mpeg",
                headers={
                    "Content-Disposition": f"inline; filename=voice-demo-{resolved_voice}.mp3",
                    "X-Voice-Used": resolved_voice,
                    "X-Voice-Model": model_name,
                }
            )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error generating voice demo: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate voice demo: {str(error)}"
        )


# Translation endpoint for greeting preview
class TranslateTextRequest(BaseModel):
    text: str
    target_language: str
    language_name: str


class TranslateTextResponse(BaseModel):
    translated_text: str
    source_language: str = "en"
    target_language: str


@router.post("/translate-text", response_model=TranslateTextResponse)
async def translate_text(request: TranslateTextRequest):
    """
    Translate text to the target language using OpenAI GPT-4o-mini.
    Uses system API key from environment variables.
    """
    try:
        # Validate input
        if not request.text or not request.text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text to translate is required"
            )

        if not request.target_language or request.target_language == 'en':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target language is required and must not be English"
            )

        # Get system OpenAI API key from environment
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.error("[TRANSLATION] OPENAI_API_KEY not found in environment")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key not configured"
            )

        # Call OpenAI to translate
        from openai import OpenAI
        client = OpenAI(api_key=openai_api_key)

        logger.info(f"[TRANSLATION] Translating to {request.language_name}...")

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cheap for translation
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator. Translate the following text to {request.language_name}. Only return the translation without any additional text. Maintain the tone, formality, and intent of the original message."
                },
                {
                    "role": "user",
                    "content": request.text
                }
            ],
            temperature=0.3,  # Low temperature for consistent translations
            max_tokens=300
        )

        translated_text = response.choices[0].message.content.strip()

        if not translated_text:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Translation returned empty result"
            )

        logger.info(f"[TRANSLATION] Successfully translated to {request.language_name}: \"{translated_text}\"")

        return TranslateTextResponse(
            translated_text=translated_text,
            source_language="en",
            target_language=request.target_language
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error translating text: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to translate text: {str(error)}"
        )
