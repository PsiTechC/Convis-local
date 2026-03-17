"""
OpenAI Whisper Transcriber for Voice Pipeline
Note: OpenAI Whisper doesn't support WebSocket streaming like Deepgram.
This implementation buffers audio and uses VAD-like logic to detect speech segments.
"""
import asyncio
import time
import io
import wave
try:
    import audioop  # Python < 3.13
except ModuleNotFoundError:
    import audioop_lts as audioop  # Python 3.13+
from typing import Optional
from openai import AsyncOpenAI

from .base_transcriber import BaseTranscriber
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.helpers.utils import create_ws_data_packet, timestamp_ms

logger = configure_logger(__name__)


class OpenAITranscriber(BaseTranscriber):
    """
    OpenAI Whisper transcriber with audio buffering and VAD-like detection.
    Since OpenAI doesn't support streaming, we buffer audio and transcribe on silence detection.
    """

    def __init__(
        self,
        telephony_provider,
        input_queue=None,
        output_queue=None,
        model='whisper-1',
        language='en',
        endpointing='400',
        **kwargs
    ):
        super().__init__(input_queue)
        self.telephony_provider = telephony_provider
        self.model = model
        self.language = language
        self.endpointing = int(endpointing)  # Silence threshold in ms
        self.transcriber_output_queue = output_queue

        # API setup
        api_key = kwargs.get("transcriber_key")
        if not api_key:
            raise ValueError("OpenAI API key is required for OpenAI transcriber")
        self.client = AsyncOpenAI(api_key=api_key)

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
            self.sample_width = 1  # μ-law is 1 byte per sample
        else:
            # Default to linear16 16kHz
            self.sample_rate = 16000
            self.encoding = 'linear16'
            self.channels = 1
            self.sample_width = 2

        # VAD parameters
        self.silence_threshold = 500  # Amplitude threshold for silence detection
        self.min_audio_length = 0.5  # Minimum 0.5 seconds of audio to transcribe

        self.transcription_task = None
        self.running = False

        logger.info(
            f"[OPENAI_TRANSCRIBER] Initialized with model={model}, "
            f"language={language}, endpointing={endpointing}ms"
        )

    def _is_silence(self, audio_chunk: bytes) -> bool:
        """
        Simple VAD: Check if audio chunk is silence based on amplitude.

        Args:
            audio_chunk: Raw audio bytes

        Returns:
            True if chunk is considered silence
        """
        try:
            # Convert μ-law to linear16 for RMS calculation if needed
            if self.encoding == 'mulaw':
                audio_chunk = audioop.ulaw2lin(audio_chunk, 2)
                sample_width = 2
            else:
                sample_width = self.sample_width

            # Calculate RMS (Root Mean Square) to detect silence
            rms = audioop.rms(audio_chunk, sample_width)
            return rms < self.silence_threshold

        except Exception as e:
            logger.error(f"[OPENAI_TRANSCRIBER] Error in VAD: {e}")
            return False

    def _buffer_to_wav(self) -> bytes:
        """
        Convert audio buffer to WAV format for OpenAI Whisper API.

        Returns:
            WAV file bytes
        """
        try:
            # Concatenate all buffered audio chunks
            audio_data = b''.join(self.audio_buffer)

            # Convert μ-law to linear16 if needed
            if self.encoding == 'mulaw':
                audio_data = audioop.ulaw2lin(audio_data, 2)
                sample_width = 2
            else:
                sample_width = self.sample_width

            # Create WAV file in memory
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_data)

            wav_buffer.seek(0)
            return wav_buffer.read()

        except Exception as e:
            logger.error(f"[OPENAI_TRANSCRIBER] Error converting buffer to WAV: {e}")
            raise

    async def _transcribe_buffer(self):
        """
        Transcribe the current audio buffer using OpenAI Whisper API.
        """
        if not self.audio_buffer:
            logger.warning("[OPENAI_TRANSCRIBER] No audio in buffer to transcribe")
            return

        # Calculate audio duration
        total_bytes = sum(len(chunk) for chunk in self.audio_buffer)
        bytes_per_second = self.sample_rate * self.sample_width
        duration = total_bytes / bytes_per_second

        # Skip if audio is too short
        if duration < self.min_audio_length:
            logger.info(f"[OPENAI_TRANSCRIBER] Audio too short ({duration:.2f}s), skipping")
            self.audio_buffer.clear()
            return

        try:
            logger.info(f"[OPENAI_TRANSCRIBER] Transcribing {duration:.2f}s of audio...")

            # Convert buffer to WAV
            start_time = timestamp_ms()
            wav_data = self._buffer_to_wav()

            # Create file-like object for API
            audio_file = io.BytesIO(wav_data)
            audio_file.name = "audio.wav"

            # Call OpenAI Whisper API
            response = await self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                language=self.language if self.language != 'en' else None,  # None for auto-detect
                response_format='verbose_json'
            )

            transcript = response.text.strip()
            elapsed = timestamp_ms() - start_time

            if transcript:
                logger.info(f"[OPENAI_TRANSCRIBER] ✅ Transcript: {transcript}")
                logger.info(f"[OPENAI_TRANSCRIBER] Transcription latency: {elapsed}ms")

                # Build data packet
                data = {
                    "type": "transcript",
                    "content": transcript
                }

                # Update meta info
                if self.meta_info:
                    self.meta_info['transcriber_latency'] = elapsed
                    self.meta_info['audio_duration'] = duration
                    self.meta_info['transcriber_first_result_latency'] = elapsed
                    self.meta_info['transcriber_total_stream_duration'] = elapsed

                # Send to output queue
                await self.transcriber_output_queue.put(
                    create_ws_data_packet(data, self.meta_info)
                )

                # Track turn latencies
                self.turn_latencies.append({
                    'turn_id': self.current_turn_id,
                    'sequence_id': self.current_turn_id,
                    'latency_ms': elapsed,
                    'audio_duration': duration
                })
            else:
                logger.info("[OPENAI_TRANSCRIBER] Empty transcript received")

        except Exception as e:
            logger.error(f"[OPENAI_TRANSCRIBER] Transcription error: {e}", exc_info=True)

        finally:
            # Clear buffer after transcription attempt
            self.audio_buffer.clear()

    async def _process_audio_stream(self):
        """
        Main loop: Process incoming audio chunks and detect speech/silence.
        """
        try:
            logger.info("[OPENAI_TRANSCRIBER] Starting audio processing loop")

            while self.running:
                try:
                    # Get audio from input queue (with timeout to allow checking running flag)
                    ws_data_packet = await asyncio.wait_for(
                        self.input_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    # Check if we have buffered audio waiting for silence timeout
                    if self.is_speaking and self.silence_start:
                        silence_duration = (time.time() - self.silence_start) * 1000
                        if silence_duration > self.endpointing:
                            logger.info(f"[OPENAI_TRANSCRIBER] Silence detected ({silence_duration:.0f}ms)")
                            self.is_speaking = False
                            await self._transcribe_buffer()
                            self.silence_start = None
                    continue

                # Extract meta info and audio data
                self.meta_info = ws_data_packet.get('meta_info', {})
                audio_chunk = ws_data_packet.get('data')

                if not audio_chunk:
                    continue

                # Initialize turn tracking
                if not self.meta_info.get('request_id'):
                    self.current_request_id = self.generate_request_id()
                    self.meta_info['request_id'] = self.current_request_id

                self.last_audio_time = time.time()

                # VAD: Check if chunk contains speech
                is_silence = self._is_silence(audio_chunk)

                if not is_silence:
                    # Speech detected
                    if not self.is_speaking:
                        # Start of new speech turn
                        self.is_speaking = True
                        self.turn_counter += 1
                        self.current_turn_id = self.turn_counter
                        self.silence_start = None
                        logger.info(f"[OPENAI_TRANSCRIBER] 🎤 Speech started (turn {self.current_turn_id})")

                        # Send speech_started event
                        data = {"type": "speech_started"}
                        await self.transcriber_output_queue.put(
                            create_ws_data_packet(data, self.meta_info)
                        )

                    # Add to buffer
                    self.audio_buffer.append(audio_chunk)
                    self.silence_start = None  # Reset silence timer

                else:
                    # Silence detected
                    if self.is_speaking:
                        if not self.silence_start:
                            self.silence_start = time.time()

                        # Still add to buffer (captures trailing silence)
                        self.audio_buffer.append(audio_chunk)

                        # Check if silence exceeded endpointing threshold
                        silence_duration = (time.time() - self.silence_start) * 1000
                        if silence_duration > self.endpointing:
                            logger.info(f"[OPENAI_TRANSCRIBER] Silence detected ({silence_duration:.0f}ms)")
                            self.is_speaking = False
                            await self._transcribe_buffer()
                            self.silence_start = None

            logger.info("[OPENAI_TRANSCRIBER] Audio processing loop stopped")

        except asyncio.CancelledError:
            logger.info("[OPENAI_TRANSCRIBER] Audio processing cancelled")
            raise
        except Exception as e:
            logger.error(f"[OPENAI_TRANSCRIBER] Error in audio processing: {e}", exc_info=True)
        finally:
            # Transcribe any remaining buffered audio
            if self.audio_buffer:
                logger.info("[OPENAI_TRANSCRIBER] Transcribing remaining buffered audio...")
                await self._transcribe_buffer()

    async def run(self):
        """Start the transcriber"""
        try:
            self.running = True
            self.transcription_task = asyncio.create_task(self._process_audio_stream())
            logger.info("[OPENAI_TRANSCRIBER] ✅ Transcriber started")
        except Exception as e:
            logger.error(f"[OPENAI_TRANSCRIBER] Failed to start: {e}", exc_info=True)
            raise

    async def toggle_connection(self):
        """Stop the transcriber"""
        logger.info("[OPENAI_TRANSCRIBER] Stopping transcriber...")
        self.running = False

        if self.transcription_task:
            self.transcription_task.cancel()
            try:
                await self.transcription_task
            except asyncio.CancelledError:
                pass

        # Send connection closed event
        if self.transcriber_output_queue:
            await self.transcriber_output_queue.put(
                create_ws_data_packet("transcriber_connection_closed", self.meta_info or {})
            )

        logger.info("[OPENAI_TRANSCRIBER] ✅ Transcriber stopped")

    async def transcribe(self):
        """
        Main transcribe method (called by base class pattern).
        Delegates to run() for consistency with other transcribers.
        """
        await self.run()
