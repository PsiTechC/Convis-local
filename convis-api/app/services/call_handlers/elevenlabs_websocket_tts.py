"""
ElevenLabs WebSocket TTS for True Word-by-Word Streaming

Latency: ~100-200ms to first audio (vs 300-600ms sentence-by-sentence)

Flow:
  LLM token → WebSocket → ElevenLabs → Audio chunk → Twilio
       ↑                                    ↓
       └────── All happening in real-time ──┘
"""

import asyncio
import json
import logging
import base64
from typing import Optional, Callable, Awaitable, AsyncIterator, Dict, Any

try:
    import websockets
except ImportError:
    websockets = None

logger = logging.getLogger(__name__)


class ElevenLabsWebSocketTTS:
    """
    True streaming TTS using ElevenLabs WebSocket input streaming API.
    Sends text word-by-word, receives audio chunk-by-chunk.

    Supported Models:
    - eleven_turbo_v2_5: Fastest, English-optimized (~100ms latency)
    - eleven_turbo_v2: Fast, English-optimized
    - eleven_multilingual_v2: Multi-language support (29 languages)
    - eleven_monolingual_v1: Original English model

    Supported Output Formats:
    - ulaw_8000: μ-law 8kHz (Twilio compatible, no conversion needed)
    - pcm_16000: PCM 16kHz (needs conversion for Twilio)
    - pcm_22050: PCM 22.05kHz
    - pcm_24000: PCM 24kHz
    - pcm_44100: PCM 44.1kHz
    - mp3_44100_128: MP3 format
    """

    # Common voice name to ID mappings (user can also pass voice ID directly)
    VOICE_IDS = {
        # ElevenLabs default voices
        "rachel": "21m00Tcm4TlvDq8ikWAM",
        "domi": "AZnzlk1XvdvUeBnXmlld",
        "bella": "EXAVITQu4vr4xnSDxMaL",
        "antoni": "ErXwobaYiN019PkySvjV",
        "josh": "TxGEqnHWrfWFTfGW9XjX",
        "arnold": "VR6AewLTigWG4xSOukaG",
        "adam": "pNInz6obpgDQGcFmaJgB",
        "sam": "yoZ06aMxZJJ28mfd3POQ",
        "shimmer": "N2lVS1w4EtoT3dr4eOWO",
        # Aliases for OpenAI voice names
        "alloy": "pNInz6obpgDQGcFmaJgB",  # maps to adam
        "echo": "TxGEqnHWrfWFTfGW9XjX",   # maps to josh
        "fable": "ErXwobaYiN019PkySvjV",  # maps to antoni
        "onyx": "VR6AewLTigWG4xSOukaG",   # maps to arnold
        "nova": "EXAVITQu4vr4xnSDxMaL",   # maps to bella
    }

    # Default voice settings
    DEFAULT_VOICE_SETTINGS = {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": False
    }

    def __init__(
        self,
        api_key: str,
        voice: str = "shimmer",
        model: str = "eleven_turbo_v2_5",
        output_format: str = "ulaw_8000",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = False,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None
    ):
        """
        Initialize ElevenLabs WebSocket TTS.

        Args:
            api_key: ElevenLabs API key
            voice: Voice name or ID (see VOICE_IDS for supported names)
            model: TTS model (eleven_turbo_v2_5, eleven_multilingual_v2, etc.)
            output_format: Audio format (ulaw_8000 for Twilio, pcm_16000, etc.)
            stability: Voice stability (0.0-1.0, higher = more consistent)
            similarity_boost: Voice clarity (0.0-1.0, higher = clearer)
            style: Style exaggeration (0.0-1.0, experimental)
            use_speaker_boost: Boost speaker similarity (can add latency)
            on_audio_chunk: Callback for each audio chunk (for streaming playback)
        """
        self.api_key = api_key
        self.voice_id = self.VOICE_IDS.get(voice.lower(), voice)
        self.model = model
        self.output_format = output_format
        self.on_audio_chunk = on_audio_chunk

        # Voice settings (all configurable)
        self.voice_settings = {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": use_speaker_boost
        }

        # WebSocket state
        self.ws = None
        self.is_connected = False
        self.receive_task = None
        self.audio_buffer = bytearray()
        self.generation_complete = asyncio.Event()
        self.first_audio_received = asyncio.Event()

        logger.info(f"[11LABS_WS] Initialized: voice={voice} ({self.voice_id}), "
                   f"model={model}, format={output_format}")

    @property
    def websocket_url(self) -> str:
        """Build WebSocket URL with configured parameters"""
        return (
            f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input"
            f"?model_id={self.model}&output_format={self.output_format}"
        )

    async def connect(self) -> bool:
        """Connect to ElevenLabs WebSocket"""
        if websockets is None:
            logger.error("[11LABS_WS] websockets library not installed. Run: pip install websockets")
            return False

        try:
            logger.info(f"[11LABS_WS] 🔌 Connecting to: {self.websocket_url}")

            self.ws = await websockets.connect(
                self.websocket_url,
                additional_headers={"xi-api-key": self.api_key},
                ping_interval=30,
                ping_timeout=60,
            )

            # Send BOS (Beginning of Stream) with voice settings
            bos_message = {
                "text": " ",
                "voice_settings": self.voice_settings,
                "xi_api_key": self.api_key,
                "try_trigger_generation": False
            }
            await self.ws.send(json.dumps(bos_message))

            self.is_connected = True
            self.receive_task = asyncio.create_task(self._receive_loop())

            logger.info(f"[11LABS_WS] ✅ Connected (voice_settings: {self.voice_settings})")
            return True

        except Exception as e:
            logger.error(f"[11LABS_WS] ❌ Connection failed: {e}")
            return False

    async def _receive_loop(self):
        """Receive audio chunks from ElevenLabs"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)

                    if "audio" in data and data["audio"]:
                        audio_chunk = base64.b64decode(data["audio"])
                        self.audio_buffer.extend(audio_chunk)

                        if not self.first_audio_received.is_set():
                            self.first_audio_received.set()
                            logger.info("[11LABS_WS] ⚡ First audio chunk received!")

                        if self.on_audio_chunk:
                            await self.on_audio_chunk(audio_chunk)

                    if data.get("isFinal"):
                        self.generation_complete.set()
                        logger.debug("[11LABS_WS] Generation complete signal received")

                except json.JSONDecodeError:
                    pass  # Binary data, ignore

        except Exception as e:
            logger.error(f"[11LABS_WS] Receive error: {e}")
        finally:
            self.is_connected = False

    async def send_text(self, text: str, flush: bool = False):
        """
        Send text chunk for immediate synthesis.

        Args:
            text: Text to synthesize (can be single word/token)
            flush: Set True to flush and complete generation
        """
        if not self.is_connected or not self.ws:
            logger.warning("[11LABS_WS] Not connected, cannot send text")
            return

        try:
            await self.ws.send(json.dumps({
                "text": text,
                "try_trigger_generation": True,
                "flush": flush
            }))
        except Exception as e:
            logger.error(f"[11LABS_WS] Send error: {e}")

    async def stream_from_llm(
        self,
        token_iterator: AsyncIterator[str],
        on_first_audio: Optional[Callable[[], Awaitable[None]]] = None
    ) -> bytes:
        """
        Stream LLM tokens directly to TTS.

        Args:
            token_iterator: Async iterator yielding LLM tokens
            on_first_audio: Callback when first audio is ready

        Returns:
            Complete audio bytes
        """
        self.audio_buffer.clear()
        self.generation_complete.clear()
        self.first_audio_received.clear()

        if not self.is_connected:
            if not await self.connect():
                return bytes()

        try:
            async for token in token_iterator:
                if token:
                    await self.send_text(token)

                    if on_first_audio and self.first_audio_received.is_set():
                        await on_first_audio()
                        on_first_audio = None

            # Flush remaining audio
            await self.send_text("", flush=True)

            try:
                await asyncio.wait_for(self.generation_complete.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("[11LABS_WS] Timeout waiting for generation complete")

            return bytes(self.audio_buffer)

        except Exception as e:
            logger.error(f"[11LABS_WS] Stream error: {e}")
            return bytes(self.audio_buffer)

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize complete text (compatibility method).

        Args:
            text: Complete text to synthesize

        Returns:
            Audio bytes in configured format
        """
        self.audio_buffer.clear()
        self.generation_complete.clear()
        self.first_audio_received.clear()

        if not self.is_connected:
            if not await self.connect():
                return bytes()

        await self.send_text(text, flush=True)

        try:
            await asyncio.wait_for(self.generation_complete.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("[11LABS_WS] Timeout waiting for synthesis")

        return bytes(self.audio_buffer)

    async def close(self):
        """Close WebSocket connection"""
        self.is_connected = False

        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

        logger.info("[11LABS_WS] 🔌 Connection closed")

    def update_voice_settings(
        self,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
        use_speaker_boost: Optional[bool] = None
    ):
        """Update voice settings (requires reconnect to take effect)"""
        if stability is not None:
            self.voice_settings["stability"] = stability
        if similarity_boost is not None:
            self.voice_settings["similarity_boost"] = similarity_boost
        if style is not None:
            self.voice_settings["style"] = style
        if use_speaker_boost is not None:
            self.voice_settings["use_speaker_boost"] = use_speaker_boost


# Supported models documentation
ELEVENLABS_MODELS = {
    "eleven_turbo_v2_5": {
        "description": "Fastest model, English-optimized, ~100ms latency",
        "languages": ["en"],
        "streaming": True,
        "recommended_for": "Ultra-low-latency English conversations"
    },
    "eleven_turbo_v2": {
        "description": "Fast model, English-optimized",
        "languages": ["en"],
        "streaming": True,
        "recommended_for": "Low-latency English applications"
    },
    "eleven_multilingual_v2": {
        "description": "Multi-language support (29 languages)",
        "languages": ["en", "hi", "es", "fr", "de", "it", "pt", "pl", "zh", "ja", "ko", "ar", "ru", "nl", "tr", "sv", "id", "fil", "ms", "ro", "uk", "el", "cs", "da", "fi", "bg", "hr", "sk", "ta"],
        "streaming": True,
        "recommended_for": "Multi-language applications including Hindi"
    },
    "eleven_monolingual_v1": {
        "description": "Original English model",
        "languages": ["en"],
        "streaming": True,
        "recommended_for": "Legacy compatibility"
    }
}
