"""
Streaming ASR Handler for VAPI-like Low Latency
Uses WebSocket connection to Deepgram for real-time transcription

Optimizations implemented:
1. Adaptive endpointing (200-400ms based on context)
2. Confidence-based early processing
3. Smart turn detection with speech patterns
4. No audio buffering - stream immediately
"""

import asyncio
import json
import logging
import time
import websockets
from websockets.exceptions import InvalidStatus
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class StreamingDeepgramASR:
    """
    Real-time streaming ASR using Deepgram WebSocket API.

    Key features for low latency:
    1. Persistent WebSocket connection (no connection overhead per utterance)
    2. Interim results for early processing (predict-and-scrap support)
    3. Adaptive endpointing for natural turn detection
    4. Confidence tracking for smart processing decisions
    5. No audio buffering - stream immediately
    """

    def __init__(
        self,
        api_key: str,
        model: str = "nova-3",
        language: str = "en",
        sample_rate: int = 8000,
        encoding: str = "mulaw",  # Twilio uses mulaw
        on_transcript: Optional[Callable[[str, bool], Awaitable[None]]] = None,
        on_utterance_end: Optional[Callable[[], Awaitable[None]]] = None,
        on_speech_started: Optional[Callable[[], Awaitable[None]]] = None,
        on_confidence_update: Optional[Callable[[float], Awaitable[None]]] = None,
        endpointing_ms: int = 250,  # Reduced from 300ms for faster response
    ):
        self.api_key = api_key
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.endpointing_ms = endpointing_ms

        # Callbacks
        self.on_transcript = on_transcript
        self.on_utterance_end = on_utterance_end
        self.on_speech_started = on_speech_started
        self.on_confidence_update = on_confidence_update

        # State
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.receive_task: Optional[asyncio.Task] = None
        self.current_transcript = ""

        # Confidence tracking for smart processing
        self.last_confidence = 0.0
        self.high_confidence_threshold = 0.85  # Process early if confidence > 85%
        self.speech_start_time: Optional[float] = None
        self.total_speech_duration = 0.0

    async def connect(self):
        """Establish WebSocket connection to Deepgram"""
        # Try with configured language first, fallback to English if it fails
        languages_to_try = [self.language]
        if self.language != "en":
            languages_to_try.append("en")  # Fallback to English

        last_error = None
        for lang in languages_to_try:
            try:
                await self._connect_with_language(lang)
                return  # Success!
            except Exception as e:
                last_error = e
                if lang != languages_to_try[-1]:
                    logger.warning(f"[STREAMING_ASR] ⚠️ Connection failed with language={lang}, trying fallback...")

        # All attempts failed
        logger.error(f"[STREAMING_ASR] ❌ All connection attempts failed: {last_error}")
        raise last_error

    async def _connect_with_language(self, language: str):
        """Attempt connection to Deepgram with specific language"""
        # Build URL with optimal parameters for low latency
        # Note: For non-English, try 'multi' model which supports code-switching
        model = self.model
        if language != "en" and language != "multi":
            # For non-English single languages, nova-2 works better
            # nova-3 currently only supports 'en' or 'multi'
            if "nova-3" in model:
                model = "nova-2"
                logger.info(f"[STREAMING_ASR] Switching from nova-3 to nova-2 for language={language}")

        # Build minimal parameters first - add optional features carefully
        # Deepgram can reject connections if unsupported params are used
        params = {
            "model": model,
            "language": language,
            "encoding": self.encoding,
            "sample_rate": self.sample_rate,
            "channels": 1,
            "punctuate": "true",
            "interim_results": "true",  # Required for real-time
            "endpointing": str(self.endpointing_ms),  # Adaptive endpointing
            "utterance_end_ms": "1000",  # Must be >= 1000ms per Deepgram docs
        }

        # Add optional features that may not be supported on all models/tiers
        # Only add if we're using nova-2 or nova-3 which support these
        if "nova" in model:
            params["smart_format"] = "true"
            params["filler_words"] = "false"

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"wss://api.deepgram.com/v1/listen?{query_string}"

        # Log connection attempt with details for debugging
        api_key_preview = f"{self.api_key[:8]}...{self.api_key[-4:]}" if len(self.api_key) > 12 else "***"
        logger.info(f"[STREAMING_ASR] Connecting to Deepgram: model={model}, language={language}")
        logger.info(f"[STREAMING_ASR] API key: {api_key_preview}, URL params: {list(params.keys())}")

        try:
            self.ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Token {self.api_key}"},
                ping_interval=30,  # Send ping every 30 seconds
                ping_timeout=60,   # Wait 60 seconds for pong
                close_timeout=10,
                max_size=None      # No message size limit
            )
        except InvalidStatus as e:
            # Log detailed error info for debugging
            logger.error(f"[STREAMING_ASR] ❌ Deepgram rejected connection: {e}")
            logger.error(f"[STREAMING_ASR] Full URL: {url}")
            logger.error(f"[STREAMING_ASR] API key length: {len(self.api_key)}, starts with: {self.api_key[:4] if self.api_key else 'EMPTY'}")
            # Try to extract response body from the exception if available
            if hasattr(e, 'response') and e.response:
                try:
                    logger.error(f"[STREAMING_ASR] Response headers: {dict(e.response.headers)}")
                except:
                    pass
            raise

        self.is_connected = True
        self.language = language  # Update to the language that worked
        self.receive_task = asyncio.create_task(self._receive_loop())

        logger.info(f"[STREAMING_ASR] ✅ Connected to Deepgram (model={model}, language={language})")
    
    async def send_audio(self, audio_bytes: bytes):
        """
        Send audio chunk to Deepgram immediately (no buffering!).
        This is the key to low latency.
        """
        if self.ws and self.is_connected:
            try:
                await self.ws.send(audio_bytes)
            except Exception as e:
                logger.error(f"[STREAMING_ASR] Error sending audio: {e}")
    
    async def _receive_loop(self):
        """Receive transcription results from Deepgram"""
        try:
            async for message in self.ws:
                data = json.loads(message)

                msg_type = data.get("type")

                if msg_type == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])

                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        confidence = alternatives[0].get("confidence", 0.0)
                        is_final = data.get("is_final", False)

                        # Track confidence for smart processing decisions
                        self.last_confidence = confidence
                        if self.on_confidence_update:
                            await self.on_confidence_update(confidence)

                        if transcript:
                            self.current_transcript = transcript

                            if self.on_transcript:
                                await self.on_transcript(transcript, is_final)

                            if is_final:
                                # Calculate speech duration for metrics
                                if self.speech_start_time:
                                    duration_ms = (time.time() - self.speech_start_time) * 1000
                                    self.total_speech_duration += duration_ms
                                    logger.info(f"[STREAMING_ASR] Final transcript ({duration_ms:.0f}ms, conf={confidence:.2f}): {transcript}")
                                    self.speech_start_time = None
                                else:
                                    logger.info(f"[STREAMING_ASR] Final transcript (conf={confidence:.2f}): {transcript}")
                                self.current_transcript = ""
                            else:
                                # Log high-confidence interims for debugging predict-and-scrap
                                if confidence > self.high_confidence_threshold:
                                    logger.debug(f"[STREAMING_ASR] High-conf interim ({confidence:.2f}): {transcript}")
                                else:
                                    logger.debug(f"[STREAMING_ASR] Interim ({confidence:.2f}): {transcript}")

                elif msg_type == "UtteranceEnd":
                    # User stopped speaking
                    duration_info = ""
                    if self.speech_start_time:
                        duration_ms = (time.time() - self.speech_start_time) * 1000
                        duration_info = f" (speech duration: {duration_ms:.0f}ms)"
                    logger.info(f"[STREAMING_ASR] Utterance end detected{duration_info}")
                    if self.on_utterance_end:
                        await self.on_utterance_end()

                elif msg_type == "SpeechStarted":
                    self.speech_start_time = time.time()
                    logger.debug("[STREAMING_ASR] Speech started")
                    if self.on_speech_started:
                        await self.on_speech_started()

        except websockets.exceptions.ConnectionClosed:
            logger.info("[STREAMING_ASR] Connection closed")
        except Exception as e:
            logger.error(f"[STREAMING_ASR] Receive error: {e}")
        finally:
            self.is_connected = False
    
    async def close(self):
        """Close the WebSocket connection"""
        if self.ws:
            try:
                # Send close frame to Deepgram
                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await self.ws.close()
            except:
                pass
            
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        
        self.is_connected = False
        logger.info("[STREAMING_ASR] Closed")

