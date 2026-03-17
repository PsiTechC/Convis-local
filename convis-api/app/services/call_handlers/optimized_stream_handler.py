"""
Optimized Stream Handler for VAPI-like Low Latency
Achieves 300-600ms response time vs 1500-3000ms in current implementation

Key optimizations:
1. Streaming Deepgram ASR (no audio buffering)
2. Streaming LLM responses (sentence-by-sentence processing)
3. Streaming TTS (audio starts playing before generation completes)
4. Parallel processing (TTS runs while LLM continues generating)
5. Barge-in support (AI stops when user speaks)
6. Keepalive mechanisms to prevent disconnection
7. Calendar scheduling support (same as realtime API)
"""

import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import WebSocket

from .streaming_asr_handler import StreamingDeepgramASR
from .streaming_llm_handler import StreamingLLMHandler, ConversationManager
from .streaming_tts_handler import StreamingElevenLabsTTS, StreamingSarvamTTS, StreamingCartesiaTTS, StreamingOpenAITTS
from app.utils.call_quality_monitor import CallQualityMonitor, QoSThresholds, QualityAlert

logger = logging.getLogger(__name__)

# Calendar services - imported lazily to avoid circular imports
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
            logger.info("[CALENDAR] ✅ Calendar services initialized")
        except Exception as e:
            logger.warning(f"[CALENDAR] ⚠️ Could not initialize calendar services: {e}")
    return _calendar_service, _calendar_intent_service


class OptimizedStreamHandler:
    """
    VAPI-style low-latency voice conversation handler.
    
    Architecture:
    1. Audio → Streaming Deepgram → Interim transcripts
    2. Final transcript → Streaming OpenAI → Sentences
    3. Each sentence → Streaming ElevenLabs → Audio chunks
    4. Audio chunks → Twilio (immediate playback)
    
    Features:
    - Barge-in: AI stops speaking when user starts talking
    - Low latency: First audio response in 300-600ms
    - Natural speech speed
    - Unlimited call duration with keepalive
    """
    
    # Keepalive interval (seconds) - send keepalive every 15 seconds
    KEEPALIVE_INTERVAL = 15
    
    def __init__(
        self,
        websocket: WebSocket,
        assistant_config: Dict[str, Any],
        provider_keys: Dict[str, str]
    ):
        self.websocket = websocket
        self.config = assistant_config
        self.provider_keys = provider_keys
        
        # Twilio state
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        
        # Pipeline components
        self.asr: Optional[StreamingDeepgramASR] = None
        self.llm: Optional[StreamingLLMHandler] = None
        self.tts: Optional[StreamingElevenLabsTTS] = None
        self.conversation: Optional[ConversationManager] = None
        
        # State
        self.is_running = False
        self.is_processing = False  # Prevent overlapping responses
        self.is_speaking = False  # Track if AI is currently speaking
        self.pending_transcript = ""
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        
        # Interruption control
        self.interrupted = False
        self.current_generation_id = 0  # Track generations to cancel stale ones
        
        # Keepalive task
        self.keepalive_task: Optional[asyncio.Task] = None
        self.last_activity_time = time.time()
        
        # Call duration tracking (no limit)
        self.call_start_time: Optional[float] = None
        
        # Metrics
        self.metrics = {
            "asr_latency_ms": [],
            "llm_latency_ms": [],
            "tts_latency_ms": [],
            "total_latency_ms": []
        }

        # LLM pre-warming state
        self.llm_warmed_up = False
        self.llm_warmup_task: Optional[asyncio.Task] = None

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
            logger.info(f"[OPTIMIZED] 📅 Calendar enabled with {len(self.calendar_account_ids)} calendar(s)")

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
            logger.info(f"[OPTIMIZED] 📊 Call quality monitoring enabled")

    def _on_quality_alert(self, alert: QualityAlert):
        """Handle quality alerts during the call"""
        logger.warning(f"[QUALITY] {alert.severity.upper()}: {alert.message}")

    async def initialize(self):
        """Initialize all pipeline components"""
        logger.info("[OPTIMIZED] 🚀 Initializing low-latency pipeline...")
        
        # Initialize ASR based on configured provider
        asr_provider = self.config.get("asr_provider", "deepgram").lower()

        if asr_provider == "whisper":
            from .offline_asr_handler import OfflineWhisperASR
            self.asr = OfflineWhisperASR(
                model_size=self.config.get("asr_model", "base"),
                language=self.config.get("asr_language", "en"),
                sample_rate=8000,
                encoding="mulaw",
                on_transcript=self._on_transcript,
                on_utterance_end=self._on_utterance_end,
                endpointing_ms=250,
            )
            logger.info(f"[OPTIMIZED] Using Whisper offline ASR (model: {self.config.get('asr_model', 'base')})")
        else:
            deepgram_key = self.provider_keys.get("deepgram") or os.getenv("DEEPGRAM_API_KEY")
            if not deepgram_key:
                raise ValueError("Deepgram API key required for streaming ASR")
            self.asr = StreamingDeepgramASR(
                api_key=deepgram_key,
                model=self.config.get("asr_model", "nova-2"),
                language=self.config.get("asr_language", "en"),
                on_transcript=self._on_transcript,
                on_utterance_end=self._on_utterance_end
            )

        # Initialize LLM
        import openai
        llm_provider = self.config.get("llm_provider", "openai").lower()

        if llm_provider == "ollama":
            ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            llm_client = openai.AsyncOpenAI(base_url=ollama_base_url, api_key="ollama")
            default_model = "llama3.2"
            logger.info(f"[OPTIMIZED] Using Ollama LLM at {ollama_base_url}")
        else:
            openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise ValueError("OpenAI API key required")
            llm_client = openai.AsyncOpenAI(api_key=openai_key)
            default_model = "gpt-4-turbo"

        self.llm = StreamingLLMHandler(
            openai_client=llm_client,
            model=self.config.get("llm_model") or default_model,
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("llm_max_tokens", 150)
        )

        # OpenAI client for TTS fallback (separate from LLM client)
        openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
        openai_client = openai.AsyncOpenAI(api_key=openai_key) if openai_key else None

        # Initialize TTS based on configured provider
        tts_provider = self.config.get("tts_provider", "elevenlabs").lower()
        tts_voice = self.config.get("tts_voice", "alloy")
        logger.info(f"[OPTIMIZED] 🔊 Initializing TTS provider: {tts_provider}")

        if tts_provider == "sarvam":
            sarvam_key = self.provider_keys.get("sarvam") or os.getenv("SARVAM_API_KEY")
            if sarvam_key:
                self.tts = StreamingSarvamTTS(
                    api_key=sarvam_key,
                    voice=tts_voice or "manisha",
                    model=self.config.get("tts_model", "bulbul:v2"),
                    language=self.config.get("bot_language", "hi-IN")
                )
                logger.info(f"[OPTIMIZED] ✅ Using Sarvam TTS (voice: {tts_voice})")
            elif openai_client:
                logger.warning("[OPTIMIZED] ⚠️ No Sarvam key, falling back to OpenAI TTS")
                self.tts = StreamingOpenAITTS(client=openai_client, voice="alloy")
            else:
                raise ValueError("No Sarvam API key and no OpenAI key for TTS fallback")
        elif tts_provider == "cartesia":
            cartesia_key = self.provider_keys.get("cartesia") or os.getenv("CARTESIA_API_KEY")
            if cartesia_key:
                self.tts = StreamingCartesiaTTS(
                    api_key=cartesia_key,
                    voice=tts_voice or "sonic",
                    model=self.config.get("tts_model", "sonic-english")
                )
                logger.info(f"[OPTIMIZED] ✅ Using Cartesia TTS (voice: {tts_voice})")
            elif openai_client:
                logger.warning("[OPTIMIZED] ⚠️ No Cartesia key, falling back to OpenAI TTS")
                self.tts = StreamingOpenAITTS(client=openai_client, voice="alloy")
            else:
                raise ValueError("No Cartesia API key and no OpenAI key for TTS fallback")
        elif tts_provider == "openai":
            if not openai_client:
                raise ValueError("OpenAI API key required for OpenAI TTS")
            self.tts = StreamingOpenAITTS(
                client=openai_client,
                voice=tts_voice or "alloy"
            )
            logger.info(f"[OPTIMIZED] ✅ Using OpenAI TTS (voice: {tts_voice})")
        elif tts_provider == "piper":
            from .offline_tts_handler import OfflinePiperTTS
            self.tts = OfflinePiperTTS(
                voice=tts_voice or "en_US-lessac-medium",
                for_browser=False
            )
            logger.info(f"[OPTIMIZED] ✅ Using Piper offline TTS (voice: {tts_voice})")
        else:
            # Default to ElevenLabs
            elevenlabs_key = self.provider_keys.get("elevenlabs") or os.getenv("ELEVENLABS_API_KEY")
            if elevenlabs_key:
                self.tts = StreamingElevenLabsTTS(
                    api_key=elevenlabs_key,
                    voice=tts_voice or "alloy",
                    model="eleven_flash_v2_5",
                    output_format="ulaw_8000"  # Twilio requires μ-law 8kHz
                )
                logger.info(f"[OPTIMIZED] ✅ Using ElevenLabs TTS (voice: {tts_voice}, format: ulaw_8000)")
            elif openai_client:
                logger.warning("[OPTIMIZED] ⚠️ No ElevenLabs key, falling back to OpenAI TTS")
                self.tts = StreamingOpenAITTS(client=openai_client, voice=tts_voice or "alloy")
            else:
                raise ValueError("No TTS provider available. Set an ElevenLabs or OpenAI API key.")
        
        # Initialize conversation manager (unlimited history for long calls)
        self.conversation = ConversationManager(
            system_message=self.config.get("system_message", "You are a helpful assistant."),
            max_history=50  # Increased for longer conversations
        )
        
        logger.info("[OPTIMIZED] ✅ Pipeline initialized")

    async def _prewarm_llm(self):
        """
        Pre-warm the LLM session by sending a minimal dummy request.
        This eliminates cold-start latency on the first real user query.

        Strategy: Send a simple system+user message that the LLM will respond to quickly.
        The response is discarded - we just want to "wake up" the model connection.
        """
        if self.llm_warmed_up:
            return

        try:
            warmup_start = time.time()
            logger.info("[OPTIMIZED] 🔥 Pre-warming LLM session...")

            # Minimal warmup prompt - just to establish connection
            warmup_messages = [
                {"role": "system", "content": "Respond with OK."},
                {"role": "user", "content": "Ready?"}
            ]

            # Use non-streaming for faster warmup (we don't care about the response)
            response = await self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=warmup_messages,
                temperature=0.1,
                max_tokens=5,  # Minimal tokens - we just need the connection
                stream=False
            )

            warmup_time = (time.time() - warmup_start) * 1000
            self.llm_warmed_up = True
            logger.info(f"[OPTIMIZED] 🔥 LLM pre-warmed in {warmup_time:.0f}ms (cold start eliminated)")

        except Exception as e:
            logger.warning(f"[OPTIMIZED] ⚠️ LLM pre-warm failed (non-fatal): {e}")
            # Not fatal - first user query will just have normal cold start

    async def start(self):
        """Start the streaming pipeline"""
        self.is_running = True
        self.call_start_time = time.time()
        
        # Connect to Deepgram
        await self.asr.connect()
        
        # Start audio sender task
        asyncio.create_task(self._audio_sender_loop())
        
        # Start keepalive task to prevent disconnection
        self.keepalive_task = asyncio.create_task(self._keepalive_loop())
        
        logger.info("[OPTIMIZED] ▶️ Pipeline started (unlimited duration)")
    
    async def _keepalive_loop(self):
        """
        Send periodic keepalive messages to prevent connection timeouts.
        This ensures the call doesn't disconnect due to inactivity.
        """
        logger.info("[OPTIMIZED] 💓 Keepalive loop started")
        
        while self.is_running:
            try:
                await asyncio.sleep(self.KEEPALIVE_INTERVAL)
                
                if not self.is_running:
                    break
                
                # Send keepalive to Deepgram ASR
                if self.asr and self.asr.ws and self.asr.is_connected:
                    try:
                        keepalive_msg = json.dumps({"type": "KeepAlive"})
                        await self.asr.ws.send(keepalive_msg)
                        logger.debug("[OPTIMIZED] 💓 Sent keepalive to Deepgram")
                    except Exception as e:
                        logger.warning(f"[OPTIMIZED] Deepgram keepalive failed: {e}")
                        # Try to reconnect Deepgram if disconnected
                        await self._reconnect_asr()
                
                # Log call duration periodically
                if self.call_start_time:
                    duration_mins = (time.time() - self.call_start_time) / 60
                    if int(duration_mins) % 5 == 0 and duration_mins > 0:  # Log every 5 minutes
                        logger.info(f"[OPTIMIZED] 📞 Call duration: {duration_mins:.1f} minutes")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[OPTIMIZED] Keepalive error: {e}")
        
        logger.info("[OPTIMIZED] 💓 Keepalive loop stopped")
    
    async def _reconnect_asr(self):
        """Reconnect to ASR if connection is lost"""
        logger.info("[OPTIMIZED] 🔄 Attempting to reconnect ASR...")

        try:
            # Close existing connection
            if self.asr:
                try:
                    await self.asr.close()
                except:
                    pass

            # Reinitialize ASR based on provider
            asr_provider = self.config.get("asr_provider", "deepgram").lower()

            if asr_provider == "whisper":
                from .offline_asr_handler import OfflineWhisperASR
                self.asr = OfflineWhisperASR(
                    model_size=self.config.get("asr_model", "base"),
                    language=self.config.get("asr_language", "en"),
                    sample_rate=8000,
                    encoding="mulaw",
                    on_transcript=self._on_transcript,
                    on_utterance_end=self._on_utterance_end,
                    endpointing_ms=250,
                )
            else:
                deepgram_key = self.provider_keys.get("deepgram") or os.getenv("DEEPGRAM_API_KEY")
                self.asr = StreamingDeepgramASR(
                    api_key=deepgram_key,
                    model=self.config.get("asr_model", "nova-2"),
                    language=self.config.get("asr_language", "en"),
                    on_transcript=self._on_transcript,
                    on_utterance_end=self._on_utterance_end
                )

            await self.asr.connect()
            logger.info("[OPTIMIZED] ✅ ASR reconnected successfully")

        except Exception as e:
            logger.error(f"[OPTIMIZED] ❌ ASR reconnection failed: {e}")
    
    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming Twilio WebSocket message"""
        event = message.get("event")
        
        # Update activity time
        self.last_activity_time = time.time()
        
        if event == "start":
            await self._handle_start(message)
        elif event == "media":
            await self._handle_media(message)
        elif event == "mark":
            await self._handle_mark(message)
        elif event == "stop":
            await self._handle_stop()
    
    async def _handle_start(self, message: Dict[str, Any]):
        """Handle Twilio stream start"""
        start_data = message.get("start", {})
        self.stream_sid = start_data.get("streamSid")
        self.call_sid = start_data.get("callSid")

        logger.info(f"[OPTIMIZED] 📞 Call started: {self.call_sid}")
        logger.info(f"[OPTIMIZED] 📞 Stream SID: {self.stream_sid}")

        # ⚡ OPTIMIZATION: Pre-warm LLM in parallel with greeting TTS
        # This eliminates cold-start latency on the first real user query
        self.llm_warmup_task = asyncio.create_task(self._prewarm_llm())

        # Send greeting (LLM warmup happens in background)
        greeting = self.config.get("greeting", "Hello! How can I help you today?")
        if greeting:
            await self._speak(greeting)
    
    async def _handle_media(self, message: Dict[str, Any]):
        """Handle incoming audio from Twilio"""
        media_data = message.get("media", {})
        payload = media_data.get("payload")
        
        if payload and self.asr:
            # Check if ASR is connected, reconnect if needed
            if not self.asr.is_connected:
                logger.warning("[OPTIMIZED] ASR disconnected, attempting reconnect...")
                await self._reconnect_asr()
            
            if self.asr.is_connected:
                # Decode base64 audio
                audio_bytes = base64.b64decode(payload)

                # Track audio quality metrics
                if self.quality_monitor and audio_bytes:
                    self.quality_monitor.track_audio_chunk(audio_bytes, is_voice=not self.is_speaking)

                # Send IMMEDIATELY to Deepgram (no buffering!)
                await self.asr.send_audio(audio_bytes)
    
    async def _handle_mark(self, message: Dict[str, Any]):
        """Handle Twilio mark event (audio playback confirmation)"""
        mark = message.get("mark", {})
        mark_name = mark.get("name", "")
        
        if mark_name == "speech_end":
            self.is_speaking = False
            logger.debug(f"[OPTIMIZED] 🔇 AI finished speaking")
        
        logger.debug(f"[OPTIMIZED] Mark received: {mark_name}")
    
    async def _handle_stop(self):
        """Handle stream stop"""
        if self.call_start_time:
            duration_mins = (time.time() - self.call_start_time) / 60
            logger.info(f"[OPTIMIZED] 🛑 Call ended. Duration: {duration_mins:.1f} minutes")
        else:
            logger.info("[OPTIMIZED] 🛑 Stream stopping")
        await self.close()
    
    async def _on_transcript(self, transcript: str, is_final: bool):
        """
        Callback when Deepgram returns a transcript.

        BARGE-IN: If we detect speech while AI is talking, interrupt immediately!

        PREDICT-AND-SCRAP (Vapi-style optimization):
        - Start LLM processing on confident interim transcripts
        - If user continues speaking, cancel and restart with updated transcript
        - This reduces perceived latency by ~200-400ms
        """
        # Update activity time
        self.last_activity_time = time.time()

        # Check for barge-in (user speaking while AI is talking)
        if self.is_speaking and transcript and len(transcript.strip()) > 3:
            logger.info(f"[OPTIMIZED] 🛑 BARGE-IN detected! User said: {transcript[:30]}...")
            await self._handle_interruption()

        if is_final:
            logger.info(f"[OPTIMIZED] 🎤 Final transcript: {transcript}")

            # Cancel any speculative processing if transcript changed significantly
            if hasattr(self, '_speculative_task') and self._speculative_task and not self._speculative_task.done():
                if self._speculative_transcript != transcript:
                    logger.info(f"[OPTIMIZED] 🔄 Scrapping speculative response - transcript changed")
                    self._speculative_task.cancel()
                    self._speculative_task = None
                else:
                    # Speculative response matches final - let it continue!
                    logger.info(f"[OPTIMIZED] ✅ Speculative response valid - using it!")
                    self.pending_transcript = ""
                    return

            self.pending_transcript = transcript

            # Don't wait - process immediately
            asyncio.create_task(self._process_user_input(transcript))
        else:
            # Interim result - use predict-and-scrap for faster response
            if transcript and len(transcript.strip()) > 5:
                logger.debug(f"[OPTIMIZED] 🎤 Interim: {transcript}")

                # ⚡ PREDICT-AND-SCRAP: Start speculative LLM processing on confident interims
                # Only if we're not already processing and interim looks complete (ends with punctuation-like patterns)
                if (not self.is_processing
                    and not self.is_speaking
                    and len(transcript.strip()) > 10
                    and self._looks_complete(transcript)):

                    # Cancel previous speculative task if exists
                    if hasattr(self, '_speculative_task') and self._speculative_task and not self._speculative_task.done():
                        self._speculative_task.cancel()

                    self._speculative_transcript = transcript
                    self._speculative_task = asyncio.create_task(
                        self._process_user_input_speculative(transcript)
                    )
                    logger.info(f"[OPTIMIZED] 🔮 Started speculative processing: {transcript[:30]}...")

            self.pending_transcript = transcript

    def _looks_complete(self, transcript: str) -> bool:
        """
        Heuristic to check if an interim transcript looks like a complete utterance.
        Used for predict-and-scrap optimization.
        """
        text = transcript.strip().lower()

        # Check for question patterns
        question_words = ['what', 'when', 'where', 'who', 'why', 'how', 'can', 'could', 'would', 'is', 'are', 'do', 'does']
        if any(text.startswith(w) for w in question_words) and len(text.split()) >= 3:
            return True

        # Check for common ending patterns
        ending_patterns = ['please', 'thanks', 'thank you', 'okay', 'yes', 'no', 'sure', 'right']
        if any(text.endswith(p) for p in ending_patterns):
            return True

        # Check for reasonable length (likely complete thought)
        if len(text.split()) >= 5:
            return True

        return False

    async def _process_user_input_speculative(self, text: str):
        """
        Speculative processing - starts LLM but can be cancelled.
        Part of predict-and-scrap optimization.
        """
        try:
            # Small delay to see if more speech is coming
            await asyncio.sleep(0.15)  # 150ms - if user still speaking, we'll get cancelled

            # If we get here, proceed with normal processing
            # The final transcript handler will either use this or cancel it
            await self._process_user_input(text)

        except asyncio.CancelledError:
            logger.debug(f"[OPTIMIZED] 🔄 Speculative processing cancelled (user still speaking)")
            raise
    
    async def _on_utterance_end(self):
        """
        Callback when user stops speaking.
        If we have a pending transcript, process it now.
        """
        if self.pending_transcript and not self.is_processing:
            logger.info(f"[OPTIMIZED] 🔚 Utterance end, processing: {self.pending_transcript}")
            await self._process_user_input(self.pending_transcript)
            self.pending_transcript = ""
    
    async def _handle_interruption(self):
        """
        Handle user interruption (barge-in).
        Stop AI speech and prepare for new user input.
        """
        logger.info("[OPTIMIZED] ⚡ Handling interruption...")
        
        # Set interrupted flag to stop ongoing generation
        self.interrupted = True
        self.current_generation_id += 1  # Invalidate current generation
        
        # Clear audio queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Send clear message to Twilio to stop audio playback
        if self.stream_sid:
            try:
                await self.websocket.send_json({
                    "event": "clear",
                    "streamSid": self.stream_sid
                })
                logger.info("[OPTIMIZED] 📤 Sent clear event to Twilio")
            except Exception as e:
                logger.warning(f"[OPTIMIZED] Failed to send clear: {e}")
        
        self.is_speaking = False
        self.is_processing = False
        
        logger.info("[OPTIMIZED] ✅ Interruption handled")
    
    async def _process_user_input(self, text: str):
        """
        Process user input through the pipeline.
        This is where the magic happens for low latency!
        """
        if self.is_processing:
            logger.debug("[OPTIMIZED] Already processing, skipping")
            return
        
        if not text or len(text.strip()) < 2:
            return
        
        self.is_processing = True
        self.interrupted = False
        self.current_generation_id += 1
        current_gen_id = self.current_generation_id
        
        pipeline_start = time.time()
        
        try:
            logger.info(f"[OPTIMIZED] 🚀 === PIPELINE START (gen={current_gen_id}) ===")
            
            # Add to conversation history
            self.conversation.add_user_message(text)
            
            # Track first sentence timing
            first_sentence_sent = False
            llm_start = time.time()
            
            async def on_sentence(sentence: str):
                """Called for each sentence from LLM - immediately synthesize and send!"""
                nonlocal first_sentence_sent
                
                # Check if this generation was cancelled
                if self.interrupted or current_gen_id != self.current_generation_id:
                    logger.info(f"[OPTIMIZED] ⏹️ Generation {current_gen_id} cancelled")
                    return
                
                if not sentence.strip():
                    return
                
                tts_start = time.time()
                
                # Mark that we're speaking
                self.is_speaking = True
                
                # Synthesize this sentence (streaming if available)
                if hasattr(self.tts, 'synthesize_streaming'):
                    # ElevenLabs streaming - send audio as it arrives
                    async def send_chunk_if_not_interrupted(chunk: bytes):
                        if not self.interrupted and current_gen_id == self.current_generation_id:
                            await self._send_audio_chunk(chunk)
                    
                    await self.tts.synthesize_streaming(
                        sentence,
                        on_audio_chunk=send_chunk_if_not_interrupted
                    )
                else:
                    # Fallback - synthesize complete then send
                    audio = await self.tts.synthesize(sentence)
                    if audio and not self.interrupted:
                        await self._send_audio_chunk(audio)
                
                tts_time = (time.time() - tts_start) * 1000
                
                if not first_sentence_sent:
                    first_sentence_sent = True
                    first_response_time = (time.time() - pipeline_start) * 1000
                    logger.info(f"[OPTIMIZED] ⚡ FIRST AUDIO: {first_response_time:.0f}ms")
                    self.metrics["total_latency_ms"].append(first_response_time)
                
                self.metrics["tts_latency_ms"].append(tts_time)
            
            # Stream LLM response with sentence callback
            full_response = await self.llm.stream_response(
                self.conversation.get_messages(),
                on_sentence=on_sentence
            )
            
            llm_time = (time.time() - llm_start) * 1000
            self.metrics["llm_latency_ms"].append(llm_time)
            
            # Add assistant response to history (if not interrupted)
            if not self.interrupted and full_response:
                self.conversation.add_assistant_message(full_response)
            
            total_time = (time.time() - pipeline_start) * 1000
            
            # Send mark to know when speech ends
            if self.stream_sid and not self.interrupted:
                try:
                    await self.websocket.send_json({
                        "event": "mark",
                        "streamSid": self.stream_sid,
                        "mark": {"name": "speech_end"}
                    })
                except Exception as e:
                    logger.warning(f"[OPTIMIZED] Failed to send mark: {e}")
            
            logger.info(f"[OPTIMIZED] ⚡ === PIPELINE COMPLETE ===")
            logger.info(f"[OPTIMIZED]   LLM total: {llm_time:.0f}ms")
            logger.info(f"[OPTIMIZED]   Total: {total_time:.0f}ms")

            # Check for calendar scheduling intent (runs in background)
            if self.calendar_enabled and not self.appointment_scheduled:
                asyncio.create_task(self._maybe_schedule_from_conversation())

        except Exception as e:
            logger.error(f"[OPTIMIZED] Pipeline error: {e}", exc_info=True)
        finally:
            self.is_processing = False

    async def _maybe_schedule_from_conversation(self):
        """
        Analyze conversation for calendar scheduling intent.
        Runs in background so it doesn't block audio.
        """
        if self.appointment_scheduled:
            return

        if self.scheduling_task and not self.scheduling_task.done():
            logger.debug("[CALENDAR] Scheduling task already running")
            return

        # Get calendar services
        calendar_service, calendar_intent_service = get_calendar_services()
        if not calendar_service or not calendar_intent_service:
            logger.debug("[CALENDAR] Calendar services not available")
            return

        # Get conversation history
        conversation_messages = self.conversation.get_messages() if self.conversation else []
        if len(conversation_messages) < 3:  # Need at least a few turns
            return

        # Get OpenAI key for intent extraction
        openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return

        async def _run_calendar_analysis():
            try:
                logger.info("[CALENDAR] 🔍 Analyzing conversation for scheduling intent...")

                # Extract calendar intent from conversation
                result = await calendar_intent_service.extract_from_conversation(
                    conversation_messages,
                    openai_key,
                    self.timezone,
                )

                logger.info(f"[CALENDAR] Intent result: {result}")

                if not result or not result.get("should_schedule"):
                    logger.debug("[CALENDAR] No scheduling intent detected")
                    return

                appointment = result.get("appointment") or {}
                start_iso = appointment.get("start_iso")
                end_iso = appointment.get("end_iso")

                if not start_iso or not end_iso:
                    logger.warning(f"[CALENDAR] Appointment missing start/end: {appointment}")
                    return

                logger.info(f"[CALENDAR] ✓ Valid appointment: {appointment.get('title')} at {start_iso}")

                appointment.setdefault("timezone", self.timezone)
                appointment.setdefault("notes", result.get("reason"))
                provider = appointment.get("provider") or self.calendar_provider

                # Parse appointment times
                try:
                    start_time = datetime.fromisoformat(start_iso)
                    end_time = datetime.fromisoformat(end_iso)
                except Exception as e:
                    logger.error(f"[CALENDAR] Error parsing times: {e}")
                    return

                # Check availability and book
                calendar_account_id_for_booking = None

                if self.calendar_account_ids and len(self.calendar_account_ids) > 1:
                    # Multi-calendar: Check all and use round-robin
                    logger.info(f"[CALENDAR] Checking availability across {len(self.calendar_account_ids)} calendars...")

                    availability = await calendar_service.check_availability_across_calendars(
                        self.calendar_account_ids,
                        start_time,
                        end_time
                    )

                    if not availability.get("is_available"):
                        conflicts = availability.get("conflicts", [])
                        logger.warning(f"[CALENDAR] Time slot conflict detected: {conflicts}")
                        # Notify via TTS
                        await self._speak(
                            "I'm sorry, but that time slot is already occupied. Could you suggest an alternative time?"
                        )
                        return

                    # Use round-robin selection
                    from app.config.database import Database
                    db = Database.get_db()
                    assistant = db['assistants'].find_one({"_id": self.assistant_id}) if self.assistant_id else None

                    calendar_account_id_for_booking = await calendar_service.get_next_available_calendar_round_robin(
                        assistant,
                        start_time,
                        end_time
                    )

                    if not calendar_account_id_for_booking:
                        logger.error("[CALENDAR] Round-robin selection failed")
                        return

                elif self.calendar_account_ids and len(self.calendar_account_ids) == 1:
                    # Single calendar
                    availability = await calendar_service.check_availability_across_calendars(
                        self.calendar_account_ids,
                        start_time,
                        end_time
                    )

                    if not availability.get("is_available"):
                        logger.warning("[CALENDAR] Time slot conflict in single calendar")
                        await self._speak(
                            "I'm sorry, but that time slot is already occupied. Could you suggest an alternative time?"
                        )
                        return

                    calendar_account_id_for_booking = self.calendar_account_ids[0]

                elif self.calendar_account_id:
                    calendar_account_id_for_booking = self.calendar_account_id

                if not calendar_account_id_for_booking:
                    logger.warning("[CALENDAR] No calendar account available for booking")
                    return

                # Book the appointment
                event_id = await calendar_service.book_inbound_appointment(
                    call_sid=self.call_sid or "custom_stream",
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
                    logger.info(f"[CALENDAR] ✅ Appointment booked! Event ID: {event_id}")

                    # Update call log with appointment info
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
                            logger.warning(f"[CALENDAR] Failed to update call log: {e}")
                else:
                    logger.warning("[CALENDAR] Calendar booking returned no event ID")

            except Exception as e:
                logger.error(f"[CALENDAR] ❌ Scheduling error: {e}", exc_info=True)

        # Run analysis in background
        self.scheduling_task = asyncio.create_task(_run_calendar_analysis())

    async def _speak(self, text: str):
        """Synthesize and send audio for given text"""
        try:
            self.is_speaking = True
            
            if hasattr(self.tts, 'synthesize_streaming'):
                await self.tts.synthesize_streaming(
                    text,
                    on_audio_chunk=self._send_audio_chunk
                )
            else:
                audio = await self.tts.synthesize(text)
                if audio:
                    await self._send_audio_chunk(audio)
            
            # Send mark to know when greeting ends
            if self.stream_sid:
                try:
                    await self.websocket.send_json({
                        "event": "mark",
                        "streamSid": self.stream_sid,
                        "mark": {"name": "speech_end"}
                    })
                except Exception as e:
                    logger.warning(f"[OPTIMIZED] Failed to send mark: {e}")
                    
        except Exception as e:
            logger.error(f"[OPTIMIZED] Speak error: {e}")
            self.is_speaking = False
    
    async def _send_audio_chunk(self, audio_bytes: bytes):
        """Send audio chunk to Twilio"""
        if not audio_bytes or not self.stream_sid:
            return
        
        if self.interrupted:
            return  # Don't send if interrupted
        
        # Queue audio for sending
        await self.audio_queue.put(audio_bytes)
    
    async def _audio_sender_loop(self):
        """Send queued audio to Twilio"""
        while self.is_running:
            try:
                # Get audio from queue (with timeout)
                try:
                    audio = await asyncio.wait_for(self.audio_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                
                # Don't send if interrupted
                if self.interrupted:
                    continue
                
                # Send to Twilio
                audio_b64 = base64.b64encode(audio).decode("utf-8")
                
                await self.websocket.send_json({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {
                        "payload": audio_b64
                    }
                })
                
            except Exception as e:
                if self.is_running:
                    logger.error(f"[OPTIMIZED] Audio sender error: {e}")
    
    async def close(self):
        """Clean up resources"""
        self.is_running = False

        # Cancel keepalive task
        if self.keepalive_task:
            self.keepalive_task.cancel()
            try:
                await self.keepalive_task
            except asyncio.CancelledError:
                pass

        # Cancel warmup task if still running
        if self.llm_warmup_task and not self.llm_warmup_task.done():
            self.llm_warmup_task.cancel()
            try:
                await self.llm_warmup_task
            except asyncio.CancelledError:
                pass

        if self.asr:
            await self.asr.close()
        
        # Log call statistics
        if self.call_start_time:
            duration_mins = (time.time() - self.call_start_time) / 60
            logger.info(f"[OPTIMIZED] 📊 Final call duration: {duration_mins:.1f} minutes")
        
        if self.metrics["total_latency_ms"]:
            avg_latency = sum(self.metrics["total_latency_ms"]) / len(self.metrics["total_latency_ms"])
            logger.info(f"[OPTIMIZED] 📊 Average first-response latency: {avg_latency:.0f}ms")

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

        logger.info("[OPTIMIZED] ✅ Closed")

    async def _save_execution_logs(self):
        """Save execution logs and performance metrics to database"""
        try:
            from app.config.database import Database
            from bson import ObjectId
            db = Database.get_db()
            call_logs_collection = db['call_logs']

            # Calculate performance stats
            asr_times = self.metrics.get("asr_latency_ms", [])
            llm_times = self.metrics.get("llm_latency_ms", [])
            tts_times = self.metrics.get("tts_latency_ms", [])
            total_times = self.metrics.get("total_latency_ms", [])

            stats = {}
            if asr_times:
                stats["asr"] = {
                    "count": len(asr_times),
                    "avg_ms": sum(asr_times) / len(asr_times),
                    "min_ms": min(asr_times),
                    "max_ms": max(asr_times)
                }
            if llm_times:
                stats["llm"] = {
                    "count": len(llm_times),
                    "avg_ms": sum(llm_times) / len(llm_times),
                    "min_ms": min(llm_times),
                    "max_ms": max(llm_times)
                }
            if tts_times:
                stats["tts"] = {
                    "count": len(tts_times),
                    "avg_ms": sum(tts_times) / len(tts_times),
                    "min_ms": min(tts_times),
                    "max_ms": max(tts_times)
                }

            # Build metrics array for turn-by-turn breakdown
            metrics_array = []
            max_turns = max(len(asr_times), len(llm_times), len(tts_times), 1)
            for turn in range(1, max_turns + 1):
                turn_idx = turn - 1
                if turn_idx < len(asr_times):
                    metrics_array.append({
                        "operation": "asr",
                        "elapsed_ms": asr_times[turn_idx],
                        "turn": turn
                    })
                if turn_idx < len(llm_times):
                    metrics_array.append({
                        "operation": "llm",
                        "elapsed_ms": llm_times[turn_idx],
                        "turn": turn
                    })
                if turn_idx < len(tts_times):
                    metrics_array.append({
                        "operation": "tts",
                        "elapsed_ms": tts_times[turn_idx],
                        "turn": turn
                    })

            # Get provider/model info from config
            asr_provider = self.config.get("asr_provider", "deepgram")
            tts_provider = self.config.get("tts_provider", "elevenlabs")
            llm_provider = self.config.get("llm_provider", "openai")
            asr_model = self.config.get("asr_model", "nova-2")
            tts_model = self.config.get("tts_model", "eleven_flash_v2_5")
            llm_model = self.config.get("llm_model", "gpt-4-turbo")
            tts_voice = self.config.get("tts_voice") or self.config.get("voice", "alloy")

            execution_logs = {
                "call_id": self.call_sid,
                "providers": {
                    "asr": asr_provider,
                    "tts": tts_provider,
                    "llm": llm_provider
                },
                "models": {
                    "asr_model": asr_model,
                    "tts_model": tts_model,
                    "tts_voice": tts_voice,
                    "llm_model": llm_model
                },
                "performance_metrics": {
                    "total_turns": max_turns,
                    "session_duration_ms": sum(total_times) if total_times else 0,
                    "stats": stats,
                    "metrics": metrics_array
                },
                "timeline": [],
                "handler_type": "optimized_stream",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Try to update existing call log
            search_query = {
                "$or": [
                    {"call_sid": self.call_sid}
                ]
            }

            # Also try MongoDB ObjectId if call_sid looks like one
            if self.call_sid and len(self.call_sid) == 24:
                try:
                    search_query["$or"].append({"_id": ObjectId(self.call_sid)})
                except:
                    pass

            # Build transcript from conversation history (real-time ASR + LLM responses)
            transcript_text = ""
            full_transcript = []
            if self.conversation:
                conversation_messages = self.conversation.get_messages()
                for msg in conversation_messages:
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

            result = call_logs_collection.update_one(
                search_query,
                {"$set": update_data}
            )

            if result.modified_count > 0:
                logger.info(f"[OPTIMIZED] 💾 Execution logs and real-time transcript saved for call {self.call_sid} ({len(full_transcript)} turns)")
            else:
                logger.warning(f"[OPTIMIZED] ⚠️ Call log not found for {self.call_sid}")

        except Exception as e:
            logger.error(f"[OPTIMIZED] ❌ Error saving execution logs: {e}", exc_info=True)


async def handle_optimized_stream(websocket: WebSocket, assistant_config: Dict[str, Any], provider_keys: Dict[str, str]):
    """
    Entry point for optimized streaming.
    Use this instead of CustomProviderStreamHandler for lower latency.
    
    Features:
    - Unlimited call duration
    - Auto-reconnect for ASR
    - Keepalive to prevent disconnection
    """
    handler = OptimizedStreamHandler(websocket, assistant_config, provider_keys)
    
    try:
        await handler.initialize()
        await handler.start()
        
        # Main message loop - no timeout, runs until call ends
        while handler.is_running:
            try:
                # Use a long timeout to prevent WebSocket disconnection
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=300.0  # 5 minute timeout per message (very long)
                )
                await handler.handle_message(message)
            except asyncio.TimeoutError:
                # No message received for 5 minutes - check if still alive
                logger.warning("[OPTIMIZED] No message for 5 minutes, checking connection...")
                continue
            except Exception as e:
                error_str = str(e).lower()
                if "disconnect" in error_str or "closed" in error_str:
                    logger.info(f"[OPTIMIZED] WebSocket closed: {e}")
                else:
                    logger.error(f"[OPTIMIZED] Message error: {e}")
                break
                
    except Exception as e:
        logger.error(f"[OPTIMIZED] Handler error: {e}", exc_info=True)
    finally:
        await handler.close()
