"""
Google Cloud Speech-to-Text Transcriber for Convis
Adapted from Bolna architecture
Uses threading to bridge async input_queue with blocking gRPC streaming
"""
import os
import time
import asyncio
import threading
import queue
import json

try:
    from google.cloud import speech_v1p1beta1 as speech
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    speech = None

from .base_transcriber import BaseTranscriber
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.helpers.utils import create_ws_data_packet

logger = configure_logger(__name__)


class GoogleTranscriber(BaseTranscriber):
    """
    Streaming transcriber using Google Cloud Speech-to-Text.
    Uses threading to bridge async input_queue with blocking gRPC streaming.
    """

    def __init__(
        self,
        telephony_provider,
        input_queue=None,
        output_queue=None,
        language="en-US",
        model="latest_long",
        endpointing="400",
        transcriber_key=None,
        **kwargs,
    ):
        super().__init__(input_queue)

        if not GOOGLE_AVAILABLE:
            raise ImportError(
                "Google Cloud Speech library not installed. "
                "Install with: pip install google-cloud-speech"
            )

        self.telephony_provider = telephony_provider
        self.transcriber_output_queue = output_queue
        self.language = language
        self.model = model
        self.endpointing = endpointing

        # Provider-specific audio configuration
        if telephony_provider == "twilio":
            self.encoding = "MULAW"
            self.sample_rate_hertz = 8000
        elif telephony_provider == "plivo":
            self.encoding = "LINEAR16"
            self.sample_rate_hertz = 8000
        else:
            self.encoding = "LINEAR16"
            self.sample_rate_hertz = 16000

        # Google client uses Application Default Credentials or GOOGLE_APPLICATION_CREDENTIALS env var
        try:
            self.client = speech.SpeechClient()
        except Exception as e:
            logger.error(f"[GOOGLE] Failed to create SpeechClient: {e}")
            logger.info("[GOOGLE] Make sure GOOGLE_APPLICATION_CREDENTIALS environment variable is set")
            raise

        # Threading bridge for gRPC streaming
        self._audio_q = queue.Queue()
        self._running = False
        self._grpc_thread = None

        # Connection state management
        self.connection_start_time = None
        self.connection_time = None
        self.websocket_connection = None
        self.connection_authenticated = False
        self.transcription_task = None

        # Audio frame tracking
        self.audio_frame_duration = 0.2
        self.num_frames = 0

        # Request tracking
        self.meta_info = {}
        self._request_id = None
        self.audio_submitted = False
        self.audio_submission_time = None

        # Turn latency tracking
        self.turn_latencies = []
        self.current_turn_start_time = None
        self.current_turn_id = None

        # Event loop reference for thread-safe queue operations
        try:
            self.loop = asyncio.get_event_loop()
        except Exception:
            self.loop = None

    def _enqueue_output(self, data, meta=None):
        """Thread-safe enqueue to transcriber_output_queue"""
        if self.transcriber_output_queue is None:
            return

        packet = create_ws_data_packet(data, meta or self.meta_info or {})

        # Thread-safe asyncio queue operation
        try:
            if self.loop and isinstance(self.transcriber_output_queue, asyncio.Queue):
                future = asyncio.run_coroutine_threadsafe(
                    self.transcriber_output_queue.put(packet), self.loop
                )
                try:
                    future.result(timeout=2.0)
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Fallback to sync operations
        try:
            if hasattr(self.transcriber_output_queue, "put_nowait"):
                self.transcriber_output_queue.put_nowait(packet)
            elif hasattr(self.transcriber_output_queue, "put"):
                self.transcriber_output_queue.put(packet)
        except Exception as e:
            logger.error(f"[GOOGLE] Failed to enqueue packet: {e}")

    async def google_connect(self):
        """Validate Google Speech client connection"""
        try:
            start_time = time.perf_counter()
            _ = self.client
            self.connection_authenticated = True

            if not self.connection_time:
                self.connection_time = round((time.perf_counter() - start_time) * 1000)

            logger.info("[GOOGLE] Successfully validated Speech client")
            return True

        except Exception as e:
            logger.error(f"[GOOGLE] Failed to validate Speech client: {e}")
            raise ConnectionError(f"Failed to validate Google Speech client: {e}")

    async def run(self):
        """Enhanced startup sequence"""
        try:
            # Connection validation
            await self.google_connect()

            self._running = True

            # Create transcription task
            self.transcription_task = asyncio.create_task(self._transcribe_wrapper())

        except Exception as e:
            logger.error(f"[GOOGLE] Error starting transcriber: {e}", exc_info=True)
            await self.toggle_connection()

    async def _transcribe_wrapper(self):
        """Wrapper to make gRPC streaming fit async pattern"""
        try:
            # Spawn the blocking gRPC consumer in a background thread
            self._grpc_thread = threading.Thread(target=self._run_grpc_stream, daemon=True)
            self._grpc_thread.start()

            # Spawn async sender to read from input_queue
            await self._send_audio_to_transcriber()

        except Exception as e:
            logger.error(f"[GOOGLE] Error in transcription wrapper: {e}", exc_info=True)
            await self.toggle_connection()
        finally:
            # Ensure cleanup
            if hasattr(self, 'transcription_task') and self.transcription_task:
                try:
                    self.transcription_task.cancel()
                except Exception:
                    pass

    async def _send_audio_to_transcriber(self):
        """Reads packets from input_queue and forwards to gRPC thread via _audio_q"""
        try:
            while True:
                ws_data_packet = await self.input_queue.get()

                # Initialize metadata on first audio packet
                if not self.audio_submitted:
                    self.audio_submitted = True
                    self.audio_submission_time = time.time()
                    self._request_id = self.generate_request_id()
                    self.meta_info = ws_data_packet.get('meta_info', {}) or {}
                    self.meta_info['request_id'] = self._request_id
                    self.meta_info['transcriber_start_time'] = time.perf_counter()
                    self.current_turn_start_time = self.meta_info['transcriber_start_time']
                    self.current_turn_id = self.meta_info.get('turn_id') or self._request_id

                # Check EOS
                if ws_data_packet.get('meta_info', {}).get('eos') is True:
                    # Put sentinel so blocking generator ends gracefully
                    self._audio_q.put(None)
                    break

                # Get raw audio bytes from packet and track frames
                data = ws_data_packet.get('data')
                if data:
                    self.num_frames += 1
                    # If data is base64 string, decode if needed
                    if isinstance(data, str):
                        try:
                            import base64
                            d = base64.b64decode(data)
                            self._audio_q.put(d)
                        except Exception:
                            # Fallback: push raw str bytes
                            self._audio_q.put(data.encode('utf-8'))
                    else:
                        # Assume bytes-like
                        self._audio_q.put(data)

        except Exception as e:
            logger.error(f"[GOOGLE] Error in _send_audio_to_transcriber: {e}", exc_info=True)

    def _audio_generator(self):
        """
        Blocking generator consumed by google client.streaming_recognize.
        Yields StreamingRecognizeRequest(audio_content=...).
        """
        while True:
            chunk = self._audio_q.get()
            if chunk is None:
                # Sentinel: end of stream
                return
            # Ensure bytes
            if isinstance(chunk, bytes):
                yield speech.StreamingRecognizeRequest(audio_content=chunk)
            else:
                # Try to coerce
                try:
                    yield speech.StreamingRecognizeRequest(audio_content=bytes(chunk))
                except Exception as e:
                    logger.error(f"[GOOGLE] Non-bytes chunk in audio generator: {e}")

    def _append_turn_latency(self):
        """Add a turn latency entry"""
        try:
            if self.current_turn_id and self.current_turn_start_time:
                first_ms = int(round((self.meta_info.get('transcriber_first_result_latency', 0)) * 1000))
                total_s = (time.perf_counter() - self.current_turn_start_time) if self.current_turn_start_time else 0
                self.turn_latencies.append({
                    'turn_id': self.current_turn_id,
                    'sequence_id': self.current_turn_id,
                    'first_result_latency_ms': first_ms,
                    'total_stream_duration_ms': int(round(total_s * 1000))
                })
                self.meta_info['turn_latencies'] = self.turn_latencies
                # Reset turn tracking
                self.current_turn_start_time = None
                self.current_turn_id = None
        except Exception as e:
            logger.error(f"[GOOGLE] Error appending turn latency: {e}")

    def _run_grpc_stream(self):
        """
        Blocking thread target that runs google streaming_recognize.
        Pushes interim and final transcripts back onto transcriber_output_queue (thread-safely).
        """
        try:
            if not self.connection_start_time:
                self.connection_start_time = time.time()

            # Build recognition config
            encoding_enum = speech.RecognitionConfig.AudioEncoding.LINEAR16
            enc = (self.encoding or "").upper()
            if 'MULAW' in enc or 'ULAW' in enc:
                encoding_enum = speech.RecognitionConfig.AudioEncoding.MULAW
            elif 'LINEAR' in enc or 'PCM' in enc:
                encoding_enum = speech.RecognitionConfig.AudioEncoding.LINEAR16

            recognition_config = speech.RecognitionConfig(
                encoding=encoding_enum,
                sample_rate_hertz=int(self.sample_rate_hertz),
                language_code=self.language,
                model=self.model,
                enable_automatic_punctuation=True,
                max_alternatives=1,
            )

            streaming_config = speech.StreamingRecognitionConfig(
                config=recognition_config,
                interim_results=True,
                single_utterance=False,
            )

            requests = self._audio_generator()

            try:
                responses = self.client.streaming_recognize(streaming_config, requests)
                self.connection_authenticated = True

                # Iterate responses synchronously
                for response in responses:
                    if not self._running:
                        break
                    if not response.results:
                        continue

                    result = response.results[0]
                    is_final = result.is_final
                    transcript = ""
                    if result.alternatives:
                        transcript = result.alternatives[0].transcript.strip()

                    if transcript:
                        # Set first-result latency if not already set
                        if self.meta_info and 'transcriber_start_time' in self.meta_info and 'transcriber_first_result_latency' not in self.meta_info:
                            self.meta_info['transcriber_first_result_latency'] = time.perf_counter() - self.meta_info['transcriber_start_time']
                            self.meta_info['first_result_latency_ms'] = round(self.meta_info['transcriber_first_result_latency'] * 1000)

                        # Prepare packet
                        if is_final:
                            # Populate total durations
                            if self.meta_info and 'transcriber_start_time' in self.meta_info:
                                self.meta_info['transcriber_total_stream_duration'] = time.perf_counter() - self.meta_info['transcriber_start_time']

                            # Append turn latencies
                            self._append_turn_latency()

                            data = {"type": "transcript", "content": transcript}
                            self._enqueue_output(data, meta=self.meta_info)
                        else:
                            data = {"type": "interim_transcript_received", "content": transcript}
                            self._enqueue_output(data, meta=self.meta_info)

                # After streaming ends, send transcriber_connection_closed
                closed_meta = (self.meta_info or {}).copy()
                if 'transcriber_total_stream_duration' not in closed_meta and 'transcriber_start_time' in closed_meta:
                    closed_meta['transcriber_total_stream_duration'] = time.perf_counter() - closed_meta['transcriber_start_time']
                self._enqueue_output("transcriber_connection_closed", meta=closed_meta)

            except Exception as stream_error:
                logger.error(f"[GOOGLE] Streaming error: {stream_error}")
                err_meta = (self.meta_info or {}).copy()
                err_meta['error'] = str(stream_error)
                err_meta['error_type'] = 'streaming_error'
                self._enqueue_output("transcriber_connection_closed", meta=err_meta)
                return

        except Exception as e:
            logger.error(f"[GOOGLE] Setup error: {e}", exc_info=True)
            err_meta = (self.meta_info or {}).copy()
            err_meta['error'] = str(e)
            err_meta['error_type'] = 'setup_error'
            self._enqueue_output("transcriber_connection_closed", meta=err_meta)
        finally:
            self.connection_authenticated = False

    async def toggle_connection(self):
        """Stop the transcriber and close connections"""
        logger.info("[GOOGLE] toggle_connection called")
        self._running = False
        self.connection_authenticated = False

        # Cancel transcription task if running
        if hasattr(self, 'transcription_task') and self.transcription_task:
            try:
                self.transcription_task.cancel()
            except Exception:
                pass

        # Signal thread to stop
        try:
            self._audio_q.put(None)
        except Exception:
            pass

        # Wait for thread cleanup with timeout
        if hasattr(self, '_grpc_thread') and self._grpc_thread and self._grpc_thread.is_alive():
            try:
                self._grpc_thread.join(timeout=2.0)
                if self._grpc_thread.is_alive():
                    logger.warning("[GOOGLE] gRPC thread did not terminate within timeout")
            except Exception as e:
                logger.error(f"[GOOGLE] Error joining gRPC thread: {e}")

        logger.info("[GOOGLE] Connection toggled off")

    def get_meta_info(self):
        return self.meta_info
