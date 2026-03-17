"""
Offline Whisper ASR Handler

Uses faster-whisper (CTranslate2) for local speech recognition.
No internet required — runs entirely on CPU.

Architecture: VAD-buffered batch transcription
- Audio chunks arrive via send_audio() (same interface as StreamingDeepgramASR)
- SileroVADProcessor detects speech boundaries
- When speech ends, faster-whisper transcribes the buffered audio
- Callbacks fire with the same signature as Deepgram handler
"""

import asyncio
import logging
import threading
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable, Awaitable

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Singleton model cache (same pattern as silero_vad.py) ────────────────────

_whisper_models = {}
_whisper_lock = threading.Lock()


def _get_or_load_model(model_size: str, device: str, compute_type: str):
    """Load Whisper model once, reuse across calls."""
    key = f"{model_size}_{device}_{compute_type}"

    if key in _whisper_models:
        return _whisper_models[key]

    with _whisper_lock:
        if key in _whisper_models:
            return _whisper_models[key]

        if not WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is not installed. "
                "Install it with: pip install faster-whisper"
            )

        logger.info(f"[OFFLINE_ASR] Loading Whisper '{model_size}' model "
                     f"(device={device}, compute_type={compute_type})...")
        load_start = time.time()

        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        load_time = (time.time() - load_start) * 1000
        logger.info(f"[OFFLINE_ASR] Whisper '{model_size}' loaded in {load_time:.0f}ms")

        _whisper_models[key] = model
        return model


class OfflineWhisperASR:
    """
    Offline ASR using faster-whisper + Silero VAD.

    Matches the StreamingDeepgramASR interface so it can be dropped in
    as a replacement in optimized_stream_handler.py and webrtc_handler.py.

    Audio flow:
    1. send_audio() receives raw audio chunks (mulaw 8kHz or linear16 16kHz)
    2. Audio is converted to float32 16kHz and fed to SileroVADProcessor
    3. During speech, audio is accumulated in a buffer
    4. When VAD detects end of speech, buffer is transcribed with faster-whisper
    5. Callbacks fire: on_transcript(text, is_final=True), on_utterance_end()
    """

    # Cap buffer at 30 seconds to prevent unbounded memory growth
    MAX_BUFFER_SAMPLES = 30 * 16000  # 480,000 samples at 16kHz

    def __init__(
        self,
        model_size: str = "base",
        language: str = "en",
        sample_rate: int = 8000,
        encoding: str = "mulaw",
        on_transcript: Optional[Callable] = None,
        on_utterance_end: Optional[Callable] = None,
        on_speech_started: Optional[Callable] = None,
        on_confidence_update: Optional[Callable] = None,
        endpointing_ms: int = 250,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size
        self.language = language
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.endpointing_ms = endpointing_ms
        self.device = device
        self.compute_type = compute_type

        # Callbacks (same signature as StreamingDeepgramASR)
        self.on_transcript = on_transcript
        self.on_utterance_end = on_utterance_end
        self.on_speech_started = on_speech_started
        self.on_confidence_update = on_confidence_update

        # State (matching StreamingDeepgramASR properties)
        self.is_connected = False
        self.current_transcript = ""
        self.ws = None  # Prevents keepalive loop from crashing (it checks self.asr.ws)

        # Whisper model (loaded lazily in connect())
        self._model = None

        # VAD processor
        self._vad = None

        # Audio buffer for transcription (float32, 16kHz)
        self._audio_buffer = []
        self._buffer_sample_count = 0
        self._is_speech_active = False
        self._speech_started_fired = False

        # Thread executor for blocking Whisper inference
        self._executor = ThreadPoolExecutor(max_workers=1)

        # Prevent concurrent transcriptions
        self._transcribing = False

        logger.info(f"[OFFLINE_ASR] Initialized: model={model_size}, language={language}, "
                     f"sample_rate={sample_rate}, encoding={encoding}")

    async def connect(self):
        """Load Whisper model and initialize VAD."""
        from app.utils.silero_vad import SileroVADProcessor

        # Load model in thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            self._executor,
            lambda: _get_or_load_model(self.model_size, self.device, self.compute_type)
        )

        # Initialize VAD with caller's endpointing setting
        self._vad = SileroVADProcessor(
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=self.endpointing_ms,
            speech_pad_ms=100,
        )

        self.is_connected = True
        logger.info(f"[OFFLINE_ASR] Connected (model={self.model_size}, "
                     f"endpointing={self.endpointing_ms}ms)")

    async def send_audio(self, audio_bytes: bytes):
        """Process an audio chunk through VAD and (when speech ends) Whisper."""
        if not self.is_connected or not self._vad:
            return

        # Convert incoming audio to float32 at 16kHz for VAD and Whisper
        audio_16k = self._convert_to_float32_16k(audio_bytes)
        if audio_16k is None or len(audio_16k) == 0:
            return

        # Feed to VAD
        # SileroVADProcessor.process_chunk() expects mulaw bytes, but we need
        # to handle linear16 input too. We'll do VAD on the float32 directly.
        was_speaking = self._is_speech_active
        is_speech, prob = self._run_vad(audio_16k)

        if is_speech:
            if not self._is_speech_active:
                # Speech just started
                self._is_speech_active = True
                self._speech_started_fired = False
                self._audio_buffer = []
                self._buffer_sample_count = 0
                logger.debug(f"[OFFLINE_ASR] Speech started (prob={prob:.2f})")

            # Fire on_speech_started on first detection
            if not self._speech_started_fired:
                self._speech_started_fired = True
                if self.on_speech_started:
                    await self.on_speech_started()

            # Accumulate audio
            self._audio_buffer.append(audio_16k)
            self._buffer_sample_count += len(audio_16k)

            # Force-transcribe if buffer exceeds max (30s)
            if self._buffer_sample_count >= self.MAX_BUFFER_SAMPLES:
                logger.info("[OFFLINE_ASR] Buffer cap reached, force-transcribing")
                await self._transcribe_buffer()

        else:
            if self._is_speech_active:
                # Speech just ended — transcribe the buffer
                self._is_speech_active = False

                if self._buffer_sample_count > 0:
                    # Include this final silence chunk for completeness
                    self._audio_buffer.append(audio_16k)
                    self._buffer_sample_count += len(audio_16k)
                    await self._transcribe_buffer()

    def _convert_to_float32_16k(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """Convert raw audio to float32 at 16kHz."""
        try:
            if self.encoding == "mulaw":
                # 8kHz mulaw → 16kHz float32 (reuse SileroVADProcessor utilities)
                linear = self._vad.mulaw_to_linear(audio_bytes)
                audio_16k = self._vad.resample_8k_to_16k(linear)
                return audio_16k

            elif self.encoding == "linear16":
                # 16kHz signed 16-bit PCM → float32
                if len(audio_bytes) < 2:
                    return None
                # Ensure even byte count
                if len(audio_bytes) % 2 != 0:
                    audio_bytes = audio_bytes[:len(audio_bytes) - 1]
                samples = np.frombuffer(audio_bytes, dtype=np.int16)
                return samples.astype(np.float32) / 32768.0

            else:
                logger.warning(f"[OFFLINE_ASR] Unsupported encoding: {self.encoding}")
                return None

        except Exception as e:
            logger.error(f"[OFFLINE_ASR] Audio conversion error: {e}")
            return None

    def _run_vad(self, audio_16k: np.ndarray):
        """Run VAD on float32 16kHz audio directly (bypassing mulaw conversion in SileroVADProcessor)."""
        import torch

        if not self._vad._ensure_model_loaded():
            return self._vad.is_speaking, 0.0

        # Buffer for VAD (expects 512-sample chunks at 16kHz)
        self._vad.audio_buffer.extend(audio_16k.tolist())
        chunk_size = 512
        speech_prob = 0.0
        ms_per_chunk = chunk_size / 16.0  # 32ms per 512-sample chunk at 16kHz

        # Process each 512-sample chunk and update state individually
        # so silence duration accumulates correctly for endpointing.
        while len(self._vad.audio_buffer) >= chunk_size:
            chunk = np.array(self._vad.audio_buffer[:chunk_size], dtype=np.float32)
            self._vad.audio_buffer = self._vad.audio_buffer[chunk_size:]
            audio_tensor = torch.from_numpy(chunk)
            speech_prob = self._vad.model(audio_tensor, self._vad.sample_rate).item()

            self._vad.current_time_ms += ms_per_chunk
            self._vad._update_state(speech_prob)

        return self._vad.is_speaking, speech_prob

    async def _transcribe_buffer(self):
        """Transcribe accumulated audio buffer with faster-whisper."""
        if self._transcribing or not self._audio_buffer:
            return

        self._transcribing = True

        try:
            # Concatenate all buffered chunks
            audio = np.concatenate(self._audio_buffer)
            self._audio_buffer = []
            self._buffer_sample_count = 0

            # Skip very short segments (< 200ms = 3200 samples at 16kHz)
            if len(audio) < 3200:
                logger.debug(f"[OFFLINE_ASR] Skipping short segment ({len(audio)} samples)")
                return

            # Transcribe in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            text, confidence = await loop.run_in_executor(
                self._executor,
                lambda: self._whisper_transcribe(audio)
            )

            if text and text.strip():
                self.current_transcript = text.strip()
                logger.info(f"[OFFLINE_ASR] Transcript: {self.current_transcript}")

                # Fire callbacks
                if self.on_confidence_update:
                    await self.on_confidence_update(confidence)

                if self.on_transcript:
                    await self.on_transcript(self.current_transcript, True)

                if self.on_utterance_end:
                    await self.on_utterance_end()
            else:
                logger.debug("[OFFLINE_ASR] Empty transcript, skipping")

        except Exception as e:
            logger.error(f"[OFFLINE_ASR] Transcription error: {e}", exc_info=True)
        finally:
            self._transcribing = False

    def _whisper_transcribe(self, audio: np.ndarray):
        """Run faster-whisper transcription (blocking, runs in thread)."""
        try:
            segments, info = self._model.transcribe(
                audio,
                language=self.language if self.language not in ("auto", "") else None,
                beam_size=1,
                best_of=1,
                vad_filter=False,  # We already did VAD
                without_timestamps=True,
            )

            # Collect all segment text
            segment_list = list(segments)
            text = " ".join(seg.text.strip() for seg in segment_list if seg.text.strip())

            # Compute average confidence from log probabilities
            if segment_list:
                avg_logprob = sum(seg.avg_logprob for seg in segment_list) / len(segment_list)
                confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
            else:
                confidence = 0.0

            return text, confidence

        except Exception as e:
            logger.error(f"[OFFLINE_ASR] Whisper error: {e}")
            return "", 0.0

    async def close(self):
        """Clean up resources."""
        self.is_connected = False

        # Transcribe any remaining buffer
        if self._audio_buffer and self._buffer_sample_count > 0:
            await self._transcribe_buffer()

        self._audio_buffer = []
        self._buffer_sample_count = 0

        if self._vad:
            self._vad.reset()

        self._executor.shutdown(wait=False)

        logger.info("[OFFLINE_ASR] Closed")
