"""
Voice Pipeline Utility Functions
Essential helper functions for WebSocket communication and audio processing
"""
import time
import json
import copy
import io
import base64
try:
    import audioop  # Python < 3.13
except ModuleNotFoundError:
    import audioop_lts as audioop  # Python 3.13+
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample as scipy_resample
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.constants import DEFAULT_LANGUAGE_CODE, PRE_FUNCTION_CALL_MESSAGE, TRANSFERING_CALL_FILLER

logger = configure_logger(__name__)


def create_ws_data_packet(data, meta_info=None, is_md5_hash=False, llm_generated=False):
    """Create WebSocket data packet with metadata"""
    metadata = copy.deepcopy(meta_info) if meta_info else {}
    if meta_info is not None:
        metadata["is_md5_hash"] = is_md5_hash
        metadata["llm_generated"] = llm_generated
    return {
        'data': data,
        'meta_info': metadata
    }


def timestamp_ms() -> float:
    """Get current timestamp in milliseconds"""
    return time.time() * 1000


def now_ms() -> float:
    """Get current time in milliseconds using perf_counter"""
    return time.perf_counter() * 1000


def convert_audio_to_wav(audio_bytes, source_format='flac'):
    """
    Simplified audio converter - for now just returns the audio bytes as-is
    In production, this would convert audio formats using pydub/AudioSegment
    """
    logger.info(f"Audio conversion requested from {source_format} to WAV")
    # For Twilio integration, we typically receive/send μ-law format directly
    # so we don't need complex conversion
    return audio_bytes


def resample(audio_bytes, target_sample_rate, format="mp3"):
    """
    Resample audio to target sample rate using scipy.
    Supports WAV format audio resampling for telephony.
    Falls back to original audio if resampling fails.

    Args:
        audio_bytes: Audio data as bytes (WAV format)
        target_sample_rate: Target sample rate (e.g., 8000 for telephony)
        format: Audio format (currently supports "wav", "mp3" returns as-is)

    Returns:
        Resampled audio bytes or original if format not WAV or resampling fails
    """
    logger.debug(f"Audio resampling requested to {target_sample_rate}Hz (format: {format})")

    # Only resample WAV format
    if format.lower() != "wav":
        logger.debug(f"Skipping resample for {format} format - returning original")
        return audio_bytes

    try:
        # Read WAV audio using scipy
        audio_buffer = io.BytesIO(audio_bytes)
        orig_sample_rate, audio_data = wavfile.read(audio_buffer)

        # Check if resampling is needed
        if orig_sample_rate == target_sample_rate:
            logger.debug(f"Audio already at {target_sample_rate}Hz, no resampling needed")
            return audio_bytes

        # Resample to target sample rate
        num_samples = int(len(audio_data) * target_sample_rate / orig_sample_rate)
        resampled_data = scipy_resample(audio_data, num_samples)

        # Convert back to int16 and clip values
        resampled_data = np.clip(resampled_data, -32768, 32767).astype(np.int16)

        # Save back as WAV
        output_buffer = io.BytesIO()
        wavfile.write(output_buffer, target_sample_rate, resampled_data)
        output_buffer.seek(0)
        resampled_bytes = output_buffer.read()

        logger.debug(f"Resampled audio from {orig_sample_rate}Hz to {target_sample_rate}Hz")
        return resampled_bytes

    except Exception as e:
        logger.warning(f"Error resampling audio: {e}. Returning original audio.")
        return audio_bytes


def wav_bytes_to_pcm(wav_bytes):
    """
    Convert WAV bytes to PCM (raw audio data).
    Extracts the audio data from WAV format by removing the header.

    Args:
        wav_bytes: WAV format audio bytes

    Returns:
        PCM audio bytes (raw audio data without header)
    """
    try:
        audio_buffer = io.BytesIO(wav_bytes)
        sample_rate, audio_data = wavfile.read(audio_buffer)

        # Convert to bytes
        pcm_bytes = audio_data.tobytes()
        logger.debug(f"Converted WAV to PCM: {len(wav_bytes)} → {len(pcm_bytes)} bytes")
        return pcm_bytes
    except Exception as e:
        logger.warning(f"Error converting WAV to PCM: {e}. Returning original data.")
        return wav_bytes


def pcm16_to_mulaw(pcm_bytes):
    """
    Convert 16-bit PCM audio bytes to μ-law (G.711) 8-bit encoding.
    Returns original audio if conversion fails.
    """
    try:
        return audioop.lin2ulaw(pcm_bytes, 2)
    except Exception as e:
        logger.warning(f"Error converting PCM to μ-law: {e}. Returning original PCM data.")
        return pcm_bytes


def convert_to_request_log(message, meta_info, model, component="transcriber", direction='response', is_cached=False, engine=None, run_id=None):
    """
    Create request log dictionary for tracking
    Simplified version - just returns basic structure
    """
    return {
        'message': message,
        'meta_info': meta_info,
        'model': model,
        'component': component,
        'direction': direction,
        'is_cached': is_cached,
        'engine': engine,
        'run_id': run_id,
        'timestamp': timestamp_ms()
    }


def compute_function_pre_call_message(language, function_name, api_tool_pre_call_message):
    """
    Get filler message to play while executing function call
    """
    default_filler = PRE_FUNCTION_CALL_MESSAGE.get(language, PRE_FUNCTION_CALL_MESSAGE.get(DEFAULT_LANGUAGE_CODE))
    if "transfer" in function_name.lower():
        default_filler = TRANSFERING_CALL_FILLER.get(language, TRANSFERING_CALL_FILLER.get(DEFAULT_LANGUAGE_CODE))
    return api_tool_pre_call_message or default_filler
