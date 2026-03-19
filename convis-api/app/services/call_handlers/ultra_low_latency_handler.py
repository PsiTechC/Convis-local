"""
Ultra-Low-Latency Voice Pipeline

WORD-BY-WORD streaming for minimum latency:
- Deepgram ASR: Streaming WebSocket (no buffering)
- LLM: Token-by-token streaming (OpenAI, Groq)
- TTS: ElevenLabs WebSocket (word-by-word) OR Sarvam (chunked streaming)

Target latency:
- ElevenLabs: 100-200ms to first audio
- Sarvam: 200-400ms to first audio (best Hindi quality)

Supported Configurations:
- ASR: Deepgram (nova-3, nova-2, etc.)
- LLM: OpenAI (gpt-4o-mini, gpt-4o), Groq (llama, mixtral)
- TTS: ElevenLabs (word-by-word), Sarvam (chunked streaming for Hindi)
- Calendar: Automatic scheduling from conversation (same as realtime API)
"""

import asyncio
import base64
import json
import logging
import os
import time
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone

from fastapi import WebSocket

from .streaming_asr_handler import StreamingDeepgramASR
from .elevenlabs_websocket_tts import ElevenLabsWebSocketTTS
from .sarvam_streaming_tts import SarvamStreamingTTS
from app.utils.call_quality_monitor import CallQualityMonitor, QoSThresholds, QualityAlert

logger = logging.getLogger(__name__)

# Calendar services - imported lazily
_calendar_service = None
_calendar_intent_service = None


def get_calendar_services():
    """Lazily initialize calendar services"""
    global _calendar_service, _calendar_intent_service
    if _calendar_service is None:
        try:
            from app.services.calendar_service import CalendarService
            from app.services.calendar_intent_service import CalendarIntentService
            _calendar_service = CalendarService()
            _calendar_intent_service = CalendarIntentService()
            logger.info("[ULTRA-CALENDAR] ✅ Calendar services initialized")
        except Exception as e:
            logger.warning(f"[ULTRA-CALENDAR] ⚠️ Could not initialize calendar services: {e}")
    return _calendar_service, _calendar_intent_service


# Supported models for streaming
SUPPORTED_MODELS = {
    "asr": {
        "deepgram": {
            "models": ["nova-3", "nova-2", "nova", "enhanced", "base"],
            "languages": ["en", "en-US", "en-GB", "en-AU", "en-IN", "hi", "es", "fr", "de", "it", "pt", "ja", "ko", "zh"],
            "streaming": True,
            "description": "Real-time streaming ASR via WebSocket"
        }
    },
    "llm": {
        "openai": {
            "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
            "streaming": True,
            "description": "OpenAI GPT models with streaming support"
        },
        "groq": {
            "models": ["llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
            "streaming": True,
            "description": "Groq ultra-fast inference (lowest latency LLM)"
        }
    },
    "tts": {
        "elevenlabs": {
            "models": ["eleven_turbo_v2_5", "eleven_turbo_v2", "eleven_multilingual_v2", "eleven_monolingual_v1"],
            "streaming": True,
            "websocket_input": True,
            "latency": "100-200ms",
            "description": "ElevenLabs with WebSocket input streaming (word-by-word)"
        },
        "sarvam": {
            "models": ["bulbul:v2", "bulbul:v1"],
            "streaming": True,
            "chunked_streaming": True,
            "latency": "200-400ms",
            "languages": ["hi-IN", "bn-IN", "ta-IN", "te-IN", "mr-IN", "gu-IN", "kn-IN", "ml-IN", "pa-IN", "or-IN", "en-IN"],
            "description": "Sarvam AI with chunked streaming (best Hindi quality)"
        }
    }
}


class UltraLowLatencyHandler:
    """
    Streaming voice pipeline supporting both ElevenLabs and Sarvam TTS.

    All settings are configurable via assistant_config:
    - asr_provider: "deepgram"
    - asr_model: "nova-3", "nova-2", etc.
    - asr_language: "en", "hi", "es", etc.
    - llm_provider: "openai" or "groq"
    - llm_model: "gpt-4o-mini", "llama-3.1-70b-versatile", etc.
    - tts_provider: "elevenlabs" or "sarvam"
    - tts_model: Model name for selected provider
    - tts_voice: Voice name or ID
    - For ElevenLabs: tts_stability, tts_similarity_boost, tts_style
    - For Sarvam: tts_pitch, tts_loudness, bot_language
    - temperature: LLM temperature
    - llm_max_tokens: Max response tokens
    - system_message: System prompt
    - greeting: Initial greeting
    - keepalive_interval: Seconds between keepalive pings
    """

    def __init__(
        self,
        websocket: WebSocket,
        assistant_config: Dict[str, Any],
        provider_keys: Dict[str, str]
    ):
        self.websocket = websocket
        self.config = assistant_config
        self.provider_keys = provider_keys

        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None

        # Pipeline components
        self.asr: Optional[StreamingDeepgramASR] = None
        self.tts: Optional[Union[ElevenLabsWebSocketTTS, SarvamStreamingTTS]] = None
        self.llm_client = None

        # Configurable settings with defaults
        self.asr_provider = self.config.get("asr_provider", "deepgram")
        self.asr_model = self.config.get("asr_model", "nova-3")
        self.asr_language = self.config.get("asr_language", "en")

        self.llm_provider = self.config.get("llm_provider", "openai")
        self.llm_model = self.config.get("llm_model", "gpt-4o-mini")
        self.temperature = self.config.get("temperature", 0.8)
        self.llm_max_tokens = self.config.get("llm_max_tokens", 150)

        # TTS provider selection
        self.tts_provider = self.config.get("tts_provider", "elevenlabs").lower()
        self.tts_model = self.config.get("tts_model")
        self.tts_voice = self.config.get("tts_voice")

        # ElevenLabs-specific settings
        self.tts_stability = self.config.get("tts_stability", 0.5)
        self.tts_similarity_boost = self.config.get("tts_similarity_boost", 0.75)
        self.tts_style = self.config.get("tts_style", 0.0)
        self.tts_output_format = self.config.get("tts_output_format", "ulaw_8000")

        # Sarvam-specific settings
        self.tts_pitch = self.config.get("tts_pitch", 0.0)
        self.tts_loudness = self.config.get("tts_loudness", 1.0)
        self.bot_language = self.config.get("bot_language", "hi-IN")

        self.keepalive_interval = self.config.get("keepalive_interval", 15)

        # Set defaults based on provider
        if self.tts_provider == "sarvam":
            self.tts_model = self.tts_model or "bulbul:v2"
            self.tts_voice = self.tts_voice or "manisha"
        else:  # elevenlabs
            self.tts_model = self.tts_model or "eleven_turbo_v2_5"
            self.tts_voice = self.tts_voice or "shimmer"

        # State
        self.is_running = False
        self.is_speaking = False
        self.interrupted = False
        self.current_gen_id = 0

        # Conversation
        self.conversation_history = []
        self.system_message = self.config.get("system_message", "You are a helpful assistant.")

        # Metrics
        self.metrics = {"first_audio_ms": [], "total_latency_ms": []}

        # Calendar scheduling state
        self.calendar_enabled = self.config.get("calendar_enabled", False)
        self.calendar_account_ids = self.config.get("calendar_account_ids", [])
        self.calendar_account_id = self.config.get("calendar_account_id")
        self.calendar_provider = self.config.get("calendar_provider", "google")
        self.timezone = self.config.get("timezone", "America/New_York")
        self.assistant_id = self.config.get("assistant_id")
        self.user_id = self.config.get("user_id")
        self.appointment_scheduled = False
        self.appointment_metadata = None
        self.scheduling_task: Optional[asyncio.Task] = None

        if self.calendar_enabled:
            logger.info(f"[ULTRA] 📅 Calendar enabled with {len(self.calendar_account_ids)} calendar(s)")

        # Call Quality Monitoring - Track network and audio quality metrics
        self.quality_monitoring_enabled = self.config.get('quality_monitoring_enabled', True)
        self.quality_monitor: Optional[CallQualityMonitor] = None
        self.call_quality_report = None
        if self.quality_monitoring_enabled:
            qos_thresholds = QoSThresholds(
                max_packet_loss_percent=self.config.get('qos_max_packet_loss', 3.0),
                max_jitter_ms=self.config.get('qos_max_jitter_ms', 30.0),
                max_rtt_ms=self.config.get('qos_max_rtt_ms', 300.0),
                min_snr_db=self.config.get('qos_min_snr_db', 10.0),
            )
            call_id = self.config.get('call_id', 'unknown')
            self.quality_monitor = CallQualityMonitor(
                call_id=call_id,
                thresholds=qos_thresholds,
                sample_rate=8000,
                alert_callback=self._on_quality_alert
            )
            logger.info(f"[ULTRA] 📊 Call quality monitoring enabled")

    def _on_quality_alert(self, alert: QualityAlert):
        """Handle quality alerts during the call"""
        logger.warning(f"[QUALITY] {alert.severity.upper()}: {alert.message}")

    async def initialize(self):
        """Initialize all streaming components with configured settings"""
        logger.info("[ULTRA] 🚀 Initializing streaming pipeline...")
        logger.info(f"[ULTRA] Config: ASR={self.asr_provider}/{self.asr_model}, "
                   f"LLM={self.llm_provider}/{self.llm_model}, "
                   f"TTS={self.tts_provider}/{self.tts_model}")

        # Initialize Deepgram streaming ASR
        deepgram_key = self.provider_keys.get("deepgram") or os.getenv("DEEPGRAM_API_KEY")
        if not deepgram_key:
            raise ValueError("Deepgram API key required for streaming mode")

        self.asr = StreamingDeepgramASR(
            api_key=deepgram_key,
            model=self.asr_model,
            language=self.asr_language,
            on_transcript=self._on_transcript,
            on_utterance_end=self._on_utterance_end
        )
        logger.info(f"[ULTRA] ✅ ASR: Deepgram {self.asr_model} ({self.asr_language})")

        # Initialize LLM client based on provider
        await self._initialize_llm()

        # Initialize TTS based on provider
        await self._initialize_tts()

        # Initialize conversation
        self.conversation_history = [{
            "role": "system",
            "content": self.system_message
        }]

        logger.info("[ULTRA] ✅ Pipeline initialized")

    async def _initialize_llm(self):
        """Initialize LLM client based on configured provider"""
        if self.llm_provider == "openai":
            openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise ValueError("OpenAI API key required")

            import openai
            self.llm_client = openai.AsyncOpenAI(api_key=openai_key)
            logger.info(f"[ULTRA] ✅ LLM: OpenAI {self.llm_model}")

        elif self.llm_provider == "groq":
            groq_key = self.provider_keys.get("groq") or os.getenv("GROQ_API_KEY")
            if not groq_key:
                raise ValueError("Groq API key required")

            from groq import AsyncGroq
            self.llm_client = AsyncGroq(api_key=groq_key)
            logger.info(f"[ULTRA] ✅ LLM: Groq {self.llm_model}")

        else:
            # Fallback to OpenAI
            logger.warning(f"[ULTRA] Unknown LLM provider '{self.llm_provider}', falling back to OpenAI")
            openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise ValueError("OpenAI API key required (fallback)")

            import openai
            self.llm_client = openai.AsyncOpenAI(api_key=openai_key)
            self.llm_provider = "openai"
            self.llm_model = "gpt-4o-mini"

    async def _initialize_tts(self):
        """Initialize TTS based on configured provider"""
        if self.tts_provider == "sarvam":
            # Sarvam TTS (chunked streaming for Hindi)
            sarvam_key = self.provider_keys.get("sarvam") or os.getenv("SARVAM_API_KEY")
            if not sarvam_key:
                logger.warning("[ULTRA] ⚠️ No Sarvam key, falling back to ElevenLabs")
                self.tts_provider = "elevenlabs"
                await self._initialize_elevenlabs()
                return

            self.tts = SarvamStreamingTTS(
                api_key=sarvam_key,
                voice=self.tts_voice,
                model=self.tts_model,
                language=self.bot_language,
                pitch=self.tts_pitch,
                loudness=self.tts_loudness,
                on_audio_chunk=self._send_audio_chunk
            )
            logger.info(f"[ULTRA] ✅ TTS: Sarvam {self.tts_model} (voice: {self.tts_voice}, lang: {self.bot_language})")

        else:
            # ElevenLabs TTS (WebSocket word-by-word streaming)
            await self._initialize_elevenlabs()

    async def _initialize_elevenlabs(self):
        """Initialize ElevenLabs WebSocket TTS"""
        elevenlabs_key = self.provider_keys.get("elevenlabs") or os.getenv("ELEVENLABS_API_KEY")
        if not elevenlabs_key:
            raise ValueError("ElevenLabs API key required")

        self.tts = ElevenLabsWebSocketTTS(
            api_key=elevenlabs_key,
            voice=self.tts_voice,
            model=self.tts_model,
            output_format=self.tts_output_format,
            stability=self.tts_stability,
            similarity_boost=self.tts_similarity_boost,
            style=self.tts_style,
            on_audio_chunk=self._send_audio_chunk
        )

        # Pre-connect WebSocket for faster first response
        await self.tts.connect()
        logger.info(f"[ULTRA] ✅ TTS: ElevenLabs {self.tts_model} (voice: {self.tts_voice})")

    async def start(self):
        """Start the pipeline"""
        self.is_running = True
        await self.asr.connect()

        # Start keepalive
        asyncio.create_task(self._keepalive_loop())

        logger.info("[ULTRA] ▶️ Pipeline started")

    async def _keepalive_loop(self):
        """Keep connections alive"""
        while self.is_running:
            await asyncio.sleep(self.keepalive_interval)
            if self.asr and self.asr.ws:
                try:
                    await self.asr.ws.send(json.dumps({"type": "KeepAlive"}))
                except Exception:
                    pass

    async def handle_message(self, message: Dict[str, Any]):
        """Handle Twilio WebSocket message"""
        event = message.get("event")

        if event == "start":
            start_data = message.get("start", {})
            self.stream_sid = start_data.get("streamSid")
            self.call_sid = start_data.get("callSid")
            logger.info(f"[ULTRA] 📞 Call started: {self.call_sid}")

            # Send greeting if configured
            greeting = self.config.get("greeting")
            if greeting:
                await self._speak(greeting)

        elif event == "media":
            media = message.get("media", {})
            payload = media.get("payload")
            if payload and self.asr and self.asr.is_connected:
                audio = base64.b64decode(payload)

                # Track audio quality metrics
                if self.quality_monitor and audio:
                    self.quality_monitor.track_audio_chunk(audio, is_voice=not self.is_speaking)

                await self.asr.send_audio(audio)

        elif event == "mark":
            mark = message.get("mark", {})
            if mark.get("name") == "speech_end":
                self.is_speaking = False

        elif event == "stop":
            await self.close()

    async def _on_transcript(self, transcript: str, is_final: bool):
        """Handle ASR transcript"""
        # Barge-in detection
        if self.is_speaking and transcript and len(transcript.strip()) > 3:
            logger.info(f"[ULTRA] 🛑 BARGE-IN: {transcript[:30]}...")
            await self._handle_interruption()

        if is_final and transcript.strip():
            logger.info(f"[ULTRA] 🎤 User: {transcript}")
            asyncio.create_task(self._process_input(transcript))

    async def _on_utterance_end(self):
        """Handle end of user speech"""
        pass

    async def _handle_interruption(self):
        """Stop AI speech immediately"""
        self.interrupted = True
        self.current_gen_id += 1
        self.is_speaking = False

        # Stop Sarvam if active
        if self.tts_provider == "sarvam" and hasattr(self.tts, 'stop'):
            self.tts.stop()

        if self.stream_sid:
            try:
                await self.websocket.send_json({
                    "event": "clear",
                    "streamSid": self.stream_sid
                })
            except Exception:
                pass

    async def _process_input(self, text: str):
        """Process user input with streaming"""
        self.interrupted = False
        self.current_gen_id += 1
        gen_id = self.current_gen_id

        pipeline_start = time.time()

        # Add to conversation
        self.conversation_history.append({"role": "user", "content": text})

        try:
            # Stream LLM → TTS
            full_response = await self._stream_llm_to_tts(gen_id, pipeline_start)

            if full_response and not self.interrupted:
                self.conversation_history.append({"role": "assistant", "content": full_response})

            total_ms = (time.time() - pipeline_start) * 1000
            logger.info(f"[ULTRA] ⚡ Total pipeline: {total_ms:.0f}ms")

            # Check for calendar scheduling intent (runs in background)
            if self.calendar_enabled and not self.appointment_scheduled:
                asyncio.create_task(self._maybe_schedule_from_conversation())

        except Exception as e:
            logger.error(f"[ULTRA] ❌ Pipeline error: {e}")

    async def _stream_llm_to_tts(self, gen_id: int, start_time: float) -> str:
        """
        Stream LLM tokens to TTS.

        For ElevenLabs: word-by-word streaming via WebSocket
        For Sarvam: chunked streaming (phrase-by-phrase)
        """
        self.is_speaking = True
        first_audio_logged = False

        async def on_first_audio():
            nonlocal first_audio_logged
            if not first_audio_logged:
                first_audio_logged = True
                latency = (time.time() - start_time) * 1000
                self.metrics["first_audio_ms"].append(latency)
                logger.info(f"[ULTRA] ⚡⚡ FIRST AUDIO: {latency:.0f}ms")

        async def token_generator():
            """Yield LLM tokens one by one"""
            try:
                response = await self.llm_client.chat.completions.create(
                    model=self.llm_model,
                    messages=self.conversation_history,
                    temperature=self.temperature,
                    max_tokens=self.llm_max_tokens,
                    stream=True
                )

                async for chunk in response:
                    if self.interrupted or gen_id != self.current_gen_id:
                        break

                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content

            except Exception as e:
                logger.error(f"[ULTRA] LLM error: {e}")

        # Use appropriate streaming method based on TTS provider
        if self.tts_provider == "sarvam":
            # Sarvam: chunked streaming
            full_response = await self.tts.stream_from_llm(
                token_generator(),
                on_first_audio=on_first_audio
            )
        else:
            # ElevenLabs: word-by-word streaming
            full_response = ""
            try:
                async for token in token_generator():
                    if self.interrupted:
                        break
                    full_response += token
                    await self.tts.send_text(token)

                    # Check for first audio
                    if not first_audio_logged and self.tts.first_audio_received.is_set():
                        await on_first_audio()

                # Flush TTS
                if not self.interrupted:
                    await self.tts.send_text("", flush=True)

                    # Wait for remaining audio
                    try:
                        await asyncio.wait_for(self.tts.generation_complete.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass

            except Exception as e:
                logger.error(f"[ULTRA] Stream error: {e}")

        # Send end mark
        if self.stream_sid and not self.interrupted:
            try:
                await self.websocket.send_json({
                    "event": "mark",
                    "streamSid": self.stream_sid,
                    "mark": {"name": "speech_end"}
                })
            except Exception:
                pass

        self.is_speaking = False
        return full_response

    async def _speak(self, text: str):
        """Speak text using TTS"""
        self.is_speaking = True

        try:
            audio = await self.tts.synthesize(text)
            if audio:
                logger.info(f"[ULTRA] 🎤 Spoke: {text[:50]}...")

        except Exception as e:
            logger.error(f"[ULTRA] Speak error: {e}")

        self.is_speaking = False

    async def _send_audio_chunk(self, audio_chunk: bytes):
        """Send audio chunk to Twilio"""
        if not self.stream_sid or self.interrupted:
            return

        try:
            audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")
            await self.websocket.send_json({
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": audio_b64}
            })
        except Exception as e:
            logger.error(f"[ULTRA] Send error: {e}")

    async def _maybe_schedule_from_conversation(self):
        """
        Analyze conversation for calendar scheduling intent.
        Runs in background so it doesn't block audio.
        """
        if self.appointment_scheduled:
            return

        if self.scheduling_task and not self.scheduling_task.done():
            logger.debug("[ULTRA-CALENDAR] Scheduling task already running")
            return

        # Get calendar services
        calendar_service, calendar_intent_service = get_calendar_services()
        if not calendar_service or not calendar_intent_service:
            logger.debug("[ULTRA-CALENDAR] Calendar services not available")
            return

        # Need at least a few conversation turns
        if len(self.conversation_history) < 3:
            return

        # Get OpenAI key for intent extraction
        openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return

        async def _run_calendar_analysis():
            try:
                logger.info("[ULTRA-CALENDAR] 🔍 Analyzing conversation for scheduling intent...")

                # Build conversation for analysis (include system message)
                messages_for_analysis = [
                    {"role": "system", "content": self.system_message}
                ] + self.conversation_history

                # Extract calendar intent
                result = await calendar_intent_service.extract_from_conversation(
                    messages_for_analysis,
                    openai_key,
                    self.timezone,
                )

                logger.info(f"[ULTRA-CALENDAR] Intent result: {result}")

                if not result or not result.get("should_schedule"):
                    logger.debug("[ULTRA-CALENDAR] No scheduling intent detected")
                    return

                appointment = result.get("appointment") or {}
                start_iso = appointment.get("start_iso")
                end_iso = appointment.get("end_iso")

                if not start_iso or not end_iso:
                    logger.warning(f"[ULTRA-CALENDAR] Appointment missing start/end: {appointment}")
                    return

                logger.info(f"[ULTRA-CALENDAR] ✓ Valid appointment: {appointment.get('title')} at {start_iso}")

                appointment.setdefault("timezone", self.timezone)
                appointment.setdefault("notes", result.get("reason"))
                provider = appointment.get("provider") or self.calendar_provider

                # Parse times
                try:
                    start_time = datetime.fromisoformat(start_iso)
                    end_time = datetime.fromisoformat(end_iso)
                except Exception as e:
                    logger.error(f"[ULTRA-CALENDAR] Error parsing times: {e}")
                    return

                # Check availability and book
                calendar_account_id_for_booking = None

                if self.calendar_account_ids and len(self.calendar_account_ids) > 1:
                    # Multi-calendar
                    logger.info(f"[ULTRA-CALENDAR] Checking availability across {len(self.calendar_account_ids)} calendars...")

                    availability = await calendar_service.check_availability_across_calendars(
                        self.calendar_account_ids,
                        start_time,
                        end_time
                    )

                    if not availability.get("is_available"):
                        logger.warning("[ULTRA-CALENDAR] Time slot conflict detected")
                        await self._speak(
                            "I'm sorry, but that time slot is already occupied. Could you suggest an alternative time?"
                        )
                        return

                    # Round-robin selection
                    from app.config.database import Database
                    db = Database.get_db()
                    assistant = db['assistants'].find_one({"_id": self.assistant_id}) if self.assistant_id else None

                    calendar_account_id_for_booking = await calendar_service.get_next_available_calendar_round_robin(
                        assistant,
                        start_time,
                        end_time
                    )

                    if not calendar_account_id_for_booking:
                        logger.error("[ULTRA-CALENDAR] Round-robin selection failed")
                        return

                elif self.calendar_account_ids and len(self.calendar_account_ids) == 1:
                    # Single calendar
                    availability = await calendar_service.check_availability_across_calendars(
                        self.calendar_account_ids,
                        start_time,
                        end_time
                    )

                    if not availability.get("is_available"):
                        logger.warning("[ULTRA-CALENDAR] Time slot conflict in single calendar")
                        await self._speak(
                            "I'm sorry, but that time slot is already occupied. Could you suggest an alternative time?"
                        )
                        return

                    calendar_account_id_for_booking = self.calendar_account_ids[0]

                elif self.calendar_account_id:
                    calendar_account_id_for_booking = self.calendar_account_id

                if not calendar_account_id_for_booking:
                    logger.warning("[ULTRA-CALENDAR] No calendar account available")
                    return

                # Book the appointment
                event_id = await calendar_service.book_inbound_appointment(
                    call_sid=self.call_sid or "ultra_stream",
                    user_id=self.user_id,
                    assistant_id=self.assistant_id,
                    appointment=appointment,
                    provider=provider,
                    calendar_account_id=str(calendar_account_id_for_booking),
                )

                if event_id:
                    self.appointment_scheduled = True
                    self.appointment_metadata = {
                        "event_id": event_id,
                        "appointment": appointment,
                        "calendar_account_id": str(calendar_account_id_for_booking),
                    }
                    logger.info(f"[ULTRA-CALENDAR] ✅ Appointment booked! Event ID: {event_id}")

                    # Update call log
                    if self.call_sid:
                        try:
                            from app.config.database import Database
                            db = Database.get_db()
                            db['call_logs'].update_one(
                                {"call_sid": self.call_sid},
                                {
                                    "$set": {
                                        "appointment_booked": True,
                                        "appointment_details": self.appointment_metadata,
                                        "updated_at": datetime.now(timezone.utc)
                                    }
                                }
                            )
                        except Exception as e:
                            logger.warning(f"[ULTRA-CALENDAR] Failed to update call log: {e}")
                else:
                    logger.warning("[ULTRA-CALENDAR] Calendar booking returned no event ID")

            except Exception as e:
                logger.error(f"[ULTRA-CALENDAR] ❌ Scheduling error: {e}", exc_info=True)

        # Run in background
        self.scheduling_task = asyncio.create_task(_run_calendar_analysis())

    async def close(self):
        """Close all connections and save execution logs"""
        self.is_running = False

        if self.asr:
            await self.asr.close()
        if self.tts:
            await self.tts.close()

        # Log call quality report at end of call
        if self.quality_monitor:
            quality_report = self.quality_monitor.get_quality_report()
            logger.info(f"[QUALITY] 📊 Call Quality Report:")
            logger.info(f"[QUALITY]   ├─ Overall Score: {quality_report.get('quality', {}).get('overall_quality', 'N/A')}")
            logger.info(f"[QUALITY]   ├─ MOS Score: {quality_report.get('quality', {}).get('mos', 0):.2f}")
            logger.info(f"[QUALITY]   ├─ Network: loss={quality_report.get('network', {}).get('packet_loss_percent', 0):.2f}%, jitter={quality_report.get('network', {}).get('jitter_ms', 0):.1f}ms")
            logger.info(f"[QUALITY]   ├─ Audio: SNR={quality_report.get('audio', {}).get('snr_db', 0):.1f}dB, silence={quality_report.get('audio', {}).get('silence_percent', 0):.1f}%")
            logger.info(f"[QUALITY]   └─ Alerts: {quality_report.get('quality', {}).get('alert_count', 0)} total")
            self.call_quality_report = quality_report

        # Save execution logs to database
        await self._save_execution_logs()

        logger.info("[ULTRA] 🔌 Pipeline closed")

    async def _save_execution_logs(self):
        """Save execution logs and performance metrics to database"""
        try:
            from app.config.database import Database
            db = Database.get_db()
            call_logs_collection = db['call_logs']

            # Calculate performance stats
            first_audio_times = self.metrics.get("first_audio_ms", [])
            total_latencies = self.metrics.get("total_latency_ms", [])

            stats = {}
            if first_audio_times:
                stats["first_audio"] = {
                    "count": len(first_audio_times),
                    "avg_ms": sum(first_audio_times) / len(first_audio_times),
                    "min_ms": min(first_audio_times),
                    "max_ms": max(first_audio_times)
                }
            if total_latencies:
                stats["total_latency"] = {
                    "count": len(total_latencies),
                    "avg_ms": sum(total_latencies) / len(total_latencies),
                    "min_ms": min(total_latencies),
                    "max_ms": max(total_latencies)
                }

            execution_logs = {
                "call_id": self.call_sid,
                "providers": {
                    "asr": self.asr_provider,
                    "tts": self.tts_provider,
                    "llm": self.llm_provider
                },
                "models": {
                    "asr_model": self.asr_model,
                    "tts_model": self.tts_model,
                    "tts_voice": self.tts_voice,
                    "llm_model": self.llm_model
                },
                "performance_metrics": {
                    "total_turns": len(self.conversation_history) // 2,
                    "session_duration_ms": 0,  # Can be calculated if needed
                    "stats": stats,
                    "metrics": []
                },
                "timeline": [],
                "handler_type": "ultra_low_latency",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Build transcript from conversation history (real-time ASR + LLM responses)
            transcript_text = ""
            full_transcript = []
            for msg in self.conversation_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ["user", "assistant"] and content:
                    speaker = "USER" if role == "user" else "ASSISTANT"
                    transcript_text += f"{speaker}: {content}\n"
                    full_transcript.append({
                        "speaker": role,
                        "text": content,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            # Prepare update data
            update_data = {
                "execution_logs": execution_logs,
                # Save the real-time transcript (from Deepgram ASR + LLM responses)
                "transcript": transcript_text,  # Plain text format
                "full_transcript": full_transcript,  # Structured format
                "conversation_log": full_transcript,  # Alias for compatibility
                "transcript_source": "realtime",  # Mark as real-time
                "updated_at": datetime.now(timezone.utc)
            }

            # Add quality report if available
            if hasattr(self, 'call_quality_report') and self.call_quality_report:
                update_data["quality_report"] = self.call_quality_report

            # Try to update existing call log
            result = call_logs_collection.update_one(
                {
                    "$or": [
                        {"call_sid": self.call_sid},
                        {"frejun_call_id": self.call_sid}
                    ]
                },
                {"$set": update_data}
            )

            if result.modified_count > 0:
                logger.info(f"[ULTRA] 💾 Execution logs and real-time transcript saved for call {self.call_sid} ({len(full_transcript)} turns)")
            else:
                logger.warning(f"[ULTRA] ⚠️ Call log not found for {self.call_sid}")

        except Exception as e:
            logger.error(f"[ULTRA] ❌ Error saving execution logs: {e}", exc_info=True)


async def handle_ultra_low_latency_stream(
    websocket: WebSocket,
    assistant_config: Dict[str, Any],
    provider_keys: Dict[str, str]
):
    """
    Entry point for streaming pipeline.

    Required provider_keys:
    - deepgram: Deepgram API key (for ASR)
    - openai OR groq: LLM provider key
    - elevenlabs OR sarvam: TTS provider key

    Configurable assistant_config options:
    - asr_model: Deepgram model (default: nova-3)
    - asr_language: ASR language (default: en)
    - llm_provider: openai or groq (default: openai)
    - llm_model: LLM model name
    - tts_provider: elevenlabs or sarvam (default: elevenlabs)
    - tts_model: TTS model name
    - tts_voice: Voice name or ID

    ElevenLabs options:
    - tts_stability: Voice stability 0-1
    - tts_similarity_boost: Voice clarity 0-1

    Sarvam options:
    - bot_language: Language code (hi-IN, bn-IN, etc.)
    - tts_pitch: Voice pitch -1 to 1
    - tts_loudness: Volume 0.5 to 2.0

    General options:
    - temperature: LLM temperature
    - llm_max_tokens: Max response tokens
    - system_message: System prompt
    - greeting: Initial greeting
    """
    handler = UltraLowLatencyHandler(websocket, assistant_config, provider_keys)

    try:
        await handler.initialize()
        await handler.start()

        while handler.is_running:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=300
                )
                await handler.handle_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[ULTRA] Error: {e}")
                break

    finally:
        await handler.close()
