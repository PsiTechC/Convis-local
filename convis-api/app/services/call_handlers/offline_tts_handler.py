"""
Offline Piper TTS Handler

Uses Piper (ONNX-based) for local text-to-speech synthesis.
No internet required — runs entirely on CPU with ~50ms latency.

Matches the interface of StreamingElevenLabsTTS / StreamingOpenAITTS
so it can be dropped in as a replacement.
"""

import asyncio
import base64
import io
import inspect
import json
import logging
import os
import re
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


# ── XTTS speaker cache (singleton, shared across all XttsTTSHandler instances) ─
_xtts_speakers_cache = {}
_xtts_cache_lock = threading.Lock()


def _get_xtts_speakers_sync(xtts_url: str) -> dict:
    """Load all XTTS studio speakers once, cache globally."""
    if _xtts_speakers_cache:
        return _xtts_speakers_cache

    with _xtts_cache_lock:
        if _xtts_speakers_cache:
            return _xtts_speakers_cache

        import urllib.request
        import json

        url = f"{xtts_url}/studio_speakers"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                _xtts_speakers_cache.update(data)
                logger.info(f"[XTTS_TTS] Cached {len(data)} studio speakers: {list(data.keys())}")
        except Exception as e:
            logger.error(f"[XTTS_TTS] Failed to cache speakers: {e}")

    return _xtts_speakers_cache


def _float32_to_int16(pcm_float: bytes) -> bytes:
    """Convert float32 PCM samples to int16 PCM."""
    import array
    float_samples = array.array('f')
    float_samples.frombytes(pcm_float)
    int16_samples = array.array('h')
    for s in float_samples:
        # Clamp to [-1.0, 1.0] then scale to int16 range
        clamped = max(-1.0, min(1.0, s))
        int16_samples.append(int(clamped * 32767))
    return int16_samples.tobytes()


def _extract_xtts_audio_bytes(response_body: bytes) -> bytes:
    """Extract audio bytes from XTTS /tts responses across common payload shapes."""
    body = response_body.strip()
    if not body:
        return bytes()

    if body.startswith(b"RIFF"):
        return body

    text_body = body.decode("utf-8", errors="ignore").strip()
    if not text_body:
        return bytes()

    pending = []
    try:
        pending.append(json.loads(text_body))
    except json.JSONDecodeError:
        pending.append(text_body)

    while pending:
        candidate = pending.pop(0)

        if isinstance(candidate, str):
            stripped = candidate.strip().strip('"')
            if not stripped:
                continue
            try:
                decoded = base64.b64decode(stripped, validate=True)
                if decoded:
                    return decoded
            except Exception:
                continue

        elif isinstance(candidate, dict):
            for key in ("audio", "wav", "wav_base64", "audio_base64", "data"):
                value = candidate.get(key)
                if value is not None:
                    pending.append(value)

        elif isinstance(candidate, list):
            pending.extend(candidate)

    raise ValueError("XTTS response did not contain decodable audio data")


def warm_xtts_speakers(xtts_url: Optional[str] = None) -> dict:
    """Warm the global XTTS speaker cache."""
    resolved_url = xtts_url or os.environ.get("XTTS_API_URL", "http://host.docker.internal:5500")
    return _get_xtts_speakers_sync(resolved_url)


class XttsTTSHandler:
    """
    XTTS v2 TTS Handler — uses the XTTS GPU container for natural voice synthesis.
    Uses /tts_stream endpoint for low-latency streaming audio.
    Speaker embeddings are cached globally at startup.
    """

    def __init__(self, voice: str = "Gracie Wise", for_browser: bool = False):
        self.voice = voice
        self.for_browser = for_browser
        self.xtts_url = os.environ.get("XTTS_API_URL", "http://host.docker.internal:5500")
        self.native_sample_rate = 24000
        logger.info(f"[XTTS_TTS] Initialized: voice={voice}, url={self.xtts_url}")

    def _get_speaker_data(self) -> Optional[dict]:
        """Get cached speaker embedding for this voice."""
        speakers = _get_xtts_speakers_sync(self.xtts_url)
        if self.voice in speakers:
            return speakers[self.voice]
        if speakers:
            first_key = list(speakers.keys())[0]
            logger.warning(f"[XTTS_TTS] Voice '{self.voice}' not found, using '{first_key}'")
            return speakers[first_key]
        return None

    def _convert_to_mulaw(self, pcm_int16: bytes, source_rate: int) -> bytes:
        """Convert int16 PCM to 8kHz mulaw for Twilio."""
        resampled, _ = audioop.ratecv(pcm_int16, 2, 1, source_rate, 8000, None)
        return audioop.lin2ulaw(resampled, 2)

    def _convert_for_browser(self, pcm_int16: bytes, source_rate: int) -> bytes:
        """Convert int16 PCM to 24kHz PCM for browser playback."""
        resampled, _ = audioop.ratecv(pcm_int16, 2, 1, source_rate, 24000, None)
        return resampled

    def _process_wav_bytes(self, wav_data: bytes) -> bytes:
        """Parse WAV bytes, handle float32→int16 conversion, return int16 PCM."""
        if wav_data[:4] == b'RIFF':
            wav_io = io.BytesIO(wav_data)
            with wave.open(wav_io, 'rb') as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                raw_frames = wf.readframes(wf.getnframes())
                logger.debug(f"[XTTS_TTS] WAV: {sample_rate}Hz, {n_channels}ch, {sample_width}B/sample")

            # Convert stereo to mono
            if n_channels == 2:
                raw_frames = audioop.tomono(raw_frames, sample_width, 1, 1)

            # XTTS often outputs float32 (sample_width=4) — must convert to int16
            if sample_width == 4:
                pcm_int16 = _float32_to_int16(raw_frames)
            elif sample_width == 2:
                pcm_int16 = raw_frames
            elif sample_width == 1:
                pcm_int16 = audioop.bias(raw_frames, 1, -128)
                pcm_int16 = audioop.lin2lin(pcm_int16, 1, 2)
            else:
                pcm_int16 = raw_frames
                logger.warning(f"[XTTS_TTS] Unexpected sample_width={sample_width}, passing through")

            self.native_sample_rate = sample_rate
            return pcm_int16
        else:
            # Raw PCM — assume 24kHz int16
            self.native_sample_rate = 24000
            return wav_data

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text using XTTS /tts_stream and return audio."""
        if not text or not text.strip():
            return bytes()

        speaker_data = self._get_speaker_data()
        if not speaker_data:
            logger.error("[XTTS_TTS] No speaker data available")
            return bytes()

        import aiohttp

        _start = time.time()

        try:
            payload = {
                "text": text,
                "language": "en",
                "speaker_embedding": speaker_data["speaker_embedding"],
                "gpt_cond_latent": speaker_data["gpt_cond_latent"],
                "add_wav_header": False,
            }

            async with aiohttp.ClientSession() as session:
                # Use /tts_stream for lower latency — returns raw 24kHz int16 PCM chunks
                async with session.post(
                    f"{self.xtts_url}/tts_stream",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        raw_pcm = await resp.read()

                        # /tts_stream with add_wav_header=False returns raw 24kHz int16 PCM
                        pcm_int16 = raw_pcm
                        source_rate = 24000

                        # Check if we got a WAV header instead (fallback)
                        if raw_pcm[:4] == b'RIFF':
                            pcm_int16 = self._process_wav_bytes(raw_pcm)
                            source_rate = self.native_sample_rate

                        if not self.for_browser:
                            mulaw_audio = self._convert_to_mulaw(pcm_int16, source_rate)
                            _elapsed = (time.time() - _start) * 1000
                            logger.info(f"[XTTS_TTS] Stream synthesized {len(mulaw_audio)} bytes (8kHz mulaw) in {_elapsed:.0f}ms: {text[:50]}...")
                            return mulaw_audio
                        else:
                            browser_audio = self._convert_for_browser(pcm_int16, source_rate)
                            _elapsed = (time.time() - _start) * 1000
                            logger.info(f"[XTTS_TTS] Stream synthesized {len(browser_audio)} bytes (24kHz PCM) in {_elapsed:.0f}ms: {text[:50]}...")
                            return browser_audio
                    else:
                        error_body = await resp.text()
                        logger.error(f"[XTTS_TTS] /tts_stream error {resp.status}: {error_body[:200]}")
                        # Fallback to /tts endpoint
                        return await self._synthesize_fallback(text, speaker_data, session)

        except Exception as e:
            logger.error(f"[XTTS_TTS] Synthesis error: {e}", exc_info=True)
            return bytes()

    async def _synthesize_fallback(self, text: str, speaker_data: dict, session) -> bytes:
        """Fallback: use /tts endpoint which returns base64 WAV JSON."""
        import base64

        _start = time.time()
        try:
            payload = {
                "text": text,
                "language": "en",
                "speaker_embedding": speaker_data["speaker_embedding"],
                "gpt_cond_latent": speaker_data["gpt_cond_latent"],
            }

            async with session.post(
                f"{self.xtts_url}/tts",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    raw_response = await resp.read()
                    wav_data = _extract_xtts_audio_bytes(raw_response)

                    pcm_int16 = self._process_wav_bytes(wav_data)

                    if not self.for_browser:
                        mulaw_audio = self._convert_to_mulaw(pcm_int16, self.native_sample_rate)
                        _elapsed = (time.time() - _start) * 1000
                        logger.info(f"[XTTS_TTS] Fallback synthesized {len(mulaw_audio)} bytes (8kHz mulaw) in {_elapsed:.0f}ms: {text[:50]}...")
                        return mulaw_audio
                    else:
                        browser_audio = self._convert_for_browser(pcm_int16, self.native_sample_rate)
                        _elapsed = (time.time() - _start) * 1000
                        logger.info(f"[XTTS_TTS] Fallback synthesized {len(browser_audio)} bytes (24kHz PCM) in {_elapsed:.0f}ms: {text[:50]}...")
                        return browser_audio
                else:
                    logger.error(f"[XTTS_TTS] /tts fallback error: {resp.status}")
                    return bytes()
        except Exception as e:
            logger.error(f"[XTTS_TTS] Fallback synthesis error: {e}", exc_info=True)
            return bytes()

    async def synthesize_streaming(
        self,
        text: str,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None,
    ) -> bytes:
        """True streaming: use /tts_stream with chunked reading for progressive playback."""
        if not text or not text.strip():
            return bytes()

        speaker_data = self._get_speaker_data()
        if not speaker_data:
            logger.error("[XTTS_TTS] No speaker data available")
            return bytes()

        import aiohttp

        _start = time.time()
        all_audio = bytearray()

        try:
            payload = {
                "text": text,
                "language": "en",
                "speaker_embedding": speaker_data["speaker_embedding"],
                "gpt_cond_latent": speaker_data["gpt_cond_latent"],
                "add_wav_header": False,
            }

            ratecv_state = None

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.xtts_url}/tts_stream",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        # Fall back to sentence-by-sentence
                        return await self._stream_by_sentence(text, on_audio_chunk)

                    # Read chunks as they arrive — raw 24kHz int16 PCM
                    chunk_size = 4800  # 100ms of 24kHz int16 mono (2400 samples × 2 bytes)
                    async for raw_chunk in resp.content.iter_chunked(chunk_size):
                        if not raw_chunk:
                            continue

                        if not self.for_browser:
                            pcm_8k, ratecv_state = audioop.ratecv(
                                raw_chunk, 2, 1, 24000, 8000, ratecv_state
                            )
                            converted = audioop.lin2ulaw(pcm_8k, 2)
                        else:
                            converted = raw_chunk

                        all_audio.extend(converted)
                        if on_audio_chunk:
                            await on_audio_chunk(converted)

            _elapsed = (time.time() - _start) * 1000
            fmt = "8kHz mulaw" if not self.for_browser else "24kHz PCM"
            logger.info(f"[XTTS_TTS] Streamed {len(all_audio)} bytes ({fmt}) in {_elapsed:.0f}ms: {text[:50]}...")
            return bytes(all_audio)

        except Exception as e:
            logger.error(f"[XTTS_TTS] Streaming error: {e}", exc_info=True)
            # Fall back to sentence-by-sentence
            return await self._stream_by_sentence(text, on_audio_chunk)

    async def _stream_by_sentence(
        self,
        text: str,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None,
    ) -> bytes:
        """Fallback streaming: split into sentences and synthesize each."""
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
