"""
Voice library and preferences API routes
"""
import asyncio
import httpx
from fastapi import APIRouter, HTTPException, status, Response
from typing import Optional, List
import io
import wave
from bson import ObjectId
from datetime import datetime
import logging

from app.models.voice import (
    VoiceMetadata,
    VoiceListResponse,
    SaveVoiceRequest,
    RemoveVoiceRequest,
    UniversalVoiceDemoRequest,
    UserVoicePreferences
)
from app.config.database import Database
from app.utils.encryption import encryption_service
from app.config.settings import settings
from app.services.call_handlers.offline_tts_handler import OfflinePiperTTS

router = APIRouter()
logger = logging.getLogger(__name__)

# Legacy catalog kept for reference only — not used by any route.
# VOICE_CATALOG has been replaced by ACTIVE_VOICE_CATALOG (Piper only).
VOICE_CATALOG: List[VoiceMetadata] = []


# Piper-only catalog used by Voice Lab and demo APIs.
ACTIVE_VOICE_CATALOG: List[VoiceMetadata] = [
    # American Female
    VoiceMetadata(
        id="en_US-lessac-medium",
        name="Lessac",
        provider="piper",
        gender="female",
        accent="American",
        language="en",
        description="American female voice optimized for voice agents - stable and natural",
        age_group="middle-aged",
        use_case="Voice Agent",
        model="medium"
    ),
    VoiceMetadata(
        id="en_US-lessac-high",
        name="Lessac HQ",
        provider="piper",
        gender="female",
        accent="American",
        language="en",
        description="High-quality American female voice for premium voice agent experiences",
        age_group="middle-aged",
        use_case="Voice Agent",
        model="high"
    ),
    VoiceMetadata(
        id="en_US-amy-medium",
        name="Amy",
        provider="piper",
        gender="female",
        accent="American",
        language="en",
        description="Friendly American female voice for warm conversational experiences",
        age_group="young",
        use_case="General Purpose",
        model="medium"
    ),
    VoiceMetadata(
        id="en_US-kathleen-low",
        name="Kathleen",
        provider="piper",
        gender="female",
        accent="American",
        language="en",
        description="Clear American female voice suitable for customer support and IVR",
        age_group="middle-aged",
        use_case="Customer Support",
        model="low"
    ),
    VoiceMetadata(
        id="en_US-arctic-medium",
        name="Arctic",
        provider="piper",
        gender="neutral",
        accent="American",
        language="en",
        description="Neutral American voice with balanced tone for professional use",
        age_group="middle-aged",
        use_case="General Purpose",
        model="medium"
    ),
    # American Male
    VoiceMetadata(
        id="en_US-ryan-medium",
        name="Ryan",
        provider="piper",
        gender="male",
        accent="American",
        language="en",
        description="American male voice with a clear, professional tone for voice agents",
        age_group="young",
        use_case="Voice Agent",
        model="medium"
    ),
    VoiceMetadata(
        id="en_US-ryan-high",
        name="Ryan HQ",
        provider="piper",
        gender="male",
        accent="American",
        language="en",
        description="High-quality American male voice for premium agent deployments",
        age_group="young",
        use_case="Voice Agent",
        model="high"
    ),
    VoiceMetadata(
        id="en_US-joe-medium",
        name="Joe",
        provider="piper",
        gender="male",
        accent="American",
        language="en",
        description="Casual American male voice great for conversational AI applications",
        age_group="middle-aged",
        use_case="Conversational",
        model="medium"
    ),
    VoiceMetadata(
        id="en_US-danny-low",
        name="Danny",
        provider="piper",
        gender="male",
        accent="American",
        language="en",
        description="Warm American male voice for customer-facing support scenarios",
        age_group="young",
        use_case="Customer Support",
        model="low"
    ),
    VoiceMetadata(
        id="en_US-kusal-medium",
        name="Kusal",
        provider="piper",
        gender="male",
        accent="American",
        language="en",
        description="Expressive American male voice with emotive characteristics",
        age_group="young",
        use_case="Emotive Character",
        model="medium"
    ),
    # British Female
    VoiceMetadata(
        id="en_GB-alba-medium",
        name="Alba",
        provider="piper",
        gender="female",
        accent="British",
        language="en",
        description="Polished British female voice for professional conversational experiences",
        age_group="middle-aged",
        use_case="General Purpose",
        model="medium"
    ),
    VoiceMetadata(
        id="en_GB-jenny-dioco-medium",
        name="Jenny",
        provider="piper",
        gender="female",
        accent="British",
        language="en",
        description="Warm British female voice ideal for customer service and IVR",
        age_group="young",
        use_case="Customer Support",
        model="medium"
    ),
    # British Male
    VoiceMetadata(
        id="en_GB-alan-medium",
        name="Alan",
        provider="piper",
        gender="male",
        accent="British",
        language="en",
        description="Authoritative British male voice for professional voice agents",
        age_group="middle-aged",
        use_case="Voice Agent",
        model="medium"
    ),
    # Australian
    VoiceMetadata(
        id="en_AU-natasha-medium",
        name="Natasha",
        provider="piper",
        gender="female",
        accent="Australian",
        language="en",
        description="Australian female voice with a friendly and approachable tone",
        age_group="young",
        use_case="General Purpose",
        model="medium"
    ),
    VoiceMetadata(
        id="en_AU-sam-medium",
        name="Sam",
        provider="piper",
        gender="male",
        accent="Australian",
        language="en",
        description="Australian male voice with a relaxed and clear conversational style",
        age_group="young",
        use_case="Conversational",
        model="medium"
    ),
    # Indian
    VoiceMetadata(
        id="hi_IN-priyamvada-medium",
        name="Priyamvada",
        provider="piper",
        gender="female",
        accent="Indian",
        language="hi",
        description="Hindi female voice tuned for natural local playback",
        age_group="young",
        use_case="Conversational",
        model="medium"
    ),
    VoiceMetadata(
        id="hi_IN-pratham-medium",
        name="Pratham",
        provider="piper",
        gender="male",
        accent="Indian",
        language="hi",
        description="Hindi male voice tuned for natural local playback",
        age_group="young",
        use_case="Conversational",
        model="medium"
    ),
]


async def fetch_elevenlabs_voices(api_key: str) -> List[VoiceMetadata]:
    """Fetch all voices from ElevenLabs API including user's custom voices"""
    voices = []
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                for voice in data.get("voices", []):
                    # Determine gender from labels
                    labels = voice.get("labels", {})
                    gender = labels.get("gender", "neutral")
                    if gender not in ["male", "female", "neutral"]:
                        gender = "neutral"

                    # Determine accent from labels
                    accent = labels.get("accent", "American")
                    if not accent:
                        accent = "American"

                    # Determine age group
                    age = labels.get("age", "middle-aged")
                    if age in ["young", "middle aged", "old"]:
                        age_group = age.replace(" ", "-")
                    else:
                        age_group = "middle-aged"

                    # Determine use case
                    use_case = labels.get("use case", labels.get("use_case", "General Purpose"))
                    if not use_case:
                        use_case = "General Purpose"

                    voice_metadata = VoiceMetadata(
                        id=voice.get("voice_id"),
                        name=voice.get("name", "Unknown"),
                        provider="elevenlabs",
                        gender=gender,
                        accent=accent,
                        language="en",  # ElevenLabs primarily supports English
                        description=voice.get("description") or f"{voice.get('name')} - ElevenLabs voice",
                        age_group=age_group if age_group in ["young", "middle-aged", "old"] else "middle-aged",
                        use_case=use_case,
                        model="eleven_turbo_v2_5"
                    )
                    voices.append(voice_metadata)

                logger.info(f"Fetched {len(voices)} voices from ElevenLabs API")
            else:
                logger.warning(f"Failed to fetch ElevenLabs voices: {response.status_code}")

    except Exception as e:
        logger.error(f"Error fetching ElevenLabs voices: {str(e)}")

    return voices


@router.get("/elevenlabs/sync")
async def sync_elevenlabs_voices(user_id: str):
    """
    Fetch all voices from user's ElevenLabs account including custom/cloned voices.

    This endpoint fetches voices directly from the ElevenLabs API using the user's API key,
    ensuring that any newly added voices in their ElevenLabs account are immediately available.

    Args:
    - user_id: User ID for API key lookup

    Returns:
    - List of all ElevenLabs voices (both default and custom)
    """
    try:
        db = Database.get_db()
        api_keys_collection = db['api_keys']

        # Validate user_id
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        # Find ElevenLabs API key
        api_key_doc = api_keys_collection.find_one({
            "user_id": user_obj_id,
            "provider": "custom",
            "$or": [
                {"label": {"$regex": "eleven", "$options": "i"}},
                {"description": {"$regex": "eleven", "$options": "i"}}
            ]
        })

        decrypted_api_key = None

        if api_key_doc:
            try:
                decrypted_api_key = encryption_service.decrypt(api_key_doc['key'])
            except Exception as e:
                logger.error(f"Failed to decrypt API key: {str(e)}")

        # Fallback to environment variable
        if not decrypted_api_key:
            decrypted_api_key = settings.elevenlabs_api_key

        if not decrypted_api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No ElevenLabs API key found. Please add an ElevenLabs API key in Settings."
            )

        # Fetch voices from ElevenLabs
        voices = await fetch_elevenlabs_voices(decrypted_api_key)

        return {
            "success": True,
            "voices": [v.model_dump() for v in voices],
            "total": len(voices),
            "provider": "elevenlabs",
            "message": f"Synced {len(voices)} voices from ElevenLabs"
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Failed to sync ElevenLabs voices: {str(error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync ElevenLabs voices: {str(error)}"
        )


@router.get("/list", response_model=VoiceListResponse)
async def get_all_voices(
    provider: Optional[str] = None,
    gender: Optional[str] = None,
    accent: Optional[str] = None,
    language: Optional[str] = None,
    user_id: Optional[str] = None,
    include_custom: bool = False
):
    """
    Get all available Piper voices with optional filtering

    Query Parameters:
    - provider: Filter by TTS provider (currently piper)
    - gender: Filter by gender (male, female, neutral)
    - accent: Filter by accent (American, British, Indian, Australian)
    - language: Filter by language code (en, hi, etc.)
    - user_id: User ID (required if include_custom=True)
    - include_custom: Reserved for backward compatibility

    Returns:
    - List of available Piper voices with complete metadata
    """
    try:
        filtered_voices = ACTIVE_VOICE_CATALOG.copy()

        # Legacy ElevenLabs sync is disabled in Piper-only mode.
        if include_custom and user_id and provider and provider.lower() == "elevenlabs":
            try:
                db = Database.get_db()
                api_keys_collection = db['api_keys']
                user_obj_id = ObjectId(user_id)

                # Legacy code path retained for backward compatibility.
                api_key_doc = api_keys_collection.find_one({
                    "user_id": user_obj_id,
                    "provider": "custom",
                    "$or": [
                        {"label": {"$regex": "eleven", "$options": "i"}},
                        {"description": {"$regex": "eleven", "$options": "i"}}
                    ]
                })

                decrypted_api_key = None
                if api_key_doc:
                    decrypted_api_key = encryption_service.decrypt(api_key_doc['key'])
                else:
                    decrypted_api_key = settings.elevenlabs_api_key

                if decrypted_api_key:
                    # Fetch fresh voices from ElevenLabs
                    elevenlabs_voices = await fetch_elevenlabs_voices(decrypted_api_key)

                    # Remove existing ElevenLabs voices from catalog
                    filtered_voices = [v for v in filtered_voices if v.provider != "elevenlabs"]

                    # Add fresh ElevenLabs voices
                    filtered_voices.extend(elevenlabs_voices)

                    logger.info(f"Replaced catalog ElevenLabs voices with {len(elevenlabs_voices)} live voices")

            except Exception as e:
                logger.warning(f"Could not fetch custom ElevenLabs voices: {str(e)}")
                # Continue with catalog voices

        # Apply filters
        if provider:
            filtered_voices = [v for v in filtered_voices if v.provider == provider.lower()]
        if gender:
            filtered_voices = [v for v in filtered_voices if v.gender == gender.lower()]
        if accent:
            filtered_voices = [v for v in filtered_voices if v.accent.lower() == accent.lower()]
        if language:
            filtered_voices = [v for v in filtered_voices if v.language == language.lower()]

        # Get unique providers
        unique_providers = list(set([v.provider for v in filtered_voices]))

        return VoiceListResponse(
            voices=filtered_voices,
            total=len(filtered_voices),
            providers=unique_providers
        )

    except Exception as error:
        logger.error(f"Failed to fetch voices: {str(error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch voices: {str(error)}"
        )


@router.get("/preferences/{user_id}")
async def get_user_voice_preferences(user_id: str):
    """
    Get user's saved voice preferences

    Args:
    - user_id: User ID

    Returns:
    - User's saved voices with full metadata
    """
    try:
        db = Database.get_db()
        preferences_collection = db['voice_preferences']

        # Validate user_id
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        # Find user preferences
        user_prefs = preferences_collection.find_one({"user_id": user_id})

        if not user_prefs:
            return {
                "user_id": user_id,
                "saved_voices": [],
                "total": 0
            }

        # Enrich saved voices with full metadata from catalog
        saved_voices = user_prefs.get("saved_voices", [])
        enriched_voices = []

        for saved_voice in saved_voices:
            # Find the voice in catalog
            voice_metadata = next(
                (v for v in ACTIVE_VOICE_CATALOG if v.id == saved_voice["voice_id"] and v.provider == saved_voice["provider"]),
                None
            )

            if voice_metadata:
                enriched_voice = {
                    **voice_metadata.model_dump(),
                    "nickname": saved_voice.get("nickname"),
                    "added_at": saved_voice.get("added_at")
                }
                enriched_voices.append(enriched_voice)

        return {
            "user_id": user_id,
            "saved_voices": enriched_voices,
            "total": len(enriched_voices),
            "updated_at": user_prefs.get("updated_at")
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Failed to fetch user preferences: {str(error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user preferences: {str(error)}"
        )


@router.post("/preferences/{user_id}/save")
async def save_voice_to_preferences(user_id: str, request: SaveVoiceRequest):
    """
    Save a voice to user's preferences

    Args:
    - user_id: User ID
    - request: Voice to save with optional nickname

    Returns:
    - Updated preferences
    """
    try:
        db = Database.get_db()
        preferences_collection = db['voice_preferences']

        # Validate user_id
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        # Note: We no longer strictly require voice to be in catalog
        # ElevenLabs voices can be dynamically synced from user's account
        # The voice_id will be validated when actually used with the TTS provider

        # Create voice preference object
        voice_pref = {
            "voice_id": request.voice_id,
            "provider": request.provider,
            "nickname": request.nickname,
            "added_at": datetime.utcnow()
        }

        # Update or create user preferences
        result = preferences_collection.update_one(
            {"user_id": user_id},
            {
                "$addToSet": {
                    "saved_voices": {
                        "$each": [voice_pref]
                    }
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "user_id": user_id
                }
            },
            upsert=True
        )

        # Remove duplicates (same voice_id + provider combination)
        preferences_collection.update_one(
            {"user_id": user_id},
            [
                {
                    "$set": {
                        "saved_voices": {
                            "$reduce": {
                                "input": "$saved_voices",
                                "initialValue": [],
                                "in": {
                                    "$cond": {
                                        "if": {
                                            "$in": [
                                                {"voice_id": "$$this.voice_id", "provider": "$$this.provider"},
                                                {
                                                    "$map": {
                                                        "input": "$$value",
                                                        "as": "item",
                                                        "in": {"voice_id": "$$item.voice_id", "provider": "$$item.provider"}
                                                    }
                                                }
                                            ]
                                        },
                                        "then": "$$value",
                                        "else": {"$concatArrays": ["$$value", ["$$this"]]}
                                    }
                                }
                            }
                        }
                    }
                }
            ]
        )

        return {
            "success": True,
            "message": "Voice saved to preferences",
            "voice_id": request.voice_id,
            "provider": request.provider
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Failed to save voice preference: {str(error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save voice preference: {str(error)}"
        )


@router.post("/preferences/{user_id}/remove")
async def remove_voice_from_preferences(user_id: str, request: RemoveVoiceRequest):
    """
    Remove a voice from user's preferences

    Args:
    - user_id: User ID
    - request: Voice to remove

    Returns:
    - Updated preferences
    """
    try:
        db = Database.get_db()
        preferences_collection = db['voice_preferences']

        # Validate user_id
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        # Remove voice from preferences
        result = preferences_collection.update_one(
            {"user_id": user_id},
            {
                "$pull": {
                    "saved_voices": {
                        "voice_id": request.voice_id,
                        "provider": request.provider
                    }
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                }
            }
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User preferences not found"
            )

        return {
            "success": True,
            "message": "Voice removed from preferences",
            "voice_id": request.voice_id,
            "provider": request.provider
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Failed to remove voice preference: {str(error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove voice preference: {str(error)}"
        )


async def generate_cartesia_demo(voice_id: str, model: str, text: str, api_key: str) -> bytes:
    """Generate voice demo using Cartesia API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "X-API-Key": api_key,
                    "Cartesia-Version": "2024-06-10",
                    "Content-Type": "application/json",
                },
                json={
                    "model_id": model,
                    "transcript": text,
                    "voice": {
                        "mode": "id",
                        "id": voice_id
                    },
                    "output_format": {
                        "container": "mp3",
                        "encoding": "mp3",
                        "sample_rate": 44100
                    },
                    "language": "en"
                },
                timeout=30.0
            )

            if response.status_code != 200:
                error_msg = f"Cartesia API error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg)
                except:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_msg
                )

            return response.content
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Cartesia API timeout. Please try again."
        )


async def generate_elevenlabs_demo(voice_id: str, model: str, text: str, api_key: str) -> bytes:
    """Generate voice demo using ElevenLabs API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": model,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                },
                timeout=30.0
            )

            if response.status_code != 200:
                error_msg = f"ElevenLabs API error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('detail', {}).get('message', error_msg)
                except:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_msg
                )

            return response.content
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="ElevenLabs API timeout. Please try again."
        )


async def generate_sarvam_demo(voice_id: str, model: str, text: str, api_key: str) -> bytes:
    """Generate voice demo using Sarvam AI API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={
                    "api-subscription-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": voice_id,
                    "model": model,
                    "enable_preprocessing": True
                },
                timeout=30.0
            )

            if response.status_code != 200:
                error_msg = f"Sarvam API error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', error_msg)
                except:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_msg
                )

            # Sarvam returns base64 encoded audio in audios array
            response_data = response.json()
            if 'audios' in response_data and len(response_data['audios']) > 0:
                import base64
                audio_base64 = response_data['audios'][0]
                return base64.b64decode(audio_base64)
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid response from Sarvam API"
                )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Sarvam API timeout. Please try again."
        )


async def generate_openai_demo(voice_id: str, model: str, text: str, api_key: str) -> bytes:
    """Generate voice demo using OpenAI TTS API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": text,
                    "voice": voice_id,
                    "response_format": "mp3"
                },
                timeout=30.0
            )

            if response.status_code != 200:
                error_msg = "Failed to generate voice sample"
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error_msg = error_json['error'].get('message', error_msg)
                except:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_msg
                )

            return response.content
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="OpenAI API timeout. Please try again."
        )


async def generate_piper_demo(voice_id: str, text: str) -> bytes:
    """Generate a Piper demo and return WAV bytes for browser playback."""
    piper_tts = OfflinePiperTTS(voice=voice_id, for_browser=True)
    pcm_24k = await piper_tts.synthesize(text)
    if not pcm_24k:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to synthesize Piper audio"
        )

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(pcm_24k)

    return wav_buffer.getvalue()


# Provider API key name mapping
PROVIDER_KEY_MAPPING = {
    "openai": "openai",
    "cartesia": "custom",  # Cartesia keys stored as custom
    "elevenlabs": "custom",  # ElevenLabs keys stored as custom
    "sarvam": "custom",  # Sarvam keys stored as custom
    "piper": "local"
}


@router.post("/demo", status_code=status.HTTP_200_OK)
async def generate_universal_voice_demo(request: UniversalVoiceDemoRequest):
    """
    Generate voice demo for any TTS provider

    Supports: OpenAI, Cartesia, ElevenLabs, Sarvam AI, Piper

    Args:
    - request: Voice demo request with provider, voice_id, and text

    Returns:
    - Audio file (mp3) as streaming response
    """
    try:
        logger.info(f"Generating voice demo for {request.provider}:{request.voice_id}, user: {request.user_id}")

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

        # Try to find voice in catalog for metadata (model info)
        voice_metadata = next(
            (v for v in ACTIVE_VOICE_CATALOG if v.id == request.voice_id and v.provider == request.provider),
            None
        )

        # For ElevenLabs, voices can be dynamically synced from user's account
        # So we don't require them to be in the catalog - just use the voice_id directly
        # The TTS API will return an error if the voice doesn't exist

        # Piper is local and does not require provider API keys.
        if request.provider == "piper":
            audio_content = await generate_piper_demo(request.voice_id, request.text)
            return Response(
                content=audio_content,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": f'inline; filename="voice_demo_{request.provider}_{request.voice_id}.wav"'
                }
            )

        # Determine which API key provider to look for
        provider_key_type = PROVIDER_KEY_MAPPING.get(request.provider, "custom")

        # Find user's API key for this provider
        api_key_doc = None
        decrypted_api_key = None

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
        else:
            # For OpenAI, look for openai provider key
            if request.provider == "openai":
                api_key_doc = api_keys_collection.find_one({
                    "user_id": user_obj_id,
                    "provider": "openai"
                })
            else:
                # For other providers, look for custom keys with matching label/description
                # First try to find by label containing provider name
                api_key_doc = api_keys_collection.find_one({
                    "user_id": user_obj_id,
                    "provider": "custom",
                    "$or": [
                        {"label": {"$regex": request.provider, "$options": "i"}},
                        {"description": {"$regex": request.provider, "$options": "i"}}
                    ]
                })

                # If not found, get the first custom key
                if not api_key_doc:
                    api_key_doc = api_keys_collection.find_one({
                        "user_id": user_obj_id,
                        "provider": "custom"
                    })

            # If no user API key found, try to use .env API keys as fallback
            if not api_key_doc:
                logger.info(f"No user API key found for {request.provider}, trying .env fallback")

                # Try to get API key from environment variables
                if request.provider == "sarvam":
                    decrypted_api_key = settings.sarvam_api_key
                elif request.provider == "cartesia":
                    decrypted_api_key = settings.cartesia_api_key
                elif request.provider == "elevenlabs":
                    decrypted_api_key = settings.elevenlabs_api_key
                elif request.provider == "openai":
                    decrypted_api_key = settings.openai_api_key if hasattr(settings, 'openai_api_key') else None

                if not decrypted_api_key:
                    provider_name = request.provider.capitalize()
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"No {provider_name} API key found. Please add a {provider_name} API key in Settings (as 'Custom Provider') or configure it in .env file."
                    )

                logger.info(f"Using .env API key for {request.provider}")

        # Decrypt the API key if found in database
        if api_key_doc and not decrypted_api_key:
            try:
                decrypted_api_key = encryption_service.decrypt(api_key_doc['key'])
            except Exception as e:
                logger.error(f"Failed to decrypt API key: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to decrypt API key"
                )

        # Default models per provider
        default_models = {
            "openai": "tts-1",
            "cartesia": "sonic-english",
            "elevenlabs": "eleven_turbo_v2_5",
            "sarvam": "bulbul:v2",
            "piper": "medium"
        }

        # Determine model to use (request model > voice metadata model > default)
        model_to_use = request.model or (voice_metadata.model if voice_metadata else None) or default_models.get(request.provider, "tts-1")

        # Generate voice demo based on provider
        audio_content = None

        if request.provider == "openai":
            audio_content = await generate_openai_demo(
                request.voice_id, model_to_use, request.text, decrypted_api_key
            )
        elif request.provider == "cartesia":
            audio_content = await generate_cartesia_demo(
                request.voice_id, model_to_use, request.text, decrypted_api_key
            )
        elif request.provider == "elevenlabs":
            audio_content = await generate_elevenlabs_demo(
                request.voice_id, model_to_use, request.text, decrypted_api_key
            )
        elif request.provider == "sarvam":
            audio_content = await generate_sarvam_demo(
                request.voice_id, model_to_use, request.text, decrypted_api_key
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Voice demos for {request.provider} are not yet supported."
            )

        # Return audio as response
        return Response(
            content=audio_content,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'inline; filename="voice_demo_{request.provider}_{request.voice_id}.mp3"'
            }
        )

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Failed to generate voice demo: {str(error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate voice demo: {str(error)}"
        )
