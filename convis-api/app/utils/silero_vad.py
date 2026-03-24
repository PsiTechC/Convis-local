"""
Silero VAD (Voice Activity Detection) Utility
Detects speech segments in audio for custom provider pipeline.
CPU-only, lightweight (~2MB model), fast inference.

IMPORTANT: Model loading is LAZY to avoid blocking Cloud Run startup.
The model is only loaded when the first call comes in.
"""
import logging
import os
import numpy as np
from typing import Tuple, Optional
import struct
import threading

logger = logging.getLogger(__name__)

# Global model instance (loaded once, lazily)
_vad_model = None
_vad_utils = None
_vad_lock = threading.Lock()
_vad_loading = False


def load_silero_vad():
    """
    Load Silero VAD model (singleton pattern with lazy loading).
    Uses ONNX runtime for faster CPU inference.

    This function is thread-safe and loads the model only once.
    """
    global _vad_model, _vad_utils, _vad_loading

    # Fast path: model already loaded
    if _vad_model is not None:
        return _vad_model, _vad_utils

    with _vad_lock:
        # Double-check after acquiring lock
        if _vad_model is not None:
            return _vad_model, _vad_utils

        if _vad_loading:
            logger.warning("[SILERO_VAD] Model is already being loaded by another thread")
            return None, None

        _vad_loading = True

    try:
        logger.info("[SILERO_VAD] Loading model (this may take a few seconds on first call)...")
        import torch
        torch.set_num_threads(1)  # Optimize for single-threaded inference

        # Try local cache first, then download
        local_vad_path = '/root/.cache/torch/hub/snakers4_silero-vad_master'
        if os.path.exists(os.path.join(local_vad_path, 'hubconf.py')):
            model, utils = torch.hub.load(
                repo_or_dir=local_vad_path,
                model='silero_vad',
                source='local',
                onnx=False
            )
        else:
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )

        with _vad_lock:
            _vad_model = model
            _vad_utils = utils
            _vad_loading = False

        logger.info("[SILERO_VAD] Model loaded successfully (ONNX mode)")
        return model, utils

    except Exception as e:
        with _vad_lock:
            _vad_loading = False
        logger.error(f"[SILERO_VAD] Failed to load model: {e}")
        raise


class SileroVADProcessor:
    """
    Real-time VAD processor for streaming audio.
    Designed for Twilio's mulaw 8kHz audio format.

    Model loading is LAZY - it only happens on first process_chunk() call,
    not during __init__(). This prevents blocking Cloud Run startup.
    """

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 300,
        speech_pad_ms: int = 100
    ):
        """
        Initialize VAD processor.

        Args:
            threshold: Speech probability threshold (0.0-1.0). Higher = stricter.
            min_speech_duration_ms: Minimum speech segment length to consider valid.
            min_silence_duration_ms: Silence duration to mark end of speech.
            speech_pad_ms: Padding around speech segments.
        """
        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.speech_pad_ms = speech_pad_ms

        # Model is loaded LAZILY on first use (not here!)
        # This prevents blocking Cloud Run startup
        self.model = None
        self.utils = None
        self._model_loaded = False

        # State tracking
        self.is_speaking = False
        self.speech_start_ms = 0
        self.silence_start_ms = 0
        self.current_time_ms = 0

        # Audio buffer for resampling (Twilio sends 8kHz, Silero needs 16kHz)
        self.audio_buffer = []
        self.sample_rate = 16000  # Silero expects 16kHz

        logger.info(f"[SILERO_VAD] Processor initialized (model will load on first use): "
                   f"threshold={threshold}, min_speech={min_speech_duration_ms}ms, "
                   f"min_silence={min_silence_duration_ms}ms")

    def _ensure_model_loaded(self) -> bool:
        """
        Ensure the model is loaded. Returns True if model is ready.
        This is called lazily on first process_chunk().
        """
        if self._model_loaded:
            return True

        try:
            self.model, self.utils = load_silero_vad()
            if self.model is not None:
                self._model_loaded = True
                return True
            return False
        except Exception as e:
            logger.error(f"[SILERO_VAD] Failed to load model on demand: {e}")
            return False

    def reset(self):
        """Reset VAD state for new call."""
        self.is_speaking = False
        self.speech_start_ms = 0
        self.silence_start_ms = 0
        self.current_time_ms = 0
        self.audio_buffer = []
        if self.model is not None:
            self.model.reset_states()
        logger.debug("[SILERO_VAD] State reset")

    def mulaw_to_linear(self, mulaw_data: bytes) -> np.ndarray:
        """
        Convert mulaw (G.711) audio to linear PCM.
        Twilio sends 8-bit mulaw at 8kHz.
        Uses ITU G.711 standard decoding.
        """
        # Mulaw decoding lookup table (ITU G.711 standard)
        # This is more accurate than manual calculation
        MULAW_BIAS = 0x84
        MULAW_CLIP = 32635

        samples = []
        for byte in mulaw_data:
            # Invert all bits (mulaw is transmitted inverted)
            byte = ~byte & 0xFF

            # Extract sign, exponent, and mantissa
            sign = byte & 0x80
            exponent = (byte >> 4) & 0x07
            mantissa = byte & 0x0F

            # Decode according to G.711 standard
            # sample = (mantissa << (exponent + 3)) + (MULAW_BIAS << (exponent + 3)) - MULAW_BIAS
            sample = ((mantissa << 3) + MULAW_BIAS) << exponent
            sample = sample - MULAW_BIAS

            if sign:
                sample = -sample

            # Normalize to [-1, 1] range
            samples.append(sample / 32768.0)

        return np.array(samples, dtype=np.float32)

    def resample_8k_to_16k(self, audio_8k: np.ndarray) -> np.ndarray:
        """
        Resample 8kHz audio to 16kHz using linear interpolation.
        Simple but effective for voice.
        """
        # Double the sample rate via linear interpolation
        n = len(audio_8k)
        x_old = np.arange(n)
        x_new = np.linspace(0, n - 1, n * 2)
        return np.interp(x_new, x_old, audio_8k).astype(np.float32)

    def process_chunk(self, mulaw_audio: bytes) -> Tuple[bool, float]:
        """
        Process audio chunk and detect speech.

        Args:
            mulaw_audio: Raw mulaw audio bytes from Twilio

        Returns:
            Tuple of (is_speech, probability)
        """
        # Lazy load model on first call
        if not self._ensure_model_loaded():
            # Model not available, return current state
            logger.warning("[SILERO_VAD] Model not loaded, skipping VAD processing")
            return self.is_speaking, 0.0

        import torch

        # Convert mulaw to linear PCM
        linear_audio = self.mulaw_to_linear(mulaw_audio)

        # Resample 8kHz to 16kHz
        audio_16k = self.resample_8k_to_16k(linear_audio)

        # Add to buffer
        self.audio_buffer.extend(audio_16k.tolist())

        # Silero VAD expects 512 samples at 16kHz (32ms chunks)
        chunk_size = 512

        if len(self.audio_buffer) < chunk_size:
            return self.is_speaking, 0.0

        # Process available chunks
        speech_prob = 0.0
        while len(self.audio_buffer) >= chunk_size:
            chunk = np.array(self.audio_buffer[:chunk_size], dtype=np.float32)
            self.audio_buffer = self.audio_buffer[chunk_size:]

            # Convert to tensor
            audio_tensor = torch.from_numpy(chunk)

            # Get speech probability
            speech_prob = self.model(audio_tensor, self.sample_rate).item()

        # Update time (approximate based on processed audio)
        chunk_duration_ms = (len(mulaw_audio) / 8) # 8 samples per ms at 8kHz
        self.current_time_ms += chunk_duration_ms

        return self._update_state(speech_prob)

    def _update_state(self, speech_prob: float) -> Tuple[bool, float]:
        """
        Update VAD state based on speech probability.

        Returns:
            Tuple of (is_speech, probability)
        """
        is_speech = speech_prob >= self.threshold

        if is_speech:
            if not self.is_speaking:
                # Speech started
                self.speech_start_ms = self.current_time_ms
                self.is_speaking = True
                logger.debug(f"[SILERO_VAD] Speech started at {self.current_time_ms}ms (prob={speech_prob:.2f})")
            self.silence_start_ms = 0
        else:
            if self.is_speaking:
                if self.silence_start_ms == 0:
                    # Silence started
                    self.silence_start_ms = self.current_time_ms
                else:
                    # Check if silence duration exceeded threshold
                    silence_duration = self.current_time_ms - self.silence_start_ms
                    if silence_duration >= self.min_silence_duration_ms:
                        # Check if speech was long enough
                        speech_duration = self.silence_start_ms - self.speech_start_ms
                        if speech_duration >= self.min_speech_duration_ms:
                            logger.debug(f"[SILERO_VAD] Speech ended at {self.current_time_ms}ms "
                                       f"(duration={speech_duration}ms, prob={speech_prob:.2f})")
                        self.is_speaking = False
                        self.silence_start_ms = 0

        return is_speech, speech_prob

    def is_speech_ended(self) -> bool:
        """
        Check if a valid speech segment has ended.
        Call this after process_chunk() to determine if it's time to process.
        """
        if self.is_speaking:
            return False

        # Check if we had valid speech that ended
        if self.silence_start_ms > 0:
            speech_duration = self.silence_start_ms - self.speech_start_ms
            return speech_duration >= self.min_speech_duration_ms

        return False

    def get_speech_duration_ms(self) -> int:
        """Get duration of the last speech segment in milliseconds."""
        if self.silence_start_ms > 0 and self.speech_start_ms > 0:
            return int(self.silence_start_ms - self.speech_start_ms)
        return 0


# Convenience function for one-shot speech detection
def detect_speech_in_audio(audio_data: bytes, sample_rate: int = 8000) -> bool:
    """
    Simple one-shot speech detection for an audio buffer.

    Args:
        audio_data: Raw audio bytes
        sample_rate: Sample rate of audio (default 8kHz for Twilio)

    Returns:
        True if speech detected, False otherwise
    """
    processor = SileroVADProcessor(threshold=0.5)
    is_speech, prob = processor.process_chunk(audio_data)
    return is_speech
