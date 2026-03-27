"""
Offline Piper TTS Handler

Uses Piper (ONNX-based) for local text-to-speech synthesis.
No internet required — runs entirely on CPU with ~50ms latency.

Matches the interface of StreamingElevenLabsTTS / StreamingOpenAITTS
so it can be dropped in as a replacement.
"""

import asyncio
import io
import inspect
import logging
import os
import re
import struct
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable, Awaitable

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop

try:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    SynthesisConfig = None

logger = logging.getLogger(__name__)

# ── Singleton voice cache ────────────────────────────────────────────────────

_piper_voices = {}
_piper_lock = threading.Lock()

PIPER_MODELS_DIR = os.environ.get("PIPER_MODELS_DIR", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "models", "piper"
))


def _get_or_load_voice(voice_name: str):
    """Load Piper voice model once, reuse across calls."""
    if voice_name in _piper_voices:
        return _piper_voices[voice_name]

    with _piper_lock:
        if voice_name in _piper_voices:
            return _piper_voices[voice_name]

        if not PIPER_AVAILABLE:
            raise ImportError(
                "piper-tts is not installed. "
                "Install it with: pip install piper-tts"
            )

        model_path = _resolve_model_path(voice_name)
        logger.info(f"[PIPER_TTS] Loading voice '{voice_name}' from {model_path}...")
        load_start = time.time()

        voice = PiperVoice.load(model_path)

        load_time = (time.time() - load_start) * 1000
        logger.info(f"[PIPER_TTS] Voice '{voice_name}' loaded in {load_time:.0f}ms")

        _piper_voices[voice_name] = voice
        return voice


def _resolve_model_path(voice_name: str) -> str:
    """Find or download Piper voice model."""
    model_dir = os.path.join(PIPER_MODELS_DIR, voice_name)
    onnx_path = os.path.join(model_dir, f"{voice_name}.onnx")

    if os.path.exists(onnx_path):
        return onnx_path

    # Auto-download from HuggingFace
    _download_piper_model(voice_name, model_dir)

    if not os.path.exists(onnx_path):
        raise FileNotFoundError(
            f"Piper model '{voice_name}' not found at {onnx_path}. "
            f"Download it manually from https://huggingface.co/rhasspy/piper-voices"
        )

    return onnx_path


def _download_piper_model(voice_name: str, target_dir: str):
    """Download Piper voice model from HuggingFace."""
    import urllib.request

    os.makedirs(target_dir, exist_ok=True)

    # Parse voice name: e.g. "en_US-lessac-medium" → lang=en, region=US, name=lessac, quality=medium
    parts = voice_name.split("-")
    if len(parts) < 3:
        logger.error(f"[PIPER_TTS] Invalid voice name format: {voice_name}")
        return

    lang_region = parts[0]  # e.g. "en_US"
    voice = parts[1]         # e.g. "lessac"
    quality = parts[2]       # e.g. "medium"

    # HuggingFace URL pattern
    lang = lang_region.split("_")[0]  # "en"
    base_url = (
        f"https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
        f"{lang}/{lang_region}/{voice}/{quality}"
    )

    for ext in [".onnx", ".onnx.json"]:
        filename = f"{voice_name}{ext}"
        url = f"{base_url}/{filename}"
        dest = os.path.join(target_dir, filename)

        if os.path.exists(dest):
            continue

        logger.info(f"[PIPER_TTS] Downloading {filename}...")
        try:
            urllib.request.urlretrieve(url, dest)
            size_mb = os.path.getsize(dest) / (1024 * 1024)
            logger.info(f"[PIPER_TTS] Downloaded {filename} ({size_mb:.1f}MB)")
        except Exception as e:
            logger.error(f"[PIPER_TTS] Failed to download {filename}: {e}")
            # Clean up partial download
            if os.path.exists(dest):
                os.remove(dest)
            raise


class OfflinePiperTTS:
    """
    Offline TTS using Piper (ONNX).

    Matches the interface of StreamingElevenLabsTTS / StreamingOpenAITTS.
    """

    def __init__(
        self,
        voice: str = "en_US-lessac-medium",
        for_browser: bool = False,
        length_scale: float = 1.0,
        noise_scale: float = 0.667,
        noise_w: float = 0.8,
        speaker_id: Optional[int] = None,
    ):
        self.voice_name = voice
        self.for_browser = for_browser
        self.length_scale = length_scale
        self.noise_scale = noise_scale
        self.noise_w = noise_w
        self.speaker_id = speaker_id

        # Loaded lazily
        self._voice = None
        self._native_sample_rate = 22050  # Default, updated after model load

        # Thread executor for blocking ONNX inference
        self._executor = ThreadPoolExecutor(max_workers=1)

        logger.info(f"[PIPER_TTS] Initialized: voice={voice}, for_browser={for_browser}")

    def _ensure_loaded(self):
        """Lazy-load voice model on first use."""
        if self._voice is not None:
            return

        self._voice = _get_or_load_voice(self.voice_name)

        # Get native sample rate from model config
        if hasattr(self._voice, 'config') and hasattr(self._voice.config, 'sample_rate'):
            self._native_sample_rate = self._voice.config.sample_rate
        logger.info(f"[PIPER_TTS] Native sample rate: {self._native_sample_rate}Hz")

    def _synthesize_raw(self, text: str) -> bytes:
        """Synthesize text to raw PCM bytes (blocking, runs in thread)."""
        self._ensure_loaded()

        synth_params = inspect.signature(self._voice.synthesize).parameters

        # Newer piper-tts returns AudioChunk objects directly.
        if "syn_config" in synth_params:
            if SynthesisConfig is None:
                raise RuntimeError("SynthesisConfig unavailable with current piper installation")

            syn_config = SynthesisConfig(
                speaker_id=self.speaker_id,
                length_scale=self.length_scale,
                noise_scale=self.noise_scale,
                noise_w_scale=self.noise_w,
            )

            pcm_parts = []
            sample_rate = None
            for chunk in self._voice.synthesize(text, syn_config=syn_config):
                if sample_rate is None:
                    sample_rate = chunk.sample_rate
                pcm_parts.append(chunk.audio_int16_bytes)

            if sample_rate:
                self._native_sample_rate = sample_rate

            return b"".join(pcm_parts)

        # Older piper-tts writes WAV to a file-like object.
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            self._voice.synthesize(
                text,
                wav_file,
                length_scale=self.length_scale,
                noise_scale=self.noise_scale,
                noise_w=self.noise_w,
                speaker_id=self.speaker_id,
            )

        # Extract raw PCM from WAV (skip header)
        wav_buffer.seek(0)
        with wave.open(wav_buffer, 'rb') as wav_file:
            raw_pcm = wav_file.readframes(wav_file.getnframes())
            self._native_sample_rate = wav_file.getframerate()

        return raw_pcm

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize speech from text.
        Returns audio in the configured format:
        - for_browser=True: 24kHz PCM (16-bit signed LE)
        - for_browser=False: 8kHz mulaw (for Twilio)
        """
        if not text or not text.strip():
            return bytes()

        try:
            loop = asyncio.get_event_loop()
            synth_start = time.time()

            raw_pcm = await loop.run_in_executor(
                self._executor,
                lambda: self._synthesize_raw(text)
            )

            if not raw_pcm:
                return bytes()

            synth_time = (time.time() - synth_start) * 1000

            if self.for_browser:
                # Resample to 24kHz PCM for browser playback
                resampled, _ = audioop.ratecv(
                    raw_pcm, 2, 1, self._native_sample_rate, 24000, None
                )
                logger.info(f"[PIPER_TTS] Synthesized {len(resampled)} bytes "
                             f"(24kHz PCM) in {synth_time:.0f}ms: {text[:50]}...")
                return resampled
            else:
                # Resample to 8kHz and convert to mulaw for Twilio
                resampled, _ = audioop.ratecv(
                    raw_pcm, 2, 1, self._native_sample_rate, 8000, None
                )
                mulaw = audioop.lin2ulaw(resampled, 2)
                logger.info(f"[PIPER_TTS] Synthesized {len(mulaw)} bytes "
                             f"(8kHz mulaw) in {synth_time:.0f}ms: {text[:50]}...")
                return mulaw

        except Exception as e:
            logger.error(f"[PIPER_TTS] Synthesis error: {e}", exc_info=True)
            return bytes()

    async def synthesize_streaming(
        self,
        text: str,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None,
    ) -> bytes:
        """
        Pseudo-streaming: split text into sentences, synthesize each,
        fire on_audio_chunk per sentence for progressive playback.
        """
        if not text or not text.strip():
            return bytes()

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        all_audio = bytearray()

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            audio = await self.synthesize(sentence)
            if audio:
                all_audio.extend(audio)
                if on_audio_chunk:
                    await on_audio_chunk(audio)

        return bytes(all_audio)


class XttsTTSHandler:
    """
    XTTS v2 TTS Handler — uses the XTTS GPU container for natural voice synthesis.
    Streams audio via the /tts_stream endpoint for lower latency.
    """

    def __init__(self, voice: str = "Gracie Wise", for_browser: bool = False):
        self.voice = voice
        self.for_browser = for_browser
        self.xtts_url = os.environ.get("XTTS_API_URL", "http://host.docker.internal:5500")
        self._speakers = None
        self._speaker_data = None
        self.native_sample_rate = 24000
        logger.info(f"[XTTS_TTS] Initialized: voice={voice}, url={self.xtts_url}")

    async def _load_speaker(self):
        """Load speaker embedding from XTTS container."""
        if self._speaker_data:
            return

        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.xtts_url}/studio_speakers") as resp:
                    if resp.status == 200:
                        self._speakers = await resp.json()
                        if self.voice in self._speakers:
                            self._speaker_data = self._speakers[self.voice]
                            logger.info(f"[XTTS_TTS] Loaded speaker: {self.voice}")
                        else:
                            # Fallback to first available speaker
                            first_key = list(self._speakers.keys())[0]
                            self._speaker_data = self._speakers[first_key]
                            logger.warning(f"[XTTS_TTS] Voice '{self.voice}' not found, using '{first_key}'")
                    else:
                        logger.error(f"[XTTS_TTS] Failed to load speakers: {resp.status}")
        except Exception as e:
            logger.error(f"[XTTS_TTS] Error loading speakers: {e}")

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text using XTTS and return 8kHz mulaw audio."""
        if not text or not text.strip():
            return bytes()

        await self._load_speaker()
        if not self._speaker_data:
            logger.error("[XTTS_TTS] No speaker data available")
            return bytes()

        import aiohttp
        import base64

        _start = time.time()

        try:
            payload = {
                "text": text,
                "language": "en",
                "speaker_embedding": self._speaker_data["speaker_embedding"],
                "gpt_cond_latent": self._speaker_data["gpt_cond_latent"],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.xtts_url}/tts", json=payload) as resp:
                    if resp.status == 200:
                        response_data = await resp.json()
                        if isinstance(response_data, str):
                            audio_b64 = response_data
                        else:
                            audio_b64 = await resp.text()
                            audio_b64 = audio_b64.strip('"')

                        pcm_24k = base64.b64decode(audio_b64)

                        # Remove WAV header if present (first 44 bytes)
                        if pcm_24k[:4] == b'RIFF':
                            pcm_24k = pcm_24k[44:]

                        # Convert 24kHz PCM to 8kHz mulaw for Twilio
                        if not self.for_browser:
                            pcm_8k, _ = audioop.ratecv(pcm_24k, 2, 1, self.native_sample_rate, 8000, None)
                            mulaw_audio = audioop.lin2ulaw(pcm_8k, 2)
                            _elapsed = (time.time() - _start) * 1000
                            logger.info(f"[XTTS_TTS] Synthesized {len(mulaw_audio)} bytes (8kHz mulaw) in {_elapsed:.0f}ms: {text[:50]}...")
                            return mulaw_audio
                        else:
                            _elapsed = (time.time() - _start) * 1000
                            logger.info(f"[XTTS_TTS] Synthesized {len(pcm_24k)} bytes (24kHz PCM) in {_elapsed:.0f}ms: {text[:50]}...")
                            return pcm_24k
                    else:
                        logger.error(f"[XTTS_TTS] API error: {resp.status}")
                        return bytes()

        except Exception as e:
            logger.error(f"[XTTS_TTS] Synthesis error: {e}")
            return bytes()

    async def synthesize_streaming(
        self,
        text: str,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None,
    ) -> bytes:
        """Stream synthesis — split into sentences, synthesize each via XTTS."""
        if not text or not text.strip():
            return bytes()

        sentences = re.split(r'(?<=[.!?])\s+', text)
        all_audio = bytearray()

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            audio = await self.synthesize(sentence)
            if audio:
                all_audio.extend(audio)
                if on_audio_chunk:
                    await on_audio_chunk(audio)

        return bytes(all_audio)
