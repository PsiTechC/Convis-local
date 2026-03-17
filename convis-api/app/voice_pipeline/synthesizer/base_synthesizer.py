import io
from app.voice_pipeline.helpers.logger_config import configure_logger
import asyncio
import re
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample as scipy_resample

logger = configure_logger(__name__)


class BaseSynthesizer:
    def __init__(self, task_manager_instance=None, stream=True, buffer_size=40, event_loop=None):
        self.stream = stream
        self.buffer_size = buffer_size
        self.internal_queue = asyncio.Queue()
        self.task_manager_instance = task_manager_instance
        self.connection_time = None
        self.turn_latencies = []

    def clear_internal_queue(self):
        logger.info(f"Clearing out internal queue")
        self.internal_queue = asyncio.Queue()

    def should_synthesize_response(self, sequence_id):
        return self.task_manager_instance.is_sequence_id_in_current_ids(sequence_id)

    async def flush_synthesizer_stream(self):
        pass

    def generate(self):
        pass

    def push(self, text):
        pass
    
    def synthesize(self, text):
        pass

    def get_synthesized_characters(self):
        return 0

    async def monitor_connection(self):
        pass

    async def cleanup(self):
        pass

    async def handle_interruption(self):
        pass

    def text_chunker(self, text):
        """
        Split text into natural phrase chunks for human-like speech.
        Splits at sentence and clause boundaries for natural flow with minimal latency.
        """
        # Natural pause points: sentences > clauses > long phrases
        strong_breaks = (".", "!", "?")  # Sentence endings
        soft_breaks = (",", ";", ":")     # Clause breaks
        
        buffer = ""
        for char in text:
            buffer += char
            
            # Strong break: sentence ending
            if char in strong_breaks:
                stripped = buffer.strip()
                if len(stripped) > 2:
                    yield stripped + " "
                    buffer = ""
            # Soft break: clause ending (only if buffer is getting long)
            elif char in soft_breaks and len(buffer) > 30:
                stripped = buffer.strip()
                if len(stripped) > 10:
                    yield stripped + " "
                    buffer = ""
        
        # Yield any remaining text
        if buffer.strip():
            yield buffer.strip() + " "

    def normalize_text(self, s):
        return re.sub(r'\s+', ' ', s.strip())

    def resample(self, audio_bytes):
        """
        Resample audio to 8kHz for telephony using scipy.
        Falls back to original audio if resampling fails.
        """
        try:
            # Read WAV audio using scipy
            audio_buffer = io.BytesIO(audio_bytes)
            orig_sample_rate, audio_data = wavfile.read(audio_buffer)

            # Check if resampling is needed
            if orig_sample_rate == 8000:
                logger.debug("Audio already at 8kHz, no resampling needed")
                return audio_bytes

            # Resample to 8000 Hz
            target_sample_rate = 8000
            num_samples = int(len(audio_data) * target_sample_rate / orig_sample_rate)
            resampled_data = scipy_resample(audio_data, num_samples)

            # Convert back to int16 and clip values
            resampled_data = np.clip(resampled_data, -32768, 32767).astype(np.int16)

            # Save back as WAV
            output_buffer = io.BytesIO()
            wavfile.write(output_buffer, target_sample_rate, resampled_data)
            output_buffer.seek(0)
            audio_data = output_buffer.read()

            logger.debug(f"Resampled audio from {orig_sample_rate}Hz to 8kHz")
            return audio_data

        except Exception as e:
            logger.warning(f"Error resampling audio: {e}. Returning original audio.")
            return audio_bytes

    def get_engine(self):
        return "default"

    def supports_websocket(self):
        return True
