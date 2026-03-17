"""
Local faster-whisper Transcriber for Voice Pipeline
Uses the faster-whisper-server (OpenAI-compatible API) running locally or on a remote server.
Buffers audio and uses VAD-like logic to detect speech segments, then sends to local whisper.
"""
import asyncio
import time
import io
import wave
import os
try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop
from typing import Optional
import aiohttp

from .base_transcriber import BaseTranscriber
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.helpers.utils import create_ws_data_packet, timestamp_ms

logger = configure_logger(__name__)


class WhisperLocalTranscriber(BaseTranscriber):
    """
    Local faster-whisper transcriber with audio buffering and VAD-like detection.
    Sends buffered audio to a local faster-whisper-server (OpenAI-compatible /v1/audio/transcriptions).
    """

    def __init__(
        self,
        telephony_provider,
        input_queue=None,
        output_queue=None,
        model='medium',
        language='en',
        endpointing='400',
        **kwargs
    ):
        super().__init__(input_queue)
        self.telephony_provider = telephony_provider
        self.model = model
        self.language = language
        self.endpointing = int(endpointing)
        self.transcriber_output_queue = output_queue

        # Whisper server URL
        self.whisper_url = kwargs.get("transcriber_key") or os.getenv("WHISPER_API_URL", "http://localhost:8080")
        # Ensure it ends with the transcription endpoint
        if not self.whisper_url.endswith("/v1/audio/transcriptions"):
            self.whisper_url = self.whisper_url.rstrip("/") + "/v1/audio/transcriptions"

        logger.info(f"[WHISPER_LOCAL] Initialized with URL: {self.whisper_url}, model: {self.model}")

        # Audio buffering
        self.audio_buffer = []
        self.is_speaking = False
        self.last_audio_time = None
        self.silence_start = None
        self.current_turn_id = None
        self.turn_counter = 0

        # Audio format (Twilio μ-law 8kHz)
        if telephony_provider == 'twilio':
            self.sample_rate = 8000
            self.encoding = 'mulaw'
            self.channels = 1
            self.sample_width = 1
        else:
            self.sample_rate = 16000
            self.encoding = 'linear16'
            self.channels = 1
            self.sample_width = 2

        # VAD parameters
        self.silence_threshold = 500
        self.min_audio_length = 0.5

        self.transcription_task = None
        self.running = False

        # Noise suppression
        self.noise_suppression_level = kwargs.get("noise_suppression_level", "medium")

        # Meta info
        self.meta_info = {
            'request_id': None,
            'previous_request_id': None,
            'origin': 'transcriber',
            'is_final': False,
            'turn_id': None
        }

    async def run(self, ws=None):
        """Main loop: read audio from input queue, detect speech, transcribe on silence"""
        self.running = True
        logger.info("[WHISPER_LOCAL] Starting transcription loop")

        while self.running:
            try:
                audio_data = await asyncio.wait_for(self.input_queue.get(), timeout=0.1)

                if isinstance(audio_data, dict) and audio_data.get('event') == 'stop':
                    logger.info("[WHISPER_LOCAL] Received stop event")
                    break

                if isinstance(audio_data, dict) and 'data' in audio_data:
                    audio_bytes = audio_data['data']
                else:
                    audio_bytes = audio_data

                if not isinstance(audio_bytes, bytes):
                    continue

                current_time = time.time()
                self.last_audio_time = current_time

                # Simple VAD: check audio energy
                if self.encoding == 'mulaw':
                    pcm_data = audioop.ulaw2lin(audio_bytes, 2)
                else:
                    pcm_data = audio_bytes

                rms = audioop.rms(pcm_data, 2)

                if rms > self.silence_threshold:
                    # Speech detected
                    if not self.is_speaking:
                        self.is_speaking = True
                        self.turn_counter += 1
                        self.current_turn_id = f"turn_{self.turn_counter}"
                        self.current_request_id = self.generate_request_id()
                        self.meta_info['turn_id'] = self.current_turn_id
                        self.meta_info['request_id'] = self.current_request_id
                        logger.info(f"[WHISPER_LOCAL] Speech started (turn: {self.current_turn_id})")

                    self.silence_start = None
                    self.audio_buffer.append(audio_bytes)
                else:
                    # Silence detected
                    if self.is_speaking:
                        self.audio_buffer.append(audio_bytes)

                        if self.silence_start is None:
                            self.silence_start = current_time
                        elif (current_time - self.silence_start) * 1000 > self.endpointing:
                            # Silence exceeded threshold - transcribe buffered audio
                            audio_duration = len(self.audio_buffer) * (len(audio_bytes) / self.sample_rate)
                            if audio_duration >= self.min_audio_length:
                                await self._transcribe_buffer()
                            else:
                                logger.debug("[WHISPER_LOCAL] Audio too short, skipping")

                            self.audio_buffer = []
                            self.is_speaking = False
                            self.silence_start = None

            except asyncio.TimeoutError:
                # Check if there's buffered audio during extended silence
                if self.is_speaking and self.silence_start and self.audio_buffer:
                    silence_duration = (time.time() - self.silence_start) * 1000
                    if silence_duration > self.endpointing:
                        await self._transcribe_buffer()
                        self.audio_buffer = []
                        self.is_speaking = False
                        self.silence_start = None
                continue
            except Exception as e:
                logger.error(f"[WHISPER_LOCAL] Error in transcription loop: {e}", exc_info=True)
                continue

        logger.info("[WHISPER_LOCAL] Transcription loop ended")

    async def _transcribe_buffer(self):
        """Send buffered audio to local faster-whisper server"""
        if not self.audio_buffer:
            return

        try:
            # Combine audio chunks
            combined_audio = b''.join(self.audio_buffer)

            # Convert μ-law to PCM if needed
            if self.encoding == 'mulaw':
                pcm_data = audioop.ulaw2lin(combined_audio, 2)
            else:
                pcm_data = combined_audio

            # Create WAV file in memory
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16-bit PCM
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(pcm_data)
            wav_buffer.seek(0)

            # Send to faster-whisper server
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field('file', wav_buffer, filename='audio.wav', content_type='audio/wav')
                form_data.add_field('model', self.model)
                form_data.add_field('language', self.language)

                async with session.post(self.whisper_url, data=form_data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('text', '').strip()

                        if text:
                            logger.info(f"[WHISPER_LOCAL] Transcribed: '{text}'")
                            self.meta_info['is_final'] = True
                            self.update_meta_info()

                            # Send transcription to output queue
                            message = create_ws_data_packet(
                                data=text,
                                meta_info=self.meta_info.copy()
                            )
                            await self.transcriber_output_queue.put(message)

                            # Update request IDs
                            self.previous_request_id = self.current_request_id
                            self.current_request_id = self.generate_request_id()
                            self.meta_info['request_id'] = self.current_request_id
                    else:
                        error_text = await response.text()
                        logger.error(f"[WHISPER_LOCAL] Transcription failed: {response.status} - {error_text}")

        except asyncio.TimeoutError:
            logger.error("[WHISPER_LOCAL] Transcription request timed out")
        except Exception as e:
            logger.error(f"[WHISPER_LOCAL] Error transcribing: {e}", exc_info=True)

    async def cleanup(self):
        """Clean up resources"""
        self.running = False
        logger.info("[WHISPER_LOCAL] Cleaned up")
