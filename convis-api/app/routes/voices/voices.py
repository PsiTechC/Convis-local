"""
Voice library and preferences API routes
"""
import asyncio
import httpx
import os
from fastapi import APIRouter, HTTPException, status, Response
from typing import Optional, List
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

router = APIRouter()
logger = logging.getLogger(__name__)

# Comprehensive voice catalog with all metadata
VOICE_CATALOG: List[VoiceMetadata] = [
    # Cartesia Voices
    VoiceMetadata(
        id="f786b574-daa5-4673-aa0c-cbe3e8534c02",
        name="Katie",
        provider="cartesia",
        gender="female",
        accent="American",
        language="en",
        description="American Female voice optimized for voice agents - stable and realistic",
        age_group="young",
        use_case="Voice Agent",
        model="sonic-english"
    ),
    VoiceMetadata(
        id="228fca29-3a0a-435c-8728-5cb483251068",
        name="Kiefer",
        provider="cartesia",
        gender="male",
        accent="American",
        language="en",
        description="American Male voice optimized for voice agents - stable and realistic",
        age_group="young",
        use_case="Voice Agent",
        model="sonic-english"
    ),
    VoiceMetadata(
        id="6ccbfb76-1fc6-48f7-b71d-91ac6298247b",
        name="Tessa",
        provider="cartesia",
        gender="female",
        accent="American",
        language="en",
        description="American Female voice with emotive characteristics for expressive conversations",
        age_group="young",
        use_case="Emotive Character",
        model="sonic-english"
    ),
    VoiceMetadata(
        id="c961b81c-a935-4c17-bfb3-ba2239de8c2f",
        name="Kyle",
        provider="cartesia",
        gender="male",
        accent="American",
        language="en",
        description="American Male voice with emotive characteristics for expressive conversations",
        age_group="young",
        use_case="Emotive Character",
        model="sonic-english"
    ),
    VoiceMetadata(
        id="a0e99841-438c-4a64-b679-ae501e7d6091",
        name="Default Voice (Recommended)",
        provider="cartesia",
        gender="neutral",
        accent="American",
        language="en",
        description="Cartesia's recommended default voice for general use",
        age_group="middle-aged",
        use_case="General Purpose",
        model="sonic-english"
    ),
    VoiceMetadata(
        id="f9836c6e-a0bd-460e-9d3c-f7299fa60f94",
        name="Alternative Voice 1",
        provider="cartesia",
        gender="neutral",
        accent="American",
        language="en",
        description="Alternative neutral voice option",
        age_group="middle-aged",
        use_case="General Purpose",
        model="sonic-english"
    ),
    VoiceMetadata(
        id="a167e0f3-df7e-4d52-a9c3-f949145efdab",
        name="Customer Support Man",
        provider="cartesia",
        gender="male",
        accent="American",
        language="en",
        description="Professional male voice optimized for customer support",
        age_group="middle-aged",
        use_case="Customer Support",
        model="sonic-english"
    ),

    # ElevenLabs Voices - Female American
    VoiceMetadata(
        id="EXAVITQu4vr4xnSDxMaL",
        name="Sarah",
        provider="elevenlabs",
        gender="female",
        accent="American",
        language="en",
        description="Young American female voice with clear, friendly tone",
        age_group="young",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="FGY2WhTYpPnrIDTdsKH5",
        name="Laura",
        provider="elevenlabs",
        gender="female",
        accent="American",
        language="en",
        description="Young American female voice, warm and professional",
        age_group="young",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="cgSgspJ2msm6clMCkdW9",
        name="Jessica",
        provider="elevenlabs",
        gender="female",
        accent="American",
        language="en",
        description="Young American female voice with energetic delivery",
        age_group="young",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="XrExE9yKIg1WjnnlVkGX",
        name="Matilda",
        provider="elevenlabs",
        gender="female",
        accent="American",
        language="en",
        description="Middle-aged American female voice with authoritative tone",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="pFZP5JQG7iQjIQuC4Bku",
        name="Lily",
        provider="elevenlabs",
        gender="female",
        accent="American",
        language="en",
        description="Middle-aged female voice with sophisticated tone",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),

    # ElevenLabs - Female British
    VoiceMetadata(
        id="Xb7hH8MSUJpSbSDYk0k2",
        name="Alice",
        provider="elevenlabs",
        gender="female",
        accent="British",
        language="en",
        description="Middle-aged British female voice with refined accent",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="FrzKLwOr0y3qieiphjs2",
        name="Paula",
        provider="elevenlabs",
        gender="female",
        accent="British",
        language="en",
        description="Warm, sophisticated female voice with refined English accent - perfect for luxury branding and corporate narration",
        age_group="young",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),

    # ElevenLabs - Male American
    VoiceMetadata(
        id="2EiwWnXFnvU5JabPnv8n",
        name="Clyde",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Middle-aged American male voice with strong, confident tone",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="CwhRBWXzGAHq8TQ4Fs17",
        name="Roger",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Middle-aged American male voice with calm, reassuring tone",
        age_group="middle-aged",
        use_case="Customer Support",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="TX3LPaxmHKxFdv7VOQHJ",
        name="Liam",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Young American male voice with dynamic, engaging delivery",
        age_group="young",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="SOYHLrjzK2X1ezoPC6cr",
        name="Harry",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Young American male voice with friendly, approachable tone",
        age_group="young",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="bIHbv24MWmeRgasZH58o",
        name="Will",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Young American male voice with clear, professional delivery",
        age_group="young",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="cjVigY5qzO86Huf0OWal",
        name="Eric",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Middle-aged American male voice with authoritative presence",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="iP95p4xoKVk53GoZ742B",
        name="Chris",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Middle-aged American male voice with versatile tone",
        age_group="middle-aged",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="nPczCjzI2devNBz1zQrb",
        name="Brian",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Middle-aged American male voice with warm, trustworthy tone",
        age_group="middle-aged",
        use_case="Customer Support",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="pqHfZKP75CvOlQylNhV4",
        name="Bill",
        provider="elevenlabs",
        gender="male",
        accent="American",
        language="en",
        description="Older American male voice with experienced, wise tone",
        age_group="old",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),

    # ElevenLabs - Male British
    VoiceMetadata(
        id="JBFqnCBsd6RMkjVDRZzb",
        name="George",
        provider="elevenlabs",
        gender="male",
        accent="British",
        language="en",
        description="Middle-aged British male voice with distinguished accent",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="onwK4e9ZLuTAKqWW03F9",
        name="Daniel",
        provider="elevenlabs",
        gender="male",
        accent="British",
        language="en",
        description="Middle-aged British male voice with clear, articulate delivery",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),
    VoiceMetadata(
        id="N2lVS1w4EtoT3dr4eOWO",
        name="Callum",
        provider="elevenlabs",
        gender="male",
        accent="British",
        language="en",
        description="Middle-aged male voice with refined British accent",
        age_group="middle-aged",
        use_case="Professional",
        model="eleven_turbo_v2_5"
    ),

    # ElevenLabs - Male Australian
    VoiceMetadata(
        id="IKne3meq5aSn9XLyUdCD",
        name="Charlie",
        provider="elevenlabs",
        gender="male",
        accent="Australian",
        language="en",
        description="Young Australian male voice with friendly, casual tone",
        age_group="young",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),

    # ElevenLabs - Neutral
    VoiceMetadata(
        id="SAz9YHcvj6GT2YYXdXww",
        name="River",
        provider="elevenlabs",
        gender="neutral",
        accent="American",
        language="en",
        description="Middle-aged American neutral voice with balanced, versatile tone",
        age_group="middle-aged",
        use_case="General Purpose",
        model="eleven_turbo_v2_5"
    ),

    # ElevenLabs - Indian Hindi Voices
    VoiceMetadata(
        id="broqrJkktxd1CclKTudW",
        name="Anika",
        provider="elevenlabs",
        gender="female",
        accent="Indian",
        language="hi",
        description="Hindi Customer Care Agent - Professional young female voice for conversational support",
        age_group="young",
        use_case="Customer Support",
        model="eleven_turbo_v2"
    ),
    VoiceMetadata(
        id="ni6cdqyS9wBvic5LPA7M",
        name="Tara",
        provider="elevenlabs",
        gender="female",
        accent="Indian",
        language="hi",
        description="Expressive Conversational Hindi Voice - Casual young female with natural delivery",
        age_group="young",
        use_case="Conversational",
        model="eleven_turbo_v2"
    ),
    VoiceMetadata(
        id="SZfY4K69FwXus87eayHK",
        name="Nikita",
        provider="elevenlabs",
        gender="female",
        accent="Indian",
        language="hi",
        description="Youthful Hindi Voice - Excited, energetic young female for engaging conversations",
        age_group="young",
        use_case="Conversational",
        model="eleven_turbo_v2"
    ),
    VoiceMetadata(
        id="1qEiC6qsybMkmnNdVMbK",
        name="Monika",
        provider="elevenlabs",
        gender="female",
        accent="Indian",
        language="hi",
        description="Hindi Modulated Voice - Professional middle-aged female for narrative and storytelling",
        age_group="middle-aged",
        use_case="Narrative",
        model="eleven_turbo_v2"
    ),
    VoiceMetadata(
        id="KSsyodh37PbfWy29kPtx",
        name="Kishan",
        provider="elevenlabs",
        gender="male",
        accent="Indian",
        language="hi",
        description="Clear & Confident Hindi Narrator - Pleasant young male for audiobooks and e-learning",
        age_group="young",
        use_case="Narrative",
        model="eleven_turbo_v2"
    ),
    VoiceMetadata(
        id="6MoEUz34rbRrmmyxgRm4",
        name="Manav",
        provider="elevenlabs",
        gender="male",
        accent="Indian",
        language="hi",
        description="Charming, Husky Indian Male Voice - Modulated young male for conversational use",
        age_group="young",
        use_case="Conversational",
        model="eleven_turbo_v2"
    ),

    # OpenAI Voices
    VoiceMetadata(
        id="alloy",
        name="Alloy",
        provider="openai",
        gender="neutral",
        accent="American",
        language="en",
        description="Neutral, balanced voice suitable for all purposes",
        age_group="middle-aged",
        use_case="General Purpose",
        model="tts-1"
    ),
    VoiceMetadata(
        id="echo",
        name="Echo",
        provider="openai",
        gender="male",
        accent="American",
        language="en",
        description="Male voice with clear, strong delivery",
        age_group="middle-aged",
        use_case="General Purpose",
        model="tts-1"
    ),
    VoiceMetadata(
        id="fable",
        name="Fable",
        provider="openai",
        gender="male",
        accent="British",
        language="en",
        description="British male voice with narrative quality",
        age_group="middle-aged",
        use_case="Storytelling",
        model="tts-1"
    ),
    VoiceMetadata(
        id="onyx",
        name="Onyx",
        provider="openai",
        gender="male",
        accent="American",
        language="en",
        description="Deep male voice with authoritative presence",
        age_group="middle-aged",
        use_case="Professional",
        model="tts-1"
    ),
    VoiceMetadata(
        id="nova",
        name="Nova",
        provider="openai",
        gender="female",
        accent="American",
        language="en",
        description="Female voice with warm, friendly tone",
        age_group="young",
        use_case="General Purpose",
        model="tts-1"
    ),
    VoiceMetadata(
        id="shimmer",
        name="Shimmer",
        provider="openai",
        gender="female",
        accent="American",
        language="en",
        description="Soft female voice with gentle, soothing quality",
        age_group="young",
        use_case="Customer Support",
        model="tts-1"
    ),

    # Sarvam AI Voices - Female (Only valid voices supported by Sarvam API)
    VoiceMetadata(
        id="anushka",
        name="Anushka",
        provider="sarvam",
        gender="female",
        accent="Indian",
        language="hi",
        description="Female Hindi voice with warm tone (default voice)",
        age_group="young",
        use_case="General Purpose",
        model="bulbul:v2"
    ),
    VoiceMetadata(
        id="manisha",
        name="Manisha",
        provider="sarvam",
        gender="female",
        accent="Indian",
        language="hi",
        description="Female voice for Hindi/English, clear and professional",
        age_group="young",
        use_case="Bilingual Support",
        model="bulbul:v2"
    ),
    VoiceMetadata(
        id="vidya",
        name="Vidya",
        provider="sarvam",
        gender="female",
        accent="Indian",
        language="hi",
        description="Female Hindi voice with professional delivery",
        age_group="middle-aged",
        use_case="Professional",
        model="bulbul:v2"
    ),
    VoiceMetadata(
        id="arya",
        name="Arya",
        provider="sarvam",
        gender="female",
        accent="Indian",
        language="hi",
        description="Female Hindi voice with friendly tone",
        age_group="young",
        use_case="General Purpose",
        model="bulbul:v2"
    ),

    # Sarvam AI Voices - Male (Only valid voices supported by Sarvam API)
    VoiceMetadata(
        id="abhilash",
        name="Abhilash",
        provider="sarvam",
        gender="male",
        accent="Indian",
        language="hi",
        description="Male Hindi voice with professional delivery",
        age_group="young",
        use_case="Professional",
        model="bulbul:v2"
    ),
    VoiceMetadata(
        id="karun",
        name="Karun",
        provider="sarvam",
        gender="male",
        accent="Indian",
        language="hi",
        description="Male Hindi voice with confident tone",
        age_group="young",
        use_case="General Purpose",
        model="bulbul:v2"
    ),
    VoiceMetadata(
        id="hitesh",
        name="Hitesh",
        provider="sarvam",
        gender="male",
        accent="Indian",
        language="hi",
        description="Male voice for Hindi/English, clear and authoritative",
        age_group="young",
        use_case="Bilingual Support",
        model="bulbul:v2"
    ),
    # Piper Voices (Local/Offline - Free)
    VoiceMetadata(
        id="en_US-lessac-medium",
        name="Lessac",
        provider="piper",
        gender="female",
        accent="American",
        language="en",
        description="American Female voice - clear and natural, optimized for conversations",
        age_group="middle-aged",
        use_case="General Purpose",
        model="medium"
    ),
    VoiceMetadata(
        id="en_US-lessac-high",
        name="Lessac HQ",
        provider="piper",
        gender="female",
        accent="American",
        language="en",
        description="American Female voice - high quality, best for important calls",
        age_group="middle-aged",
        use_case="General Purpose",
        model="high"
    ),
    VoiceMetadata(
        id="en_US-amy-medium",
        name="Amy",
        provider="piper",
        gender="female",
        accent="American",
        language="en",
        description="American Female voice - warm and friendly tone",
        age_group="young",
        use_case="Customer Support",
        model="medium"
    ),
    VoiceMetadata(
        id="en_US-ryan-medium",
        name="Ryan",
        provider="piper",
        gender="male",
        accent="American",
        language="en",
        description="American Male voice - professional and clear",
        age_group="middle-aged",
        use_case="General Purpose",
        model="medium"
    ),
    VoiceMetadata(
        id="en_GB-alba-medium",
        name="Alba",
        provider="piper",
        gender="female",
        accent="British",
        language="en",
        description="British Female voice - elegant and professional",
        age_group="middle-aged",
        use_case="General Purpose",
        model="medium"
    ),
    VoiceMetadata(
        id="en_US-libritts_r-medium",
        name="LibriTTS",
        provider="piper",
        gender="neutral",
        accent="American",
        language="en",
        description="American neutral voice - balanced and clear",
        age_group="middle-aged",
        use_case="General Purpose",
        model="medium"
    ),
    # XTTS Voices (Local/Offline - Natural)
    VoiceMetadata(
        id="Gracie Wise",
        name="Gracie Wise",
        provider="xtts",
        gender="female",
        accent="American",
        language="en",
        description="Natural American female voice for premium local voice agents",
        age_group="middle-aged",
        use_case="Voice Agent",
        model="default"
    ),
    VoiceMetadata(
        id="Tammie Ema",
        name="Tammie Ema",
        provider="xtts",
        gender="female",
        accent="American",
        language="en",
        description="Friendly American female voice with a conversational tone",
        age_group="young",
        use_case="General Purpose",
        model="default"
    ),
    VoiceMetadata(
        id="Luis Moray",
        name="Luis Moray",
        provider="xtts",
        gender="male",
        accent="American",
        language="en",
        description="Warm American male voice for trustworthy customer interactions",
        age_group="middle-aged",
        use_case="Customer Support",
        model="default"
    ),
    VoiceMetadata(
        id="Damjan Chapman",
        name="Damjan Chapman",
        provider="xtts",
        gender="male",
        accent="American",
        language="en",
        description="Balanced American male voice for natural conversations",
        age_group="middle-aged",
        use_case="General Purpose",
        model="default"
    ),
    VoiceMetadata(
        id="Craig Gutsy",
        name="Craig Gutsy",
        provider="xtts",
        gender="male",
        accent="American",
        language="en",
        description="Professional American male voice with strong clarity",
        age_group="middle-aged",
        use_case="Professional",
        model="default"
    ),
    VoiceMetadata(
        id="Brenda Stern",
        name="Brenda Stern",
        provider="xtts",
        gender="female",
        accent="American",
        language="en",
        description="Confident American female voice suited for support and sales",
        age_group="middle-aged",
        use_case="Customer Support",
        model="default"
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
    Get all available voices from all TTS providers with optional filtering

    Query Parameters:
    - provider: Filter by TTS provider (cartesia, elevenlabs, openai, sarvam)
    - gender: Filter by gender (male, female, neutral)
    - accent: Filter by accent (American, British, Indian, Australian)
    - language: Filter by language code (en, hi, etc.)
    - user_id: User ID (required if include_custom=True)
    - include_custom: If True, also fetch custom voices from ElevenLabs account

    Returns:
    - List of all available voices with complete metadata
    """
    try:
        filtered_voices = VOICE_CATALOG.copy()

        # If user wants to include custom ElevenLabs voices
        if include_custom and user_id and (provider is None or provider.lower() == "elevenlabs"):
            try:
                db = Database.get_db()
                api_keys_collection = db['api_keys']
                user_obj_id = ObjectId(user_id)

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
                (v for v in VOICE_CATALOG if v.id == saved_voice["voice_id"] and v.provider == saved_voice["provider"]),
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
        import io
        import wave

        from app.services.call_handlers.streaming_tts_handler import StreamingSarvamTTS

        sarvam = StreamingSarvamTTS(
            api_key=api_key,
            voice=voice_id,
            model=model,
            language="hi-IN",
            for_browser=True
        )
        pcm_audio = await sarvam.synthesize(text)

        if not pcm_audio:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid response from Sarvam API"
            )

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_audio)

        return wav_buffer.getvalue()
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
    """Generate voice demo using local Piper TTS"""
    try:
        import io
        import wave
        from app.services.call_handlers.offline_tts_handler import OfflinePiperTTS

        piper = OfflinePiperTTS(voice=voice_id, for_browser=True)
        pcm_audio = await piper.synthesize(text)

        if not pcm_audio:
            raise Exception("Piper returned empty audio")

        # Convert PCM to WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_audio)

        return wav_buffer.getvalue()
    except Exception as e:
        logger.error(f"Piper demo generation error: {e}")
        raise


def _get_env_provider_key(provider: str) -> Optional[str]:
    """Resolve provider API keys from loaded settings or current environment."""
    provider = provider.lower()
    key_from_settings = None

    if provider == "sarvam":
        key_from_settings = settings.sarvam_api_key
    elif provider == "cartesia":
        key_from_settings = settings.cartesia_api_key
    elif provider == "elevenlabs":
        key_from_settings = settings.elevenlabs_api_key
    elif provider == "openai":
        key_from_settings = settings.openai_api_key if hasattr(settings, "openai_api_key") else None

    if key_from_settings and str(key_from_settings).strip():
        return str(key_from_settings).strip()

    env_var_name = {
        "sarvam": "SARVAM_API_KEY",
        "cartesia": "CARTESIA_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(provider)

    if not env_var_name:
        return None

    env_value = os.getenv(env_var_name)
    return env_value.strip() if env_value and env_value.strip() else None


async def generate_xtts_demo(voice_id: str, text: str) -> bytes:
    """Generate voice demo using local XTTS."""
    try:
        import io
        import wave

        from app.services.call_handlers.offline_tts_handler import XttsTTSHandler

        xtts = XttsTTSHandler(voice=voice_id, for_browser=True)
        pcm_audio = await xtts.synthesize(text)

        if not pcm_audio:
            raise Exception("XTTS returned empty audio")

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_audio)

        return wav_buffer.getvalue()
    except Exception as e:
        logger.error(f"XTTS demo generation error: {e}")
        raise


# Provider API key name mapping
PROVIDER_KEY_MAPPING = {
    "openai": "openai",
    "cartesia": "custom",  # Cartesia keys stored as custom
    "elevenlabs": "custom",  # ElevenLabs keys stored as custom
    "sarvam": "custom",  # Sarvam keys stored as custom
    "piper": "local",  # Piper is local, no key needed
    "xtts": "local"  # XTTS is local, no key needed
}


@router.post("/demo", status_code=status.HTTP_200_OK)
async def generate_universal_voice_demo(request: UniversalVoiceDemoRequest):
    """
    Generate voice demo for any TTS provider

    Supports: OpenAI, Cartesia, ElevenLabs, Sarvam AI

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
            (v for v in VOICE_CATALOG if v.id == request.voice_id and v.provider == request.provider),
            None
        )

        # For ElevenLabs, voices can be dynamically synced from user's account
        # So we don't require them to be in the catalog - just use the voice_id directly
        # The TTS API will return an error if the voice doesn't exist

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

                # Piper is local - no API key needed
                if request.provider in {"piper", "xtts"}:
                    decrypted_api_key = ""
                    logger.info("%s is a local provider, no API key needed", request.provider.upper())
                # Try to get API key from environment variables
                elif request.provider in {"sarvam", "cartesia", "elevenlabs", "openai"}:
                    decrypted_api_key = _get_env_provider_key(request.provider)

                if decrypted_api_key is None:
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

        if request.provider in {"sarvam", "cartesia", "elevenlabs", "openai"} and not (decrypted_api_key and decrypted_api_key.strip()):
            decrypted_api_key = _get_env_provider_key(request.provider)

        if request.provider in {"sarvam", "cartesia", "elevenlabs", "openai"} and not decrypted_api_key:
            provider_name = request.provider.capitalize()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {provider_name} API key found. Please add a {provider_name} API key in Settings (as 'Custom Provider') or configure it in .env file."
            )

        # Default models per provider
        default_models = {
            "openai": "tts-1",
            "cartesia": "sonic-english",
            "elevenlabs": "eleven_turbo_v2_5",
            "sarvam": "bulbul:v2",
            "xtts": "default"
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
        elif request.provider == "piper":
            audio_content = await generate_piper_demo(
                request.voice_id, request.text
            )
        elif request.provider == "xtts":
            audio_content = await generate_xtts_demo(
                request.voice_id, request.text
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Voice demos for {request.provider} are not yet supported."
            )

        # Return audio as response
        media_type = "audio/wav" if request.provider in {"piper", "xtts", "sarvam"} else "audio/mpeg"
        file_ext = "wav" if request.provider in {"piper", "xtts", "sarvam"} else "mp3"
        return Response(
            content=audio_content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="voice_demo_{request.provider}_{request.voice_id}.{file_ext}"'
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
