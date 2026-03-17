"""
Sarvam AI Transcriber for Convis
Adapted from Bolna architecture for Indian language support
"""
import asyncio
import base64
import json
import os
import io
import wave
import time
try:
    import audioop  # Python < 3.13
except ModuleNotFoundError:
    import audioop_lts as audioop  # Python 3.13+
import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import InvalidHandshake

import numpy as np
from scipy.signal import resample_poly
from typing import Optional

from .base_transcriber import BaseTranscriber
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.helpers.utils import create_ws_data_packet

logger = configure_logger(__name__)


class SarvamTranscriber(BaseTranscriber):
    def __init__(
        self,
        telephony_provider,
        input_queue=None,
        output_queue=None,
        model="saarika:v2",
        language="en-IN",
        endpointing="400",
        transcriber_key=None,
        **kwargs,
    ):
        super().__init__(input_queue)

        self.telephony_provider = telephony_provider
        self.model = model
        self.language = language
        self.endpointing = endpointing
        
        # Noise suppression settings
        self.noise_suppression_level = kwargs.get("noise_suppression_level", "medium")
        logger.info(f"[SARVAM] Initialized with noise_suppression_level={self.noise_suppression_level}, endpointing={endpointing}ms")

        self.api_key = (transcriber_key or os.getenv("SARVAM_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY not configured for SarvamTranscriber")
        self.api_host = os.getenv("SARVAM_HOST", "api.sarvam.ai")

        # Determine endpoint based on model
        if model.startswith("saaras"):
            self.ws_url = f"wss://{self.api_host}/speech-to-text-translate/ws"
        else:
            self.ws_url = f"wss://{self.api_host}/speech-to-text/ws"

        self.transcriber_output_queue = output_queue
        self.transcription_task = None
        self.sender_task = None
        self.heartbeat_task = None

        self.audio_submitted = False
        self.audio_submission_time = None
        self.num_frames = 0
        self.connection_start_time = None
        self.connection_time = None
        self.audio_frame_duration = 0.2

        self.websocket_connection = None
        self.connection_authenticated = False
        self.meta_info = {}

        self._configure_audio_params()

    def _configure_audio_params(self):
        """Configure audio parameters based on telephony provider"""
        if self.telephony_provider == "twilio":
            self.encoding = "mulaw"
            self.input_sampling_rate = 8000
            self.sampling_rate = 16000
        elif self.telephony_provider == "plivo":
            self.encoding = "linear16"
            self.input_sampling_rate = 8000
            self.sampling_rate = 16000
        else:
            self.encoding = "linear16"
            self.sampling_rate = 16000
            self.input_sampling_rate = 16000

    def _get_ws_url(self):
        """Build WebSocket URL with query parameters"""
        params = {"model": self.model}

        # saaras auto-detects language, saarika requires language-code
        if not self.model.startswith("saaras"):
            params["language-code"] = self.language

        # Add VAD parameters
        params["high_vad_sensitivity"] = "true"
        params["vad_signals"] = "true"

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.ws_url}?{query_string}"

    def _convert_audio_to_wav(self, audio_data) -> Optional[bytes]:
        """Convert audio data to WAV format for Sarvam API"""
        try:
            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data

            # Convert μ-law to linear PCM if needed
            if self.encoding == "mulaw":
                audio_bytes = audioop.ulaw2lin(audio_bytes, 2)

            # Resample if needed
            if self.input_sampling_rate != self.sampling_rate:
                audio_bytes = self.normalize_to_16k(audio_bytes, self.input_sampling_rate)

            # Convert to numpy array and create WAV
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self.sampling_rate)
                wav_file.writeframes(audio_array.tobytes())
            wav_buffer.seek(0)
            return wav_buffer.getvalue()
        except Exception as e:
            logger.error(f"[SARVAM] WAV conversion error: {e}")
            return None

    def normalize_to_16k(self, raw_audio: bytes, in_sr: int) -> bytes:
        """Resample audio to 16kHz"""
        if in_sr == self.sampling_rate:
            return raw_audio
        try:
            audio_np = np.frombuffer(raw_audio, dtype=np.int16)
            gcd = np.gcd(in_sr, self.sampling_rate)
            up = self.sampling_rate // gcd
            down = in_sr // gcd
            resampled_np = resample_poly(audio_np, up, down)
            resampled_np = np.clip(resampled_np, -32768, 32767).astype(np.int16)
            return resampled_np.tobytes()
        except Exception as e:
            logger.error(f"[SARVAM] Resampling error: {e}")
            return raw_audio

    async def sender(self, ws: ClientConnection):
        """Send audio frames to Sarvam WebSocket"""
        try:
            while True:
                ws_data_packet = await self.input_queue.get()
                if ws_data_packet is None:
                    continue

                if not self.audio_submitted:
                    self.meta_info = ws_data_packet.get("meta_info", {})
                    self.audio_submitted = True
                    self.audio_submission_time = time.time()
                    self.meta_info["request_id"] = self.generate_request_id()

                # Check for end of stream
                if ws_data_packet.get("meta_info", {}).get("eos") is True:
                    await ws.close()
                    break

                self.num_frames += 1

                audio_data = ws_data_packet.get("data")
                if audio_data:
                    # Convert to WAV format
                    wav_bytes = self._convert_audio_to_wav(audio_data)
                    if not wav_bytes:
                        continue

                    # Encode as base64 and send
                    audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                    message = {
                        "audio": {
                            "data": audio_b64,
                            "encoding": "audio/wav",
                            "sample_rate": self.sampling_rate
                        }
                    }
                    await ws.send(json.dumps(message))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[SARVAM] Sender error: {e}", exc_info=True)

    async def receiver(self, ws: ClientConnection):
        """Receive transcription results from Sarvam WebSocket"""
        try:
            async for message in ws:
                try:
                    data = json.loads(message) if isinstance(message, str) else message
                    logger.debug(f"[SARVAM] Received: {str(data)[:200]}...")

                    if not isinstance(data, dict):
                        continue

                    # Handle Sarvam STT response format
                    # Sarvam sends: {"transcript": "...", "isFinal": bool, ...}
                    # Or: {"type": "data", "data": {"transcript": "..."}}
                    
                    transcript = None
                    is_final = False
                    
                    # Try direct transcript field (Sarvam's actual format)
                    if "transcript" in data:
                        transcript = data.get("transcript", "").strip()
                        is_final = data.get("isFinal", False)
                    # Try nested format (legacy)
                    elif data.get("type") == "data":
                        payload = data.get("data", {})
                        transcript = payload.get("transcript", "").strip()
                        is_final = True
                    # Try normalizedAlignment (some Sarvam responses)
                    elif "normalizedAlignment" in data:
                        alignment = data.get("normalizedAlignment", {})
                        chars = alignment.get("chars", [])
                        if chars:
                            transcript = "".join(chars).strip()
                        is_final = data.get("isFinal", False)

                    if transcript:
                        logger.info(f"[SARVAM] 📝 Transcript: {transcript}")
                        
                        # Track first result latency
                        if self.audio_submission_time and "transcriber_first_result_latency" not in self.meta_info:
                            latency = time.time() - self.audio_submission_time
                            self.meta_info["transcriber_first_result_latency"] = latency
                            self.meta_info["first_result_latency_ms"] = round(latency * 1000)

                        # Create transcript data packet
                        transcript_data = {
                            "type": "transcript" if is_final else "interim_transcript_received",
                            "content": transcript,
                            "is_final": is_final
                        }
                        yield create_ws_data_packet(transcript_data, self.meta_info)

                    # Handle VAD events
                    elif data.get("type") == "events":
                        vad = data.get("data", {})
                        if vad.get("signal_type") == "START_SPEECH":
                            yield create_ws_data_packet("speech_started", self.meta_info)
                        elif vad.get("signal_type") == "END_SPEECH":
                            yield create_ws_data_packet("speech_ended", self.meta_info)

                    elif data.get("type") == "connection_closed":
                        yield create_ws_data_packet("transcriber_connection_closed", self.meta_info)
                        return

                except Exception as e:
                    logger.error(f"[SARVAM] Receiver error: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[SARVAM] Receiver stream error: {e}", exc_info=True)

    async def sarvam_connect(self, retries: int = 3, timeout: float = 10.0) -> ClientConnection:
        """Connect to Sarvam WebSocket with retries"""
        ws_url = self._get_ws_url()
        additional_headers = {
            'api-subscription-key': self.api_key,
            'api-key': self.api_key,
            'x-api-key': self.api_key,
            'authorization': f"Bearer {self.api_key}"
        }

        attempt = 0
        last_err = None

        while attempt < retries:
            try:
                ws = await asyncio.wait_for(
                    websockets.connect(ws_url, additional_headers=additional_headers),
                    timeout=timeout,
                )
                self.websocket_connection = ws
                self.connection_authenticated = True
                logger.info("[SARVAM] Connected successfully")
                return ws

            except asyncio.TimeoutError:
                logger.error("[SARVAM] Connection timeout")
                raise ConnectionError("Timeout connecting to Sarvam")

            except InvalidHandshake as e:
                error_msg = str(e)
                if '401' in error_msg or '403' in error_msg:
                    logger.error(f"[SARVAM] Authentication failed: {e}")
                    raise ConnectionError(f"Sarvam authentication failed: {e}")
                elif '404' in error_msg:
                    logger.error(f"[SARVAM] Endpoint not found: {e}")
                    raise ConnectionError(f"Sarvam endpoint not found: {e}")
                else:
                    last_err = e
                    attempt += 1
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"[SARVAM] Connection error (attempt {attempt + 1}/{retries}): {e}")
                last_err = e
                attempt += 1
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)

        raise ConnectionError(f"Failed to connect to Sarvam after {retries} attempts: {last_err}")

    async def send_heartbeat(self, ws: ClientConnection, interval_sec: float = 10.0):
        """Send periodic pings to keep connection alive"""
        try:
            while True:
                await asyncio.sleep(interval_sec)
                try:
                    await ws.ping()
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    async def toggle_connection(self):
        """Stop the transcriber and close connections"""
        self.connection_on = False

        if self.sender_task:
            self.sender_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.websocket_connection:
            try:
                await self.websocket_connection.close()
            except Exception:
                pass
            finally:
                self.websocket_connection = None
                self.connection_authenticated = False

    async def run(self):
        """Main transcription loop"""
        try:
            start_time = time.perf_counter()

            # Connect to Sarvam WebSocket
            try:
                sarvam_ws = await self.sarvam_connect()
            except (ValueError, ConnectionError) as e:
                logger.error(f"[SARVAM] Connection failed: {e}")
                await self.toggle_connection()
                return

            if not self.connection_time:
                self.connection_time = round((time.perf_counter() - start_time) * 1000)
                logger.info(f"[SARVAM] Connection established in {self.connection_time}ms")

            try:
                async with sarvam_ws:
                    # Start sender and heartbeat tasks
                    self.sender_task = asyncio.create_task(self.sender(sarvam_ws))
                    self.heartbeat_task = asyncio.create_task(self.send_heartbeat(sarvam_ws))

                    # Process transcription results
                    async for message in self.receiver(sarvam_ws):
                        if self.transcriber_output_queue:
                            await self.transcriber_output_queue.put(message)

            except Exception as e:
                logger.error(f"[SARVAM] Transcription error: {e}", exc_info=True)

        finally:
            # Cleanup
            if self.sender_task:
                self.sender_task.cancel()
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            if self.websocket_connection:
                try:
                    await self.websocket_connection.close()
                except Exception:
                    pass
                finally:
                    self.websocket_connection = None
                    self.connection_authenticated = False

    def get_meta_info(self):
        return getattr(self, "meta_info", {})
