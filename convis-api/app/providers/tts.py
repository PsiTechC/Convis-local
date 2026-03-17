"""
TTS (Text-to-Speech) Provider Abstraction
"""

import logging
import asyncio
import io
import inspect
from abc import ABC, abstractmethod
from typing import Optional, Dict
import os
import base64
import threading
import wave
import aiohttp

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    """Base class for all TTS providers"""

    def __init__(self, api_key: str, voice: str = "default"):
        self.api_key = api_key
        self.voice = voice
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Convert text to speech

        Args:
            text: Text to convert to speech

        Returns:
            Audio bytes (PCM format)
        """
        pass

    @abstractmethod
    async def synthesize_stream(self, text: str) -> bytes:
        """
        Convert text to speech with streaming (for lower latency)

        Args:
            text: Text to convert to speech

        Returns:
            Audio bytes (PCM format)
        """
        pass

    @abstractmethod
    def get_latency_ms(self) -> int:
        """Get average latency in milliseconds"""
        pass

    @abstractmethod
    def get_cost_per_minute(self) -> float:
        """Get cost per minute of audio in USD"""
        pass

    @abstractmethod
    def get_available_voices(self) -> Dict[str, str]:
        """Get list of available voices"""
        pass


class CartesiaTTS(TTSProvider):
    """
    Cartesia Sonic TTS Provider

    Latency: 80-120ms (FASTEST)
    Cost: $0.005/min
    Best for: Ultra-low latency conversations
    """

    def __init__(self, api_key: Optional[str] = None, voice: str = "sonic"):
        super().__init__(
            api_key=api_key or os.getenv("CARTESIA_API_KEY"),
            voice=voice
        )
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Cartesia client"""
        try:
            from cartesia import Cartesia
            self.client = Cartesia(api_key=self.api_key)
            self.logger.info(f"Cartesia TTS initialized with voice: {self.voice}")
        except ImportError:
            self.logger.error("cartesia package not installed. Run: pip install cartesia")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Cartesia: {e}")
            raise

    async def synthesize(self, text: str) -> bytes:
        """Synthesize speech using Cartesia"""
        try:
            # Use Sonic English voice ID
            voice_id = "a0e99841-438c-4a64-b679-ae501e7d6091"  # Sonic (default fast voice)

            # Generate audio using bytes endpoint
            audio_chunks = []
            for chunk in self.client.tts.bytes(
                model_id="sonic-english",
                transcript=text,
                voice={
                    "mode": "id",
                    "id": voice_id
                },
                output_format={
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": 8000  # Match telephony sample rate
                }
            ):
                audio_chunks.append(chunk)

            return b''.join(audio_chunks)

        except Exception as e:
            self.logger.error(f"Cartesia synthesis error: {e}")
            raise

    async def synthesize_stream(self, text: str) -> bytes:
        """Cartesia streaming - just use bytes method (it's already fast)"""
        # The bytes method is already very fast, no need for separate streaming
        return await self.synthesize(text)

    def get_latency_ms(self) -> int:
        """Average latency: 80-120ms"""
        return 100

    def get_cost_per_minute(self) -> float:
        """Cost: $0.005/min"""
        return 0.005

    def get_available_voices(self) -> Dict[str, str]:
        """Available Cartesia voices"""
        return {
            "sonic": "Fast, natural voice",
            "stella": "Warm, friendly female voice",
            "marcus": "Professional male voice"
        }


class ElevenLabsTTS(TTSProvider):
    """
    ElevenLabs TTS Provider

    Latency: 100-200ms
    Cost: $0.018/min (Turbo) or $0.06/min (Standard)
    Best for: High-quality, natural voices
    """

    # Voice settings for natural, calm conversation (not over-excited)
    # Higher stability = more consistent, calm tone
    # Lower style = less dramatic/expressive
    # similarity_boost = how close to original voice
    NATURAL_VOICE_SETTINGS = {
        "stability": 0.71,           # Higher = calmer, more consistent (was 0.5)
        "similarity_boost": 0.75,    # Voice matching
        "style": 0.0,                # 0 = neutral, no exaggeration
        "use_speaker_boost": True    # Better audio quality
    }

    def __init__(self, api_key: Optional[str] = None, voice: str = "rachel"):
        super().__init__(
            api_key=api_key or os.getenv("ELEVENLABS_API_KEY"),
            voice=voice
        )
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize ElevenLabs client"""
        try:
            from elevenlabs import ElevenLabs
            self.client = ElevenLabs(api_key=self.api_key)
            self.logger.info(f"ElevenLabs TTS initialized with voice: {self.voice}")
            self.logger.info(f"ElevenLabs voice settings: stability={self.NATURAL_VOICE_SETTINGS['stability']}, style={self.NATURAL_VOICE_SETTINGS['style']}")
        except ImportError:
            self.logger.error("elevenlabs package not installed. Run: pip install elevenlabs")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize ElevenLabs: {e}")
            raise

    async def synthesize(self, text: str) -> bytes:
        """Synthesize speech using ElevenLabs with natural conversation settings"""
        try:
            # OPTIMIZED: Use Turbo v2.5 (fastest model - 32ms latency!)
            # with voice settings tuned for natural, calm conversation
            audio = self.client.generate(
                text=text,
                voice=self.voice,
                model="eleven_turbo_v2_5",  # Fastest model! (was eleven_turbo_v2)
                output_format="pcm_16000",
                voice_settings=self.NATURAL_VOICE_SETTINGS
            )

            # Collect all audio bytes
            audio_bytes = b"".join(audio)
            return audio_bytes

        except Exception as e:
            self.logger.error(f"ElevenLabs synthesis error: {e}")
            raise

    async def synthesize_stream(self, text: str) -> bytes:
        """ElevenLabs streaming for lower latency - with natural conversation settings"""
        try:
            audio_chunks = []

            # OPTIMIZED: Use streaming API with fastest model and natural voice settings
            for chunk in self.client.generate(
                text=text,
                voice=self.voice,
                model="eleven_turbo_v2_5",  # Fastest model!
                output_format="pcm_16000",
                stream=True,
                voice_settings=self.NATURAL_VOICE_SETTINGS  # Apply natural settings to streaming too
            ):
                audio_chunks.append(chunk)

            return b''.join(audio_chunks)

        except Exception as e:
            self.logger.error(f"ElevenLabs streaming error: {e}")
            return await self.synthesize(text)

    def get_latency_ms(self) -> int:
        """Average latency: 100-200ms"""
        return 150

    def get_cost_per_minute(self) -> float:
        """Cost: $0.018/min (Turbo model)"""
        return 0.018

    def get_available_voices(self) -> Dict[str, str]:
        """Available ElevenLabs voices"""
        return {
            "rachel": "Young female American voice",
            "domi": "Strong female American voice",
            "bella": "Soft young American female",
            "antoni": "Well-rounded male voice",
            "josh": "Deep American male voice",
            "arnold": "Crisp American male"
        }


class OpenAITTS(TTSProvider):
    """
    OpenAI TTS Provider

    Latency: 200-300ms
    Cost: $0.015/min (tts-1) or $0.030/min (tts-1-hd)
    Best for: Good quality, reliable
    """

    def __init__(self, api_key: Optional[str] = None, voice: str = "alloy"):
        super().__init__(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            voice=voice
        )
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize OpenAI client"""
        try:
            import openai
            self.client = openai.AsyncOpenAI(api_key=self.api_key)
            self.logger.info(f"OpenAI TTS initialized with voice: {self.voice}")
        except ImportError:
            self.logger.error("openai package not installed. Run: pip install openai")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI: {e}")
            raise

    async def synthesize(self, text: str) -> bytes:
        """Synthesize speech using OpenAI"""
        try:
            self.logger.info(f"[OpenAI TTS] 🔊 Synthesizing text (length: {len(text)} chars)")
            self.logger.info(f"[OpenAI TTS] 🔊 Using voice: {self.voice}, model: tts-1")

            response = await self.client.audio.speech.create(
                model="tts-1",  # Faster model
                voice=self.voice,
                input=text,
                response_format="pcm"
            )

            audio_bytes = response.content
            self.logger.info(f"[OpenAI TTS] ✅ Synthesis complete: {len(audio_bytes)} bytes returned")

            if not audio_bytes or len(audio_bytes) == 0:
                self.logger.error(f"[OpenAI TTS] ❌ CRITICAL: OpenAI returned empty audio!")
                self.logger.error(f"[OpenAI TTS] ❌ Text was: \"{text[:100]}...\"")
                return bytes()  # Return empty bytes instead of None

            return audio_bytes

        except Exception as e:
            self.logger.error(f"[OpenAI TTS] ❌ Synthesis error: {e}", exc_info=True)
            raise

    async def synthesize_stream(self, text: str) -> bytes:
        """OpenAI TTS with streaming response"""
        try:
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice=self.voice,
                input=text,
                response_format="pcm"
            )

            return response.content

        except Exception as e:
            self.logger.error(f"OpenAI streaming error: {e}")
            return await self.synthesize(text)

    def get_latency_ms(self) -> int:
        """Average latency: 200-300ms"""
        return 250

    def get_cost_per_minute(self) -> float:
        """Cost: $0.015/min (tts-1 model)"""
        return 0.015

    def get_available_voices(self) -> Dict[str, str]:
        """Available OpenAI voices"""
        return {
            "alloy": "Neutral, balanced voice",
            "echo": "Male voice",
            "fable": "British male voice",
            "onyx": "Deep male voice",
            "nova": "Female voice",
            "shimmer": "Soft female voice"
        }


class SarvamTTS(TTSProvider):
    """
    Sarvam AI TTS Provider (HTTP API)

    Latency: 300-500ms
    Cost: Varies
    Best for: Indian languages (Hindi, Tamil, Telugu, etc.)
    """

    def __init__(self, api_key: Optional[str] = None, voice: str = "manisha", language: str = "hi-IN"):
        super().__init__(
            api_key=api_key or os.getenv("SARVAM_API_KEY"),
            voice=voice
        )
        self.language = language
        self.api_url = "https://api.sarvam.ai/text-to-speech"
        self.logger.info(f"Sarvam TTS initialized with voice: {voice}, language: {language}")

    async def synthesize(self, text: str) -> bytes:
        """Synthesize speech using Sarvam AI HTTP API"""
        try:
            self.logger.info(f"[Sarvam TTS] 🔊 Synthesizing text (length: {len(text)} chars)")

            payload = {
                "target_language_code": self.language,
                "text": text,
                "speaker": self.voice,
                "pitch": 0.0,
                "loudness": 1.0,
                "speech_sample_rate": 8000,
                "enable_preprocessing": True,
                "model": "bulbul:v2"
            }

            headers = {
                'api-subscription-key': self.api_key,
                'api-key': self.api_key,
                'x-api-key': self.api_key,
                'authorization': f"Bearer {self.api_key}",
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        audios = data.get('audios', [])
                        if audios and isinstance(audios, list) and len(audios) > 0:
                            # Sarvam returns base64 encoded audio
                            audio_b64 = audios[0]
                            audio_bytes = base64.b64decode(audio_b64)
                            self.logger.info(f"[Sarvam TTS] ✅ Synthesis complete: {len(audio_bytes)} bytes returned")
                            return audio_bytes
                        else:
                            self.logger.error(f"[Sarvam TTS] ❌ No audio in response: {data}")
                            return bytes()
                    else:
                        error_text = await response.text()
                        self.logger.error(f"[Sarvam TTS] ❌ API error ({response.status}): {error_text}")
                        return bytes()

        except Exception as e:
            self.logger.error(f"[Sarvam TTS] ❌ Synthesis error: {e}", exc_info=True)
            raise

    async def synthesize_stream(self, text: str) -> bytes:
        """Sarvam HTTP API doesn't support streaming, use regular synthesis"""
        return await self.synthesize(text)

    def get_latency_ms(self) -> int:
        """Average latency: 300-500ms"""
        return 400

    def get_cost_per_minute(self) -> float:
        """Cost: TBD (varies by plan)"""
        return 0.02

    def get_available_voices(self) -> Dict[str, str]:
        """Available Sarvam voices"""
        return {
            "anushka": "Female Hindi voice (default)",
            "manisha": "Female bilingual Hindi/English voice",
            "vidya": "Female Hindi voice",
            "arya": "Female Hindi voice",
            "abhilash": "Male Hindi voice",
            "karun": "Male Hindi voice",
            "hitesh": "Male Hindi/English voice"
        }


class PiperTTS(TTSProvider):
    """
    Piper offline TTS provider.

    Latency: ~50-200ms (local CPU, model-dependent)
    Cost: $0.00/min
    Best for: Offline/local deployments
    """

    _voice_cache = {}
    _voice_lock = threading.Lock()

    def __init__(self, api_key: Optional[str] = None, voice: str = "en_US-lessac-medium"):
        # api_key is unused for Piper, but kept for factory compatibility.
        super().__init__(api_key=api_key or "", voice=voice)
        self.models_dir = os.environ.get(
            "PIPER_MODELS_DIR",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models", "piper"))
        )
        self._voice = self._get_or_load_voice()

    def _get_model_path(self) -> str:
        model_path = os.path.join(self.models_dir, self.voice, f"{self.voice}.onnx")
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Piper model not found: {model_path}. "
                f"Set PIPER_MODELS_DIR or download model files."
            )
        return model_path

    def _get_or_load_voice(self):
        cache_key = f"{self.models_dir}:{self.voice}"
        if cache_key in self._voice_cache:
            return self._voice_cache[cache_key]

        with self._voice_lock:
            if cache_key in self._voice_cache:
                return self._voice_cache[cache_key]

            try:
                from piper import PiperVoice
            except ImportError as e:
                raise ImportError("piper-tts is not installed. Install with: pip install piper-tts") from e

            model_path = self._get_model_path()
            voice_obj = PiperVoice.load(model_path)
            self._voice_cache[cache_key] = voice_obj
            self.logger.info(f"Piper TTS initialized with voice: {self.voice}")
            return voice_obj

    def _synthesize_native_pcm(self, text: str) -> tuple[bytes, int]:
        synth_params = inspect.signature(self._voice.synthesize).parameters

        if "syn_config" in synth_params:
            try:
                from piper.config import SynthesisConfig
                syn_config = SynthesisConfig()
                chunks = list(self._voice.synthesize(text, syn_config=syn_config))
            except Exception:
                chunks = list(self._voice.synthesize(text))

            if not chunks:
                return b"", 22050

            sample_rate = chunks[0].sample_rate
            pcm = b"".join(chunk.audio_int16_bytes for chunk in chunks)
            return pcm, sample_rate

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            self._voice.synthesize(text, wav_file)

        wav_buffer.seek(0)
        with wave.open(wav_buffer, "rb") as wav_file:
            pcm = wav_file.readframes(wav_file.getnframes())
            sample_rate = wav_file.getframerate()

        return pcm, sample_rate

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize text and return 8kHz PCM s16le bytes.
        The custom Twilio pipeline converts this to μ-law.
        """
        if not text or not text.strip():
            return bytes()

        loop = asyncio.get_event_loop()
        pcm_native, native_rate = await loop.run_in_executor(
            None,
            lambda: self._synthesize_native_pcm(text)
        )

        if not pcm_native:
            return bytes()

        if native_rate != 8000:
            pcm_8k, _ = audioop.ratecv(pcm_native, 2, 1, native_rate, 8000, None)
            return pcm_8k
        return pcm_native

    async def synthesize_stream(self, text: str) -> bytes:
        """Piper provider currently uses non-streaming synthesis."""
        return await self.synthesize(text)

    def get_latency_ms(self) -> int:
        return 120

    def get_cost_per_minute(self) -> float:
        return 0.0

    def get_available_voices(self) -> Dict[str, str]:
        return {
            "en_US-lessac-medium": "English (US), medium quality",
            "en_US-amy-medium": "English (US), medium quality",
        }


class XttsTTS(TTSProvider):
    """
    Coqui XTTS v2 TTS Provider (self-hosted)

    Latency: 200-500ms (depends on hardware)
    Cost: $0.00/min (self-hosted)
    Best for: Privacy, voice cloning, no API costs
    """

    def __init__(self, api_key: Optional[str] = None, voice: str = "default", **kwargs):
        super().__init__(
            api_key=api_key or os.getenv("XTTS_API_URL", "http://localhost:5500"),
            voice=voice
        )
        self.base_url = self.api_key.rstrip("/")
        self.language = kwargs.get('language', 'en')
        self.speaker_embedding = None
        self.gpt_cond_latent = None
        self.logger.info(f"XTTS TTS initialized with URL: {self.base_url}")

    async def _load_speaker(self):
        """Load speaker embeddings from XTTS server"""
        if self.speaker_embedding:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/studio_speakers", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        speakers = await resp.json()
                        if speakers:
                            name = list(speakers.keys())[0]
                            self.speaker_embedding = speakers[name].get('speaker_embedding')
                            self.gpt_cond_latent = speakers[name].get('gpt_cond_latent')
                            self.logger.info(f"XTTS loaded speaker: {name}")
        except Exception as e:
            self.logger.error(f"XTTS failed to load speaker: {e}")

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to speech via XTTS server"""
        await self._load_speaker()

        if not self.speaker_embedding or not self.gpt_cond_latent:
            self.logger.error("XTTS: No speaker embeddings available")
            return bytes()

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": text,
                    "language": self.language,
                    "speaker_embedding": self.speaker_embedding,
                    "gpt_cond_latent": self.gpt_cond_latent
                }
                async with session.post(f"{self.base_url}/tts", json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    else:
                        error = await resp.text()
                        self.logger.error(f"XTTS synthesis failed: {resp.status} - {error}")
                        return bytes()
        except Exception as e:
            self.logger.error(f"XTTS synthesis error: {e}")
            return bytes()

    async def synthesize_stream(self, text: str) -> bytes:
        """Stream synthesis via XTTS server"""
        return await self.synthesize(text)

    def get_latency_ms(self) -> int:
        return 300

    def get_cost_per_minute(self) -> float:
        return 0.0

    def get_available_voices(self) -> Dict[str, str]:
        return {
            "default": "XTTS v2 default voice",
            "cloned": "Clone from reference audio via /clone_speaker",
        }
