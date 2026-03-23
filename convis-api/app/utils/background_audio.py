"""
Background Audio Mixer for Voice Calls

This module provides functionality to mix background ambient audio
(like call center noise) with the AI's speech output for more
natural-sounding calls.

Audio is mixed in real-time during the call at the mu-law 8kHz format
that Twilio expects.
"""

import os
import base64
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Generator
import struct

logger = logging.getLogger(__name__)

# Audio file paths - stored in static/audio directory
AUDIO_DIR = Path(__file__).parent.parent / "static" / "audio"

# Background audio types and their corresponding files
BACKGROUND_AUDIO_FILES: Dict[str, str] = {
    "call_center": "call_center_ambience.raw",
    "office": "office_ambience.raw",
    "cafe": "cafe_ambience.raw",
    "white_noise": "white_noise.raw",
    "custom": "custom_background.raw",  # User's custom background music
}

# Cache for loaded audio data
_audio_cache: Dict[str, bytes] = {}


def mu_law_encode(sample: int) -> int:
    """Encode a 16-bit PCM sample to 8-bit mu-law."""
    MULAW_MAX = 0x1FFF
    MULAW_BIAS = 33

    sign = (sample >> 8) & 0x80
    if sign:
        sample = -sample

    sample = sample + MULAW_BIAS
    if sample > MULAW_MAX:
        sample = MULAW_MAX

    # Find the segment
    segment = 0
    temp = sample
    while temp > 0x3F:
        temp >>= 1
        segment += 1

    # Combine sign, segment, and quantization
    return ~(sign | (segment << 4) | ((sample >> (segment + 1)) & 0x0F)) & 0xFF


def mu_law_decode(mulaw_byte: int) -> int:
    """Decode an 8-bit mu-law sample to 16-bit PCM."""
    MULAW_BIAS = 33

    mulaw_byte = ~mulaw_byte
    sign = mulaw_byte & 0x80
    segment = (mulaw_byte >> 4) & 0x07
    quantization = mulaw_byte & 0x0F

    sample = ((quantization << 1) + MULAW_BIAS) << segment
    sample -= MULAW_BIAS

    if sign:
        sample = -sample

    return sample


def load_background_audio(audio_type: str) -> Optional[bytes]:
    """
    Load background audio file into memory.

    Args:
        audio_type: Type of background audio (call_center, office, cafe, white_noise)

    Returns:
        Raw audio bytes (mu-law 8kHz) or None if not found
    """
    global _audio_cache

    if audio_type in _audio_cache:
        return _audio_cache[audio_type]

    filename = BACKGROUND_AUDIO_FILES.get(audio_type)
    if not filename:
        logger.warning(f"Unknown background audio type: {audio_type}")
        return None

    audio_path = AUDIO_DIR / filename

    if not audio_path.exists():
        logger.warning(f"Background audio file not found: {audio_path}")
        return None

    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        _audio_cache[audio_type] = audio_data
        logger.info(f"Loaded background audio: {audio_type} ({len(audio_data)} bytes)")
        return audio_data
    except Exception as e:
        logger.error(f"Error loading background audio {audio_type}: {e}")
        return None


class BackgroundAudioMixer:
    """
    Mixes background audio with speech audio in real-time.

    The mixer loops through the background audio continuously
    and mixes it with the speech audio at the specified volume.
    """

    def __init__(
        self,
        audio_type: str = "custom",
        volume: float = 0.25,  # 25% volume for background, AI voice stays louder
        enabled: bool = True
    ):
        """
        Initialize the background audio mixer.

        Args:
            audio_type: Type of background audio
            volume: Volume level for background audio (0.0-1.0)
            enabled: Whether background audio is enabled
        """
        self.audio_type = audio_type
        self.volume = max(0.0, min(1.0, volume))  # Clamp to 0-1
        self.enabled = enabled
        self.background_audio: Optional[bytes] = None
        self.position = 0

        if self.enabled:
            self.background_audio = load_background_audio(audio_type)
            if self.background_audio:
                logger.info(f"BackgroundAudioMixer initialized: type={audio_type}, volume={volume}")
            else:
                logger.warning(f"BackgroundAudioMixer: Could not load audio, disabling")
                self.enabled = False

    def mix_audio(self, speech_audio: bytes) -> bytes:
        """
        Mix background audio with speech audio.

        Args:
            speech_audio: Speech audio bytes (mu-law 8kHz)

        Returns:
            Mixed audio bytes (mu-law 8kHz)
        """
        if not self.enabled or not self.background_audio:
            return speech_audio

        if not speech_audio:
            return speech_audio

        mixed = bytearray(len(speech_audio))
        bg_len = len(self.background_audio)

        for i in range(len(speech_audio)):
            # Decode both samples to PCM
            speech_pcm = mu_law_decode(speech_audio[i])
            bg_pcm = mu_law_decode(self.background_audio[self.position])

            # Mix: speech at full volume, background at specified volume
            mixed_pcm = int(speech_pcm + (bg_pcm * self.volume))

            # Clamp to 16-bit range
            mixed_pcm = max(-32768, min(32767, mixed_pcm))

            # Encode back to mu-law
            mixed[i] = mu_law_encode(mixed_pcm)

            # Advance background audio position (loop)
            self.position = (self.position + 1) % bg_len

        return bytes(mixed)

    def mix_audio_base64(self, speech_audio_b64: str) -> str:
        """
        Mix background audio with base64-encoded speech audio.

        Args:
            speech_audio_b64: Base64-encoded speech audio (mu-law 8kHz)

        Returns:
            Base64-encoded mixed audio
        """
        if not self.enabled or not self.background_audio:
            return speech_audio_b64

        try:
            speech_audio = base64.b64decode(speech_audio_b64)
            mixed_audio = self.mix_audio(speech_audio)
            return base64.b64encode(mixed_audio).decode('utf-8')
        except Exception as e:
            logger.error(f"Error mixing audio: {e}")
            return speech_audio_b64

    def get_background_chunk(self, length: int) -> bytes:
        """
        Get a chunk of background audio (for silence periods).

        Args:
            length: Number of bytes to get

        Returns:
            Background audio bytes (mu-law 8kHz)
        """
        if not self.enabled or not self.background_audio:
            # Return silence
            return bytes([0xFF] * length)  # 0xFF is silence in mu-law

        chunk = bytearray(length)
        bg_len = len(self.background_audio)

        for i in range(length):
            # Get background sample and apply volume
            bg_pcm = mu_law_decode(self.background_audio[self.position])
            adjusted_pcm = int(bg_pcm * self.volume)
            adjusted_pcm = max(-32768, min(32767, adjusted_pcm))
            chunk[i] = mu_law_encode(adjusted_pcm)

            self.position = (self.position + 1) % bg_len

        return bytes(chunk)

    def get_background_chunk_base64(self, length: int) -> str:
        """
        Get a base64-encoded chunk of background audio.

        Args:
            length: Number of bytes to get

        Returns:
            Base64-encoded background audio
        """
        chunk = self.get_background_chunk(length)
        return base64.b64encode(chunk).decode('utf-8')

    def reset(self):
        """Reset the mixer position to the beginning."""
        self.position = 0


def create_mixer_from_assistant(assistant: dict) -> BackgroundAudioMixer:
    """
    Create a BackgroundAudioMixer from assistant configuration.

    Args:
        assistant: Assistant configuration dict

    Returns:
        Configured BackgroundAudioMixer instance
    """
    enabled = assistant.get('background_audio_enabled', False)
    audio_type = assistant.get('background_audio_type', 'custom')  # Default to custom music
    volume = assistant.get('background_audio_volume', 0.25)  # 25% volume default

    return BackgroundAudioMixer(
        audio_type=audio_type,
        volume=volume,
        enabled=enabled
    )


# Utility function to generate background audio files
def generate_sample_audio_files():
    """
    Generate sample background audio files for testing.
    Creates simple synthetic audio patterns.

    Run this once to create the audio files:
    python -c "from app.utils.background_audio import generate_sample_audio_files; generate_sample_audio_files()"
    """
    import random
    import math

    os.makedirs(AUDIO_DIR, exist_ok=True)

    # Generate 30 seconds of audio at 8kHz
    duration_seconds = 30
    sample_rate = 8000
    num_samples = duration_seconds * sample_rate

    def generate_noise_audio(noise_level: float = 0.1) -> bytes:
        """Generate white/pink noise."""
        audio = bytearray(num_samples)
        for i in range(num_samples):
            # Random noise
            noise = random.gauss(0, noise_level * 32767)
            noise = int(max(-32768, min(32767, noise)))
            audio[i] = mu_law_encode(noise)
        return bytes(audio)

    def generate_ambient_audio(base_noise: float = 0.05, variation: float = 0.02) -> bytes:
        """Generate ambient background audio with subtle variations."""
        audio = bytearray(num_samples)
        phase = 0
        for i in range(num_samples):
            # Low frequency hum + noise
            hum = math.sin(phase) * 0.02 * 32767
            phase += 2 * math.pi * 60 / sample_rate  # 60Hz hum

            # Random ambient noise
            noise = random.gauss(0, (base_noise + random.random() * variation) * 32767)

            sample = int(hum + noise)
            sample = max(-32768, min(32767, sample))
            audio[i] = mu_law_encode(sample)
        return bytes(audio)

    # Generate different audio types
    audio_configs = {
        "call_center_ambience.raw": {"base_noise": 0.08, "variation": 0.03},
        "office_ambience.raw": {"base_noise": 0.04, "variation": 0.02},
        "cafe_ambience.raw": {"base_noise": 0.06, "variation": 0.04},
        "white_noise.raw": {"base_noise": 0.05, "variation": 0.01},
    }

    for filename, config in audio_configs.items():
        filepath = AUDIO_DIR / filename
        audio_data = generate_ambient_audio(**config)
        with open(filepath, "wb") as f:
            f.write(audio_data)
        logger.info(f"Generated {filename}: {len(audio_data)} bytes")
        print(f"Generated {filepath}")

    print(f"\nAudio files created in: {AUDIO_DIR}")
