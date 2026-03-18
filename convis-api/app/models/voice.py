"""
Voice models for voice library and preferences
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime

# Voice metadata model
class VoiceMetadata(BaseModel):
    """Metadata for a single voice"""
    id: str = Field(..., description="Unique voice identifier")
    name: str = Field(..., description="Display name of the voice")
    provider: Literal["piper"] = Field(..., description="TTS provider")
    gender: Literal["male", "female", "neutral"] = Field(..., description="Voice gender")
    accent: str = Field(..., description="Voice accent/region (e.g., American, British, Indian)")
    language: str = Field(default="en", description="Primary language code")
    description: Optional[str] = Field(None, description="Detailed description of the voice")
    age_group: Optional[Literal["young", "middle-aged", "old"]] = Field(None, description="Age group of the voice")
    use_case: Optional[str] = Field(None, description="Recommended use case (e.g., Voice Agent, Emotive, Customer Support)")
    model: Optional[str] = Field(None, description="Associated TTS model")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "en_US-lessac-medium",
                "name": "Lessac",
                "provider": "piper",
                "gender": "female",
                "accent": "American",
                "language": "en",
                "description": "American female voice optimized for local offline synthesis",
                "age_group": "middle-aged",
                "use_case": "Voice Agent",
                "model": "medium"
            }
        }


class VoiceListResponse(BaseModel):
    """Response model for listing all available voices"""
    voices: List[VoiceMetadata]
    total: int
    providers: List[str]

    class Config:
        json_schema_extra = {
            "example": {
                "voices": [],
                "total": 17,
                "providers": ["piper"]
            }
        }


class VoicePreference(BaseModel):
    """User's saved voice preference"""
    voice_id: str = Field(..., description="Voice identifier")
    provider: str = Field(..., description="TTS provider")
    nickname: Optional[str] = Field(None, description="User's custom nickname for the voice")
    added_at: datetime = Field(default_factory=datetime.utcnow)


class UserVoicePreferences(BaseModel):
    """User's voice preferences stored in database"""
    user_id: str
    saved_voices: List[VoicePreference] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SaveVoiceRequest(BaseModel):
    """Request to save a voice to user's preferences"""
    voice_id: str
    provider: Literal["piper"]
    nickname: Optional[str] = None


class RemoveVoiceRequest(BaseModel):
    """Request to remove a voice from user's preferences"""
    voice_id: str
    provider: str


class UniversalVoiceDemoRequest(BaseModel):
    """Request for generating voice demo for any provider"""
    voice_id: str = Field(..., description="Voice identifier")
    provider: Literal["piper"] = Field(..., description="TTS provider")
    user_id: str = Field(..., description="User ID for API key lookup")
    text: Optional[str] = Field(
        default="This is the text you can play using this voice. Experience the natural tone and clarity.",
        description="Text to synthesize"
    )
    model: Optional[str] = Field(None, description="Specific model to use (provider-dependent)")
    api_key_id: Optional[str] = Field(None, description="Specific API key ID to use")
