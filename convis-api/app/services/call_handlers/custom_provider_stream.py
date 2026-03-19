"""
Custom Provider WebSocket Streaming Handler
Handles calls using separate ASR and TTS providers (not OpenAI Realtime API)
WITH CALENDAR INTEGRATION SUPPORT
"""

import logging
import asyncio
import json
import base64
try:
    import audioop  # Python < 3.13
except ModuleNotFoundError:
    import audioop_lts as audioop  # Python 3.13+
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from bson import ObjectId

from app.config.database import Database
from app.providers.factory import ProviderFactory
from app.utils.assistant_keys import resolve_provider_keys, resolve_assistant_api_key
from app.utils.twilio_mark_handler import TwilioMarkHandler
from app.services.calendar_service import CalendarService
from app.services.calendar_intent_service import CalendarIntentService
from app.services.realtime_tool_service import RealtimeToolService
from app.utils.call_quality_monitor import CallQualityMonitor, QoSThresholds, QualityAlert

# Try to import Silero VAD (optional dependency for intelligent speech detection)
try:
    from app.utils.silero_vad import SileroVADProcessor
    SILERO_VAD_AVAILABLE = True
except ImportError:
    SILERO_VAD_AVAILABLE = False

logger = logging.getLogger(__name__)

if SILERO_VAD_AVAILABLE:
    logger.info("[CUSTOM] Silero VAD available for intelligent speech detection")
else:
    logger.warning("[CUSTOM] Silero VAD not available, using time-based buffering")


def detect_language_from_text(text: str) -> str:
    """
    Detect language from text using simple heuristics and character patterns.
    Returns ISO language code (e.g., 'en', 'hi', 'es', 'fr', etc.)

    This is a fast, lightweight detection that works for most common languages.
    For more accuracy, could integrate with langdetect library, but this adds dependency.
    """
    if not text or len(text.strip()) < 3:
        return 'en'  # Default to English for very short text

    text = text.lower().strip()

    # Hindi detection - Devanagari script
    if any('\u0900' <= char <= '\u097F' for char in text):
        return 'hi'

    # Spanish indicators
    spanish_words = ['hola', 'gracias', 'por favor', 'sí', 'no', 'cómo', 'qué', 'dónde', 'cuándo']
    if any(word in text for word in spanish_words):
        return 'es'

    # French indicators
    french_words = ['bonjour', 'merci', 's\'il vous plaît', 'oui', 'non', 'comment', 'quoi', 'où', 'quand']
    if any(word in text for word in french_words):
        return 'fr'

    # German indicators
    german_words = ['hallo', 'danke', 'bitte', 'ja', 'nein', 'wie', 'was', 'wo', 'wann']
    if any(word in text for word in german_words):
        return 'de'

    # Portuguese indicators
    portuguese_words = ['olá', 'obrigado', 'por favor', 'sim', 'não', 'como', 'que', 'onde', 'quando']
    if any(word in text for word in portuguese_words):
        return 'pt'

    # Italian indicators
    italian_words = ['ciao', 'grazie', 'per favore', 'sì', 'no', 'come', 'cosa', 'dove', 'quando']
    if any(word in text for word in italian_words):
        return 'it'

    # Arabic detection
    if any('\u0600' <= char <= '\u06FF' for char in text):
        return 'ar'

    # Chinese detection
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        return 'zh'

    # Japanese detection
    if any('\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' for char in text):
        return 'ja'

    # Korean detection
    if any('\uac00' <= char <= '\ud7af' for char in text):
        return 'ko'

    # Default to English
    return 'en'


class CustomProviderStreamHandler:
    """
    Handles bidirectional audio streaming using custom ASR/TTS providers.

    Flow:
    1. Receive audio from FreJun (PCM 8kHz)
    2. Convert speech to text using ASR provider (Deepgram/OpenAI)
    3. Send text to LLM for response (OpenAI GPT-4/etc)
    4. Convert response to speech using TTS provider (Cartesia/ElevenLabs/OpenAI)
    5. Stream audio back to FreJun
    """

    def __init__(
        self,
        websocket: WebSocket,
        assistant_config: Dict[str, Any],
        openai_api_key: Optional[str],
        call_id: str,
        platform: str = "frejun",  # "frejun" or "twilio"
        provider_keys: Optional[Dict[str, str]] = None
    ):
        self.websocket = websocket
        self.assistant_config = assistant_config
        self.call_id = call_id
        self.platform = platform  # Track which platform we're on

        # Provider instances
        self.asr_provider = None
        self.tts_provider = None
        self.llm_client = None

        # Conversation state
        self.conversation_history = []
        self.is_running = False
        self.audio_buffer = bytearray()

        # Call timing and transcript tracking for workflow triggers
        self.call_start_time: Optional[datetime] = None
        self.call_end_time: Optional[datetime] = None
        self.full_transcript: List[Dict[str, str]] = []  # Full transcript with speaker labels

        # Twilio-specific state
        self.stream_sid = None  # Required for Twilio audio streaming
        self.call_sid = None
        self.mark_handler = TwilioMarkHandler(websocket)  # Bolna-style mark event handler

        # Calendar integration state
        self.calendar_enabled = False
        self.calendar_service: Optional[CalendarService] = None
        self.calendar_intent_service: Optional[CalendarIntentService] = None
        self.calendar_account_ids: List[str] = []
        self.scheduling_task: Optional[asyncio.Task] = None
        self.appointment_scheduled = False
        self.appointment_metadata: Dict[str, Any] = {}

        # Pre-synthesized greeting audio (for immediate playback)
        self.greeting_audio_cache: Optional[bytes] = None
        self.greeting_synthesis_task: Optional[asyncio.Task] = None

        # User and assistant IDs for appointment tracking
        self.user_id = assistant_config.get('user_id')
        self.assistant_id = assistant_config.get('assistant_id') or assistant_config.get('_id')

        # API keys
        self.provider_keys = provider_keys or assistant_config.get("provider_keys") or {}
        if openai_api_key:
            self.provider_keys.setdefault("openai", openai_api_key)
        self.openai_api_key = (
            openai_api_key
            or self.provider_keys.get("openai")
            or os.getenv("OPENAI_API_KEY")
        )

        # Configuration
        self.asr_provider_name = assistant_config.get('asr_provider', 'openai')
        self.tts_provider_name = assistant_config.get('tts_provider', 'openai')
        self.voice = assistant_config.get('voice', 'alloy')
        self.tts_voice = assistant_config.get('tts_voice', self.voice)
        self.temperature = assistant_config.get('temperature', 0.8)
        self.system_message = assistant_config.get('system_message', 'You are a helpful AI assistant.')

        # Add language instruction to system message if not English
        self.bot_language = assistant_config.get('bot_language', 'en')
        self.language_names = {
            'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'pt': 'Portuguese', 'it': 'Italian', 'ja': 'Japanese', 'ko': 'Korean',
            'ar': 'Arabic', 'ru': 'Russian', 'zh': 'Chinese', 'nl': 'Dutch',
            'pl': 'Polish', 'tr': 'Turkish'
        }

        if self.bot_language and self.bot_language != 'en':
            language_name = self.language_names.get(self.bot_language, self.bot_language.upper())
            self.system_message = f"{self.system_message}\n\nIMPORTANT: You MUST speak and respond ONLY in {language_name}. All your responses should be in {language_name} language."

        # Get greeting (will be translated to bot_language if needed)
        self.greeting = assistant_config.get('greeting', 'Hello! Thanks for calling. How can I help you today?')
        self.original_greeting = self.greeting  # Store original for reference

        # ASR Configuration
        self.asr_language = assistant_config.get('asr_language', 'en')
        self.asr_model = assistant_config.get('asr_model')
        self.asr_keywords = assistant_config.get('asr_keywords', [])

        # TTS Configuration
        self.tts_model = assistant_config.get('tts_model')
        self.tts_speed = assistant_config.get('tts_speed', 1.0)

        # Transcription & Interruptions
        self.enable_precise_transcript = assistant_config.get('enable_precise_transcript', False)
        self.interruption_threshold = assistant_config.get('interruption_threshold', 2)

        # Real-time interruption detection settings
        # When user speaks while AI is playing, stop AI immediately
        self.enable_interruption = assistant_config.get('enable_interruption', True)
        self.interruption_probability_threshold = assistant_config.get('interruption_probability_threshold', 0.6)
        self.interruption_min_chunks = assistant_config.get('interruption_min_chunks', 2)  # Require 2 consecutive speech chunks
        self._consecutive_speech_chunks = 0  # Counter for consecutive speech detections
        self._is_interrupted = False  # Flag to track if current response was interrupted
        self._last_speech_prob = 0.0  # Track last speech probability for monitoring
        self._is_ai_speaking = False  # Track AI speaking state for FreJun platform

        # Voice Response Rate
        self.response_rate = assistant_config.get('response_rate', 'balanced')

        # User Online Detection
        self.check_user_online = assistant_config.get('check_user_online', True)

        # LLM pre-warming state
        self.llm_warmed_up = False
        self.llm_warmup_task = None

        # Buffer & Latency Settings
        # OPTIMIZED: Reduced from 200ms to 100ms for lower latency
        # Set to 0 for streaming mode (requires streaming ASR)
        self.audio_buffer_size = assistant_config.get('audio_buffer_size', 100)

        # NEW: Enable streaming mode for VAPI-like latency
        self.use_streaming_mode = assistant_config.get('use_streaming_mode', False)

        # Silero VAD Configuration for intelligent speech detection
        # OPTIMIZED: Reduced defaults for faster interruption response
        self.use_vad = assistant_config.get('use_vad', True) and SILERO_VAD_AVAILABLE
        self.vad_processor = None
        self.vad_threshold = assistant_config.get('vad_threshold', 0.4)  # More sensitive (was 0.5)
        self.vad_min_speech_ms = assistant_config.get('vad_min_speech_ms', 150)  # Faster detection (was 250ms)
        self.vad_min_silence_ms = assistant_config.get('vad_min_silence_ms', 200)  # Faster end-of-speech (was 300ms)
        self.min_audio_threshold = 3000  # Reduced from 4KB for faster processing

        if self.use_vad:
            try:
                self.vad_processor = SileroVADProcessor(
                    threshold=self.vad_threshold,
                    min_speech_duration_ms=self.vad_min_speech_ms,
                    min_silence_duration_ms=self.vad_min_silence_ms
                )
                logger.info(f"[CUSTOM] 🎤 VAD enabled: threshold={self.vad_threshold}, "
                           f"min_speech={self.vad_min_speech_ms}ms, min_silence={self.vad_min_silence_ms}ms")
            except Exception as e:
                logger.error(f"[CUSTOM] ❌ Failed to initialize VAD: {e}")
                self.use_vad = False
                self.vad_processor = None

        # LLM Configuration
        self.llm_provider = assistant_config.get('llm_provider', 'openai')
        self.llm_model = assistant_config.get('llm_model')
        self.llm_max_tokens = assistant_config.get('llm_max_tokens', 150)

        # Performance metrics tracking for execution logs
        self.metrics = {
            "asr_times": [],
            "llm_times": [],
            "tts_times": [],
            "total_times": []
        }

        # Workflow Integration - Post-call automation
        self.assigned_workflows = assistant_config.get('assigned_workflows', [])
        self.workflow_trigger_events = assistant_config.get('workflow_trigger_events', ['CALL_COMPLETED'])
        self.call_status = "in_progress"  # Track call status for workflow triggers

        # Real-time Tool Calling (Vapi-like functionality)
        # Tools allow the AI to call webhooks, APIs, and perform actions mid-conversation
        self.tools_enabled = assistant_config.get('tools_enabled', False)
        self.tools_config = assistant_config.get('tools', [])
        self.tool_service = None
        self.max_tool_calls_per_turn = assistant_config.get('max_tool_calls_per_turn', 5)
        self.tool_execution_timeout = assistant_config.get('tool_execution_timeout', 30)

        # Call Quality Monitoring - Track network and audio quality metrics
        self.quality_monitoring_enabled = assistant_config.get('quality_monitoring_enabled', True)
        self.quality_monitor: Optional[CallQualityMonitor] = None
        if self.quality_monitoring_enabled:
            qos_thresholds = QoSThresholds(
                max_packet_loss_percent=assistant_config.get('qos_max_packet_loss', 3.0),
                max_jitter_ms=assistant_config.get('qos_max_jitter_ms', 30.0),
                max_rtt_ms=assistant_config.get('qos_max_rtt_ms', 300.0),
                min_snr_db=assistant_config.get('qos_min_snr_db', 10.0),
            )
            self.quality_monitor = CallQualityMonitor(
                call_id=call_id,
                thresholds=qos_thresholds,
                sample_rate=8000,
                alert_callback=self._on_quality_alert
            )
            logger.info(f"[CUSTOM] 📊 Call quality monitoring enabled")

    def _on_quality_alert(self, alert: QualityAlert):
        """Handle quality alerts during the call"""
        logger.warning(f"[QUALITY] {alert.severity.upper()}: {alert.message}")
        # Could trigger webhooks, send notifications, etc.

    async def initialize_providers(self):
        """Initialize ASR, TTS, and LLM providers"""
        try:
            logger.info(f"[CUSTOM] 🔧 === PROVIDER INITIALIZATION START ===")
            logger.info(f"[CUSTOM] 📋 Configuration:")
            logger.info(f"[CUSTOM]   ├─ ASR: {self.asr_provider_name} (model: {self.asr_model}, lang: {self.asr_language})")
            logger.info(f"[CUSTOM]   ├─ TTS: {self.tts_provider_name} (model: {self.tts_model}, voice: {self.tts_voice})")
            logger.info(f"[CUSTOM]   └─ LLM: {self.llm_provider} (model: {self.llm_model})")

            # Initialize ASR provider
            logger.info(f"[CUSTOM] 🎤 Initializing ASR provider: {self.asr_provider_name}")
            # Determine ASR model based on provider and config
            asr_model = self.asr_model
            if not asr_model:
                asr_model = 'nova-2' if self.asr_provider_name == 'deepgram' else 'whisper-1'
                logger.info(f"[CUSTOM]   └─ No model specified, using default: {asr_model}")

            asr_api_key = self.provider_keys.get(self.asr_provider_name)
            if self.asr_provider_name == 'openai':
                asr_api_key = asr_api_key or self.openai_api_key
            elif self.asr_provider_name == 'deepgram':
                asr_api_key = asr_api_key or os.getenv("DEEPGRAM_API_KEY")
            elif self.asr_provider_name == 'sarvam':
                asr_api_key = asr_api_key or os.getenv("SARVAM_API_KEY")
            elif self.asr_provider_name == 'google':
                asr_api_key = asr_api_key or os.getenv("GOOGLE_API_KEY")

            logger.info(f"[CUSTOM]   └─ API key {'✓ found' if asr_api_key else '✗ missing'}")

            # Fallback logic for missing API keys
            if self.asr_provider_name == 'deepgram' and not asr_api_key:
                logger.warning("[CUSTOM] ⚠️ Deepgram key not configured. Falling back to OpenAI Whisper for ASR.")
                self.asr_provider_name = 'openai'
                asr_model = 'whisper-1'
                asr_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
            elif self.asr_provider_name == 'sarvam' and not asr_api_key:
                logger.warning("[CUSTOM] ⚠️ Sarvam key not configured. Falling back to OpenAI Whisper for ASR.")
                self.asr_provider_name = 'openai'
                asr_model = 'whisper-1'
                asr_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
            elif self.asr_provider_name == 'google' and not asr_api_key:
                logger.warning("[CUSTOM] ⚠️ Google key not configured. Falling back to OpenAI Whisper for ASR.")
                self.asr_provider_name = 'openai'
                asr_model = 'whisper-1'
                asr_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")

            try:
                logger.info(f"[CUSTOM]   └─ Creating ASR provider instance...")

                # Build keywords string for Deepgram (combine user keywords with defaults)
                keywords_str = None
                if self.asr_provider_name == 'deepgram':
                    if self.asr_keywords:
                        keywords_str = ",".join(self.asr_keywords)
                        logger.info(f"[CUSTOM]   └─ ASR keywords configured: {keywords_str}")
                    else:
                        logger.info(f"[CUSTOM]   └─ Using default email/domain keywords for Deepgram")

                self.asr_provider = ProviderFactory.create_asr_provider(
                    provider_name=self.asr_provider_name,
                    api_key=asr_api_key,
                    model=asr_model,
                    language=self.asr_language,
                    keywords=keywords_str  # Pass keywords for Deepgram boosting
                )
                logger.info(f"[CUSTOM] ✅ ASR provider initialized: {self.asr_provider_name}/{asr_model}")
            except Exception as asr_error:
                logger.error(f"[CUSTOM] ❌ Failed to initialize ASR provider '{self.asr_provider_name}': {asr_error}", exc_info=True)
                if self.asr_provider_name != 'openai':
                    logger.warning("[CUSTOM] ⚠️ Falling back to OpenAI Whisper for ASR")
                    self.asr_provider_name = 'openai'
                    self.asr_model = 'whisper-1'
                    self.asr_provider = ProviderFactory.create_asr_provider(
                        provider_name='openai',
                        api_key=self.openai_api_key or os.getenv("OPENAI_API_KEY"),
                        model='whisper-1',
                        language=self.asr_language
                    )
                    logger.info(f"[CUSTOM] ✅ ASR fallback successful: openai/whisper-1")
                else:
                    raise

            # Initialize TTS provider
            logger.info(f"[CUSTOM] 🔊 Initializing TTS provider: {self.tts_provider_name}")
            # Determine TTS model based on provider and config
            tts_model = self.tts_model
            if not tts_model:
                tts_model = 'tts-1' if self.tts_provider_name == 'openai' else None
                if tts_model:
                    logger.info(f"[CUSTOM]   └─ No model specified, using default: {tts_model}")

            tts_api_key = self.provider_keys.get(self.tts_provider_name)
            if self.tts_provider_name == 'openai':
                tts_api_key = tts_api_key or self.openai_api_key
            elif self.tts_provider_name == 'cartesia':
                tts_api_key = tts_api_key or os.getenv("CARTESIA_API_KEY")
            elif self.tts_provider_name == 'elevenlabs':
                tts_api_key = tts_api_key or os.getenv("ELEVENLABS_API_KEY")
            elif self.tts_provider_name == 'sarvam':
                tts_api_key = tts_api_key or os.getenv("SARVAM_API_KEY")

            logger.info(f"[CUSTOM]   └─ API key {'✓ found' if tts_api_key else '✗ missing'}")

            if self.tts_provider_name == 'cartesia' and not tts_api_key:
                logger.warning("[CUSTOM] ⚠️ Cartesia key not configured. Falling back to OpenAI TTS.")
                self.tts_provider_name = 'openai'
                tts_model = 'tts-1'
                tts_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
            elif self.tts_provider_name == 'elevenlabs' and not tts_api_key:
                logger.warning("[CUSTOM] ⚠️ ElevenLabs key not configured. Falling back to OpenAI TTS.")
                self.tts_provider_name = 'openai'
                tts_model = 'tts-1'
                tts_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
            elif self.tts_provider_name == 'sarvam' and not tts_api_key:
                logger.warning("[CUSTOM] ⚠️ Sarvam key not configured. Falling back to OpenAI TTS.")
                self.tts_provider_name = 'openai'
                tts_model = 'tts-1'
                tts_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")

            try:
                logger.info(f"[CUSTOM]   └─ Creating TTS provider instance...")
                # Prepare kwargs for provider-specific parameters
                tts_kwargs = {}
                if self.tts_provider_name == 'sarvam':
                    # Sarvam needs language parameter
                    tts_kwargs['language'] = self.language or 'hi-IN'
                    logger.info(f"[CUSTOM]   └─ Sarvam language: {tts_kwargs['language']}")

                self.tts_provider = ProviderFactory.create_tts_provider(
                    provider_name=self.tts_provider_name,
                    api_key=tts_api_key,
                    voice=self.tts_voice or self.voice,
                    **tts_kwargs
                )
                logger.info(f"[CUSTOM] ✅ TTS provider initialized: {self.tts_provider_name}/{tts_model or 'default'} (voice: {self.tts_voice or self.voice})")
            except Exception as tts_error:
                logger.error(f"[CUSTOM] ❌ Failed to initialize TTS provider '{self.tts_provider_name}': {tts_error}", exc_info=True)
                if self.tts_provider_name != 'openai':
                    logger.warning("[CUSTOM] ⚠️ Falling back to OpenAI TTS")
                    self.tts_provider_name = 'openai'
                    self.tts_model = 'tts-1'
                    self.tts_provider = ProviderFactory.create_tts_provider(
                        provider_name='openai',
                        api_key=self.openai_api_key or os.getenv("OPENAI_API_KEY"),
                        voice=self.voice
                    )
                    logger.info(f"[CUSTOM] ✅ TTS fallback successful: openai/tts-1")
                else:
                    raise

            # Initialize LLM client based on provider
            logger.info(f"[CUSTOM] 🤖 Initializing LLM provider: {self.llm_provider}")
            llm_initialized = False
            if self.llm_provider == "openai":
                try:
                    import openai
                    openai_key = self.provider_keys.get('openai') or self.openai_api_key or os.getenv("OPENAI_API_KEY")
                    logger.info(f"[CUSTOM]   └─ API key {'✓ found' if openai_key else '✗ missing'}")
                    if not openai_key:
                        raise RuntimeError("OpenAI API key is not configured")
                    self.llm_client = openai.AsyncOpenAI(api_key=openai_key)
                    llm_initialized = True
                    logger.info(f"[CUSTOM] ✅ LLM initialized: openai/{self.llm_model or 'gpt-4o-mini'}")
                except Exception as openai_error:
                    logger.error(f"[CUSTOM] ❌ Failed to initialize OpenAI LLM client: {openai_error}", exc_info=True)
            elif self.llm_provider == "anthropic":
                try:
                    import anthropic
                    api_key = self.provider_keys.get('anthropic') or os.getenv("ANTHROPIC_API_KEY")
                    if not api_key:
                        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
                    self.llm_client = anthropic.AsyncAnthropic(api_key=api_key)
                    logger.warning("[CUSTOM] ⚠️ Anthropic client initialized but API responses are not yet supported. Falling back to OpenAI.")
                except Exception as anthropic_error:
                    logger.error(f"[CUSTOM] ❌ Failed to initialize Anthropic client: {anthropic_error}", exc_info=True)
            elif self.llm_provider == "groq":
                try:
                    from groq import AsyncGroq
                    api_key = self.provider_keys.get('groq') or os.getenv("GROQ_API_KEY")
                    if not api_key:
                        raise RuntimeError("GROQ_API_KEY is not configured")
                    self.llm_client = AsyncGroq(api_key=api_key)
                    logger.warning("[CUSTOM] ⚠️ Groq client initialized but API responses are not yet supported. Falling back to OpenAI.")
                except Exception as groq_error:
                    logger.error(f"[CUSTOM] ❌ Failed to initialize Groq client: {groq_error}", exc_info=True)

            if not llm_initialized:
                logger.warning("[CUSTOM] ⚠️ LLM provider not initialized, falling back to OpenAI")
                import openai
                fallback_key = self.provider_keys.get('openai') or self.openai_api_key or os.getenv("OPENAI_API_KEY")
                if not fallback_key:
                    raise RuntimeError("No supported LLM provider could be initialized (missing API keys)")
                self.llm_provider = "openai"
                self.llm_client = openai.AsyncOpenAI(api_key=fallback_key)
                if not self.llm_model:
                    self.llm_model = "gpt-4o-mini"
                llm_initialized = True
                logger.info(f"[CUSTOM] ✅ LLM fallback successful: openai/{self.llm_model}")

            # Add current date/time context to system message with timezone awareness
            # This ensures the AI always knows the current date for scheduling
            from datetime import timedelta
            import pytz

            # Get timezone from assistant config or default to Asia/Kolkata (IST)
            self.timezone_str = self.assistant_config.get('timezone', 'Asia/Kolkata')
            try:
                tz = pytz.timezone(self.timezone_str)
                now = datetime.now(tz)
            except Exception:
                # Fallback to UTC if timezone is invalid
                now = datetime.now(pytz.UTC)
                self.timezone_str = 'UTC'

            tomorrow = now + timedelta(days=1)
            day_after = now + timedelta(days=2)

            date_context = f"""

CURRENT DATE AND TIME CONTEXT (Timezone: {self.timezone_str}):
- Today's date: {now.strftime('%A, %B %d, %Y')}
- Current time: {now.strftime('%I:%M %p %Z')}
- When someone says 'today', they mean {now.strftime('%B %d, %Y')}.
- When someone says 'tomorrow', they mean {tomorrow.strftime('%A, %B %d, %Y')}.
- When someone says 'day after tomorrow', they mean {day_after.strftime('%A, %B %d, %Y')}.
- Always use this date context when discussing scheduling or dates.
- IMPORTANT: Before confirming any appointment, always verify the time slot is available. If a slot is busy, politely inform the caller and ask for an alternative time."""

            self.system_message += date_context
            logger.info(f"[CUSTOM] 📅 Date context added: Today is {now.strftime('%B %d, %Y')} ({self.timezone_str})")

            # Add system message to conversation history
            self.conversation_history.append({
                "role": "system",
                "content": self.system_message
            })

            # Initialize calendar services if enabled
            logger.info(f"[CUSTOM] 📅 Checking calendar configuration...")
            calendar_enabled_flag = self.assistant_config.get('calendar_enabled', False)
            calendar_account_ids = self.assistant_config.get('calendar_account_ids', [])

            if calendar_enabled_flag and calendar_account_ids:
                logger.info(f"[CUSTOM] 📅 Calendar enabled with {len(calendar_account_ids)} account(s)")
                self.calendar_enabled = True
                self.calendar_account_ids = calendar_account_ids
                self.calendar_service = CalendarService()
                self.calendar_intent_service = CalendarIntentService()

                # Add calendar instructions to system message
                calendar_instruction = "\n\nIMPORTANT: You can schedule appointments for the caller. When someone wants to schedule a meeting or appointment, collect the following: date, time, duration, and their name/email. Always confirm the details before finalizing."
                self.system_message += calendar_instruction
                self.conversation_history[0]["content"] += calendar_instruction

                logger.info(f"[CUSTOM] ✅ Calendar services initialized successfully")
            else:
                logger.info(f"[CUSTOM] ℹ️ Calendar integration disabled or no accounts configured")

            # Initialize Real-time Tool Service (Vapi-like functionality)
            if self.tools_enabled and self.tools_config:
                logger.info(f"[CUSTOM] 🔧 Initializing real-time tool service...")
                logger.info(f"[CUSTOM]   └─ {len(self.tools_config)} tool(s) configured")

                # Get database connection for tool service
                db = None
                try:
                    db = await Database.get_db()
                except Exception:
                    logger.warning("[CUSTOM] ⚠️ Database not available for tool service")

                self.tool_service = RealtimeToolService(
                    user_id=str(self.user_id) if self.user_id else None,
                    assistant_id=str(self.assistant_id) if self.assistant_id else None,
                    call_id=self.call_id,
                    db=db
                )

                # Add tool descriptions to system message
                tool_names = [t.get('name', 'unnamed') for t in self.tools_config]
                tools_instruction = f"\n\nAVAILABLE TOOLS: You have access to the following tools that you can use during this conversation: {', '.join(tool_names)}. Use these tools when appropriate to help the caller."
                self.system_message += tools_instruction
                self.conversation_history[0]["content"] += tools_instruction

                logger.info(f"[CUSTOM] ✅ Real-time tool service initialized with {len(self.tools_config)} tools")
            else:
                logger.info(f"[CUSTOM] ℹ️ Real-time tools disabled or no tools configured")

            # Translate greeting to bot language if needed
            if self.bot_language and self.bot_language != 'en':
                await self.translate_greeting()

            # ⚡ OPTIMIZATION: Start pre-synthesizing greeting audio immediately
            # This runs in background so greeting is ready when call connects
            logger.info(f"[CUSTOM] 🎙️ Starting greeting pre-synthesis in background...")
            self.greeting_synthesis_task = asyncio.create_task(self.presynthesize_greeting())

            logger.info(f"[CUSTOM] Providers initialized successfully (LLM: {self.llm_provider}, Model: {self.llm_model or 'default'})")
            return True

        except Exception as e:
            logger.error(f"[CUSTOM] Error initializing providers: {e}", exc_info=True)
            return False

    async def prewarm_llm(self):
        """
        Pre-warm the LLM session by sending a minimal dummy request.
        This eliminates cold-start latency on the first real user query.

        Strategy: Send a simple system+user message that the LLM will respond to quickly.
        The response is discarded - we just want to "wake up" the model connection.
        """
        if self.llm_warmed_up or not self.llm_client:
            return

        import time
        try:
            warmup_start = time.time()
            logger.info("[CUSTOM] 🔥 Pre-warming LLM session...")

            # Minimal warmup prompt - just to establish connection
            warmup_messages = [
                {"role": "system", "content": "Respond with OK."},
                {"role": "user", "content": "Ready?"}
            ]

            # Determine model to use
            llm_model = self.llm_model or "gpt-4o-mini"

            # Use non-streaming for faster warmup (we don't care about the response)
            response = await self.llm_client.chat.completions.create(
                model=llm_model,
                messages=warmup_messages,
                temperature=0.1,
                max_tokens=5,  # Minimal tokens - we just need the connection
                stream=False
            )

            warmup_time = (time.time() - warmup_start) * 1000
            self.llm_warmed_up = True
            logger.info(f"[CUSTOM] 🔥 LLM pre-warmed in {warmup_time:.0f}ms (cold start eliminated)")

        except Exception as e:
            logger.warning(f"[CUSTOM] ⚠️ LLM pre-warm failed (non-fatal): {e}")
            # Not fatal - first user query will just have normal cold start

    async def presynthesize_greeting(self):
        """
        Pre-synthesize greeting audio during initialization so it's ready
        for IMMEDIATE playback when the call connects.
        This eliminates TTS latency from the greeting.
        """
        import time
        try:
            synth_start = time.time()
            logger.info(f"[CUSTOM] 🎙️ Pre-synthesizing greeting audio...")
            logger.info(f"[CUSTOM]   └─ Greeting: \"{self.greeting[:50]}...\"" if len(self.greeting) > 50 else f"[CUSTOM]   └─ Greeting: \"{self.greeting}\"")

            # Generate greeting audio
            greeting_audio = await self.tts_provider.synthesize(self.greeting)

            if greeting_audio and len(greeting_audio) > 0:
                # Determine input sample rate based on TTS provider
                input_sample_rate = 8000  # Default for Cartesia
                is_wav_format = False

                if self.tts_provider_name == 'elevenlabs':
                    input_sample_rate = 16000
                elif self.tts_provider_name == 'openai':
                    input_sample_rate = 24000
                elif self.tts_provider_name == 'sarvam':
                    input_sample_rate = 8000
                    is_wav_format = True

                # Extract PCM from WAV if needed
                if is_wav_format:
                    try:
                        from app.voice_pipeline.helpers.utils import wav_bytes_to_pcm
                        greeting_audio = wav_bytes_to_pcm(greeting_audio)
                    except Exception as wav_error:
                        logger.error(f"[CUSTOM] WAV extraction failed: {wav_error}")

                # Resample to 8kHz if needed
                if input_sample_rate != 8000:
                    try:
                        greeting_audio, _ = audioop.ratecv(greeting_audio, 2, 1, input_sample_rate, 8000, None)
                    except Exception as conv_error:
                        logger.warning(f"[CUSTOM] Audio resampling failed: {conv_error}")

                # Encode to μ-law for Twilio
                if self.platform == "twilio":
                    try:
                        greeting_audio = audioop.lin2ulaw(greeting_audio, 2)
                    except Exception as enc_error:
                        logger.error(f"[CUSTOM] μ-law encoding failed: {enc_error}")

                # Cache the pre-processed audio
                self.greeting_audio_cache = greeting_audio

                synth_time = (time.time() - synth_start) * 1000
                logger.info(f"[CUSTOM] ✅ Greeting pre-synthesized in {synth_time:.0f}ms ({len(greeting_audio)} bytes cached)")
            else:
                logger.error(f"[CUSTOM] ❌ TTS returned NO AUDIO for greeting pre-synthesis!")

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Greeting pre-synthesis failed: {e}")
            # Not fatal - will fall back to on-demand synthesis

    async def send_greeting(self):
        """Send initial greeting to caller - IMMEDIATE playback using pre-synthesized audio"""
        import time
        try:
            send_start = time.time()
            logger.info(f"[CUSTOM] 🎙️ === SENDING GREETING ===")

            # Check if we have pre-synthesized audio (should be ready from initialization)
            if self.greeting_audio_cache:
                logger.info(f"[CUSTOM] ⚡ Using PRE-SYNTHESIZED greeting audio ({len(self.greeting_audio_cache)} bytes)")
                converted_audio = self.greeting_audio_cache
            else:
                # Fallback: Wait for pre-synthesis task if still running
                if self.greeting_synthesis_task and not self.greeting_synthesis_task.done():
                    logger.info(f"[CUSTOM] ⏳ Waiting for greeting pre-synthesis to complete...")
                    try:
                        await asyncio.wait_for(self.greeting_synthesis_task, timeout=3.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"[CUSTOM] ⚠️ Pre-synthesis timeout, synthesizing on-demand")

                # If still no cached audio, synthesize on-demand
                if self.greeting_audio_cache:
                    converted_audio = self.greeting_audio_cache
                    logger.info(f"[CUSTOM] ✅ Pre-synthesis completed, using cached audio")
                else:
                    logger.warning(f"[CUSTOM] ⚠️ No pre-synthesized audio, synthesizing on-demand...")
                    await self.presynthesize_greeting()
                    if self.greeting_audio_cache:
                        converted_audio = self.greeting_audio_cache
                    else:
                        logger.error(f"[CUSTOM] ❌ Failed to synthesize greeting audio!")
                        return

            # Send audio in platform-specific format
            if self.platform == "frejun":
                # FreJun format
                audio_b64 = base64.b64encode(converted_audio).decode('utf-8')
                await self.websocket.send_json({
                    "type": "audio",
                    "audio_b64": audio_b64
                })
            else:
                # Twilio format with mark events (Bolna-style)
                if not self.stream_sid:
                    logger.warning("[CUSTOM] ⚠️ Missing streamSid for Twilio audio, waiting for start event")
                else:
                    logger.info(f"[CUSTOM] 📤 Sending greeting audio to Twilio ({len(converted_audio)} bytes)")
                    await self.mark_handler.send_audio_with_marks(
                        converted_audio,
                        self.greeting,
                        is_final=True
                    )
                    logger.info(f"[CUSTOM] ✅ Greeting audio sent to Twilio successfully")

            send_time = (time.time() - send_start) * 1000
            logger.info(f"[CUSTOM] 🎉 === GREETING SENT IN {send_time:.0f}ms === ({len(converted_audio)} bytes)")

        except Exception as e:
            logger.error(f"[CUSTOM] Error sending greeting: {e}", exc_info=True)

    async def translate_greeting(self):
        """Translate greeting to the selected bot language using OpenAI"""
        try:
            language_name = self.language_names.get(self.bot_language, self.bot_language.upper())
            logger.info(f"[CUSTOM] 🌍 Translating greeting to {language_name}...")
            logger.info(f"[CUSTOM]   Original greeting: \"{self.original_greeting}\"")

            # Use OpenAI to translate the greeting
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)

            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Fast and cheap model for translation
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a professional translator. Translate the given text to {language_name}. Only return the translation, nothing else. Maintain the tone and formality of the original text."
                    },
                    {
                        "role": "user",
                        "content": self.original_greeting
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent translations
                max_tokens=150
            )

            translated_greeting = response.choices[0].message.content.strip()

            if translated_greeting:
                self.greeting = translated_greeting
                logger.info(f"[CUSTOM] ✅ Greeting translated to {language_name}: \"{self.greeting}\"")
            else:
                logger.warning(f"[CUSTOM] ⚠️ Translation returned empty, using original greeting")

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error translating greeting: {e}")
            logger.warning(f"[CUSTOM] ⚠️ Falling back to original greeting: \"{self.original_greeting}\"")
            # Keep original greeting on error

    async def process_audio_chunk(self, audio_data: bytes):
        """
        Buffer audio and transcribe when we have enough data.
        Uses Silero VAD for intelligent speech detection when available,
        falls back to time-based buffering otherwise.
        """
        self.audio_buffer.extend(audio_data)
        logger.debug(f"[CUSTOM] 🎙️ Buffered audio: {len(self.audio_buffer)} bytes total")

        # Track audio quality metrics
        if self.quality_monitor and audio_data:
            is_voice = False
            if self.use_vad and self.vad_processor:
                # Check if VAD detected voice
                is_voice = self._last_speech_prob > 0.5 if hasattr(self, '_last_speech_prob') else False
            self.quality_monitor.track_audio_chunk(audio_data, is_voice=is_voice)

        if self.use_vad and self.vad_processor:
            # Use Silero VAD for intelligent speech detection
            await self._process_audio_with_vad(audio_data)
        else:
            # Fallback to time-based buffering
            await self._process_audio_time_based()

    async def _process_audio_with_vad(self, audio_data: bytes):
        """
        Process audio using Silero VAD for intelligent speech detection.
        Only triggers transcription when a complete speech segment ends.

        ENHANCED: Now includes real-time interruption detection.
        When user speaks while AI is playing audio, we immediately stop playback.
        """
        # Process audio chunk through VAD
        # Note: VAD expects raw PCM, audio_data is already converted from mulaw
        is_speech, speech_prob = self.vad_processor.process_chunk(audio_data)
        self._last_speech_prob = speech_prob  # Track for monitoring

        # ========== REAL-TIME INTERRUPTION DETECTION ==========
        # If AI is currently playing audio and user starts speaking, interrupt immediately
        if self.enable_interruption:
            if is_speech and speech_prob >= self.interruption_probability_threshold:
                self._consecutive_speech_chunks += 1

                # Check if AI is playing and we have enough consecutive speech chunks
                is_ai_playing = self.mark_handler.is_playing_audio if self.platform == "twilio" else self._is_ai_speaking

                if is_ai_playing and self._consecutive_speech_chunks >= self.interruption_min_chunks:
                    logger.info(f"[CUSTOM] 🛑 === INTERRUPTION DETECTED ===")
                    logger.info(f"[CUSTOM]   └─ Platform: {self.platform}")
                    logger.info(f"[CUSTOM]   └─ Speech probability: {speech_prob:.2f}")
                    logger.info(f"[CUSTOM]   └─ Consecutive chunks: {self._consecutive_speech_chunks}")
                    logger.info(f"[CUSTOM]   └─ Stopping AI audio playback immediately!")

                    # Platform-specific interruption handling
                    if self.platform == "twilio":
                        # Send clear to stop audio immediately
                        await self.mark_handler.send_clear()
                    else:
                        # FreJun: Send stop signal (if supported) or just set flag
                        try:
                            await self.websocket.send_json({
                                "type": "clear",
                                "reason": "user_interruption"
                            })
                        except Exception as e:
                            logger.debug(f"[CUSTOM] FreJun clear not supported: {e}")
                        self._is_ai_speaking = False

                    self._is_interrupted = True
                    self._consecutive_speech_chunks = 0

                    logger.info(f"[CUSTOM] 🛑 === AI AUDIO STOPPED - Ready for user input ===")
            else:
                # Reset consecutive counter if no speech detected
                self._consecutive_speech_chunks = 0

        # ========== END-OF-SPEECH DETECTION ==========
        # Check if a valid speech segment has ended
        if self.vad_processor.is_speech_ended() and len(self.audio_buffer) >= self.min_audio_threshold:
            speech_duration = self.vad_processor.get_speech_duration_ms()
            logger.info(f"[CUSTOM] 🎤 [VAD] Speech ended after {speech_duration}ms, processing buffer "
                       f"({len(self.audio_buffer)} bytes)")

            # Reset interruption flag before processing new response
            self._is_interrupted = False
            await self.transcribe_and_respond()
            self.vad_processor.reset()

        # Emergency flush to prevent memory buildup (4 seconds of audio)
        if len(self.audio_buffer) >= 64000:  # 64KB = ~4 seconds at 8kHz 16-bit
            logger.warning("[CUSTOM] 🎤 [VAD] Emergency buffer flush (64KB limit)")
            await self.transcribe_and_respond()
            self.vad_processor.reset()

    async def _process_audio_time_based(self):
        """
        Fallback: Process audio using time-based buffering.
        Used when Silero VAD is not available.
        """
        # Calculate buffer threshold based on configured buffer size (in ms)
        # Formula: (sample_rate * buffer_ms / 1000) * bytes_per_sample
        # Example: (8000 * 200 / 1000) * 2 = 3200 bytes for 200ms buffer
        buffer_threshold_bytes = int((8000 * self.audio_buffer_size / 1000) * 2)

        # Process when buffer reaches threshold
        # Twilio sends 20ms chunks (320 bytes), so actual buffer will be a multiple of 320
        if len(self.audio_buffer) >= buffer_threshold_bytes:
            logger.info(f"[CUSTOM] 🎯 Buffer threshold reached ({len(self.audio_buffer)}/{buffer_threshold_bytes} bytes), processing...")
            await self.transcribe_and_respond()

    async def transcribe_and_respond(self):
        """
        Transcribe buffered audio and generate response
        """
        if len(self.audio_buffer) == 0:
            logger.debug(f"[CUSTOM] ℹ️ Empty buffer, skipping transcription")
            return

        try:
            # ⏱️ Start timing the entire pipeline
            pipeline_start = datetime.now()

            # Copy buffer and clear it
            audio_to_process = bytes(self.audio_buffer)
            self.audio_buffer.clear()

            logger.info(f"[CUSTOM] 🎤 === TRANSCRIPTION START === ({len(audio_to_process)} bytes)")

            # Transcribe using ASR provider
            asr_start = datetime.now()
            logger.info(f"[CUSTOM] 🔄 Calling ASR provider: {self.asr_provider_name}")
            transcript = await self.asr_provider.transcribe(audio_to_process)
            asr_time = (datetime.now() - asr_start).total_seconds() * 1000

            if not transcript or len(transcript.strip()) == 0:
                logger.debug(f"[CUSTOM] ℹ️ Empty transcript from ASR, skipping")
                return

            logger.info(f"[CUSTOM] ✅ Transcribed in {asr_time:.0f}ms ({len(transcript)} chars): \"{transcript}\"")

            # 🌍 AUTOMATIC LANGUAGE DETECTION & SWITCHING
            detected_language = detect_language_from_text(transcript)
            if detected_language != self.bot_language:
                logger.info(f"[CUSTOM] 🌍 Language switch detected: {self.bot_language} → {detected_language}")
                logger.info(f"[CUSTOM] 🌍 User is now speaking in: {detected_language.upper()}")

                # Update bot language for responses
                old_language = self.bot_language
                self.bot_language = detected_language

                # Update ASR language for better future transcriptions (if ASR supports it)
                if hasattr(self.asr_provider, 'set_language'):
                    self.asr_provider.set_language(detected_language)
                    logger.info(f"[CUSTOM] 🌍 Updated ASR language to: {detected_language}")

                # Update system message to reflect new language
                language_name = self.language_names.get(self.bot_language, self.bot_language.upper())
                if self.bot_language != 'en':
                    # Add language instruction to system message
                    base_system_message = self.system_message.split("\n\nIMPORTANT: You MUST speak")[0]
                    self.system_message = f"{base_system_message}\n\nIMPORTANT: You MUST speak and respond ONLY in {language_name}. All your responses should be in {language_name} language."
                    logger.info(f"[CUSTOM] 🌍 Updated system message for {language_name} responses")
                else:
                    # Remove language instruction for English
                    self.system_message = self.system_message.split("\n\nIMPORTANT: You MUST speak")[0]
                    logger.info(f"[CUSTOM] 🌍 Switched back to English - removed language instruction")

                # Update the system message in conversation history
                if len(self.conversation_history) > 0 and self.conversation_history[0].get('role') == 'system':
                    self.conversation_history[0]['content'] = self.system_message
                    logger.info(f"[CUSTOM] 🌍 Updated system message in conversation history")

                logger.info(f"[CUSTOM] 🌍 ✅ Language switched from {old_language} to {detected_language}")

            # Add user message to history
            self.conversation_history.append({
                "role": "user",
                "content": transcript
            })
            # Track full transcript with timestamps for workflow triggers
            self.full_transcript.append({
                "speaker": "user",
                "text": transcript,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"[CUSTOM] 💬 Added user message to conversation history (total: {len(self.conversation_history)} messages)")

            # Generate LLM response
            logger.info(f"[CUSTOM] 🤖 === LLM GENERATION START ===")
            logger.info(f"[CUSTOM] 🔄 Calling LLM provider: {self.llm_provider}/{self.llm_model}")
            llm_start = datetime.now()

            # Use streaming mode for lower latency if enabled
            if self.use_streaming_mode:
                logger.info(f"[CUSTOM] ⚡ Using STREAMING mode for lower latency")
                response_text = await self._generate_and_stream_response()
                llm_time = (datetime.now() - llm_start).total_seconds() * 1000
                # Streaming mode handles TTS internally, so we're done
                if response_text:
                    # Add assistant message to history
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": response_text
                    })
                    # Track full transcript with timestamps for workflow triggers
                    self.full_transcript.append({
                        "speaker": "assistant",
                        "text": response_text,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    # Log to database
                    await self.log_interaction(transcript, response_text)
                return
            else:
                response_text = await self.generate_llm_response()
                llm_time = (datetime.now() - llm_start).total_seconds() * 1000

            if not response_text:
                logger.warning(f"[CUSTOM] ⚠️ Empty LLM response, skipping")
                return

            logger.info(f"[CUSTOM] ✅ LLM response ({len(response_text)} chars) in {llm_time:.0f}ms: \"{response_text}\"")

            # Add assistant message to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response_text
            })
            # Track full transcript with timestamps for workflow triggers
            self.full_transcript.append({
                "speaker": "assistant",
                "text": response_text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"[CUSTOM] 💬 Added assistant message to conversation history")

            # ⚡ OPTIMIZATION: Run TTS synthesis and calendar check IN PARALLEL to reduce lag
            logger.info(f"[CUSTOM] ⚡ Starting TTS synthesis and calendar check in parallel...")

            # Start TTS synthesis immediately (don't wait)
            tts_task = asyncio.create_task(self._synthesize_response(response_text))

            # Check for calendar intent in parallel (non-blocking)
            if self.calendar_enabled and not self.appointment_scheduled and not self.scheduling_task:
                asyncio.create_task(self.check_calendar_intent())  # Fire and forget

            # Wait ONLY for TTS to complete (calendar check runs in background)
            response_audio, tts_time = await tts_task

            if not response_audio:
                logger.error(f"[CUSTOM] ❌ TTS synthesis returned no audio!")
                return

            logger.info(f"[CUSTOM] ✅ TTS completed: {len(response_audio)} bytes")

            # ⏱️ Log complete pipeline timing breakdown
            total_time = (datetime.now() - pipeline_start).total_seconds() * 1000
            logger.info(f"[CUSTOM] ⚡ === PIPELINE LATENCY BREAKDOWN ===")
            logger.info(f"[CUSTOM]   ASR (Speech-to-Text): {asr_time:.0f}ms")
            logger.info(f"[CUSTOM]   LLM (AI Response):     {llm_time:.0f}ms")
            logger.info(f"[CUSTOM]   TTS (Text-to-Speech):  {tts_time:.0f}ms")
            logger.info(f"[CUSTOM]   ⚡ TOTAL PIPELINE:     {total_time:.0f}ms")
            logger.info(f"[CUSTOM] ⚡ === END PIPELINE TIMING ===")

            # Store metrics for execution logs
            self.metrics["asr_times"].append(asr_time)
            self.metrics["llm_times"].append(llm_time)
            self.metrics["tts_times"].append(tts_time)
            self.metrics["total_times"].append(total_time)

            # Convert audio format if needed
            logger.info(f"[CUSTOM] 🔄 Converting audio format...")
            # Determine input sample rate based on TTS provider
            input_sample_rate = 8000  # Default for Cartesia
            is_wav_format = False  # Flag for WAV-encoded audio

            if self.tts_provider_name == 'elevenlabs':
                input_sample_rate = 16000
            elif self.tts_provider_name == 'openai':
                input_sample_rate = 24000  # OpenAI TTS outputs 24kHz
            elif self.tts_provider_name == 'sarvam':
                # Sarvam returns WAV format @ 8kHz
                input_sample_rate = 8000
                is_wav_format = True

            logger.info(f"[CUSTOM]   └─ Input sample rate: {input_sample_rate}Hz, Target: 8000Hz (Twilio requirement)")
            logger.info(f"[CUSTOM]   └─ Is WAV format: {is_wav_format}")

            # Step 0: Extract PCM from WAV if needed (for Sarvam)
            if is_wav_format:
                try:
                    from app.voice_pipeline.helpers.utils import wav_bytes_to_pcm
                    logger.info(f"[CUSTOM]   └─ Extracting PCM from WAV container...")
                    response_audio = wav_bytes_to_pcm(response_audio)
                    logger.info(f"[CUSTOM] ✅ Extracted PCM: {len(response_audio)} bytes")
                except Exception as wav_error:
                    logger.error(f"[CUSTOM] ❌ WAV extraction failed: {wav_error}")

            # Step 1: Resample to 8kHz if needed
            if input_sample_rate != 8000:
                try:
                    logger.info(f"[CUSTOM]   └─ Resampling from {input_sample_rate}Hz to 8000Hz...")
                    converted_audio, _ = audioop.ratecv(response_audio, 2, 1, input_sample_rate, 8000, None)
                    logger.info(f"[CUSTOM] ✅ Resampled audio: {len(converted_audio)} bytes")
                except Exception as conv_error:
                    logger.error(f"[CUSTOM] ❌ Audio resampling failed: {conv_error}")
                    converted_audio = response_audio
            else:
                logger.info(f"[CUSTOM]   └─ No resampling needed (already 8kHz)")
                converted_audio = response_audio

            # Step 2: Encode to μ-law for Twilio, keep PCM for FreJun
            if self.platform == "twilio":
                try:
                    logger.info(f"[CUSTOM]   └─ Converting PCM to μ-law for Twilio...")
                    # Convert PCM to μ-law (G.711) for Twilio
                    converted_audio = audioop.lin2ulaw(converted_audio, 2)
                    logger.info(f"[CUSTOM] ✅ Encoded to μ-law: {len(converted_audio)} bytes")
                except Exception as enc_error:
                    logger.error(f"[CUSTOM] ❌ μ-law encoding failed: {enc_error}")
                    # Fall back to PCM (won't work but at least won't crash)
                    pass

            # Send audio in platform-specific format
            logger.info(f"[CUSTOM] 📤 === SENDING AUDIO TO {self.platform.upper()} ===")
            if self.platform == "frejun":
                # FreJun format
                audio_b64 = base64.b64encode(converted_audio).decode('utf-8')
                logger.info(f"[CUSTOM]   └─ Sending FreJun format audio ({len(audio_b64)} chars base64)")
                self._is_ai_speaking = True  # Track AI speaking state for interruption detection
                await self.websocket.send_json({
                    "type": "audio",
                    "audio_b64": audio_b64
                })
                # Estimate audio duration and set speaking to false after
                audio_duration_ms = len(converted_audio) / 16  # 8kHz, 2 bytes per sample = 16 bytes/ms
                asyncio.create_task(self._clear_ai_speaking_after(audio_duration_ms))
                logger.info(f"[CUSTOM] ✅ Audio sent to FreJun successfully")
            else:
                # Twilio format with mark events (Bolna-style)
                if not self.stream_sid:
                    logger.error("[CUSTOM] ❌ Missing streamSid for Twilio audio! Cannot send.")
                    logger.error("[CUSTOM]   └─ This usually means 'start' event was not received properly")
                    return
                else:
                    logger.info(f"[CUSTOM]   └─ Sending Twilio format audio with mark events (streamSid: {self.stream_sid})")
                    logger.info(f"[CUSTOM]   └─ Audio size: {len(converted_audio)} bytes")
                    await self.mark_handler.send_audio_with_marks(
                        converted_audio,
                        response_text,
                        is_final=True
                    )
                    logger.info(f"[CUSTOM] ✅ Audio sent to Twilio with mark events")

            logger.info(f"[CUSTOM] 🎉 === RESPONSE PIPELINE COMPLETE === ({len(converted_audio)} bytes sent)")

            # Log to database
            await self.log_interaction(transcript, response_text)

        except Exception as e:
            logger.error(f"[CUSTOM] Error in transcribe_and_respond: {e}", exc_info=True)

    async def _clear_ai_speaking_after(self, duration_ms: float):
        """
        Clear AI speaking state after estimated audio duration.
        Used for FreJun platform where we don't have mark events.
        """
        try:
            await asyncio.sleep(duration_ms / 1000.0)
            self._is_ai_speaking = False
            logger.debug(f"[CUSTOM] AI speaking state cleared after {duration_ms:.0f}ms")
        except asyncio.CancelledError:
            pass

    async def _synthesize_response(self, text: str) -> tuple[Optional[bytes], float]:
        """
        Internal helper to synthesize speech from text
        This is separated to allow parallel execution with calendar checks

        Returns:
            Tuple of (audio_bytes, elapsed_time_ms)
        """
        try:
            logger.info(f"[CUSTOM] 🔊 TTS synthesis starting for {len(text)} chars...")
            start_time = datetime.now()

            audio = await self.tts_provider.synthesize(text)

            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"[CUSTOM] ✅ TTS synthesis completed in {elapsed_ms:.0f}ms")

            return audio, elapsed_ms
        except Exception as e:
            logger.error(f"[CUSTOM] ❌ TTS synthesis error: {e}")
            return None, 0.0

    async def _speak_conflict_response(self, text: str):
        """
        Synthesize and send a conflict response to the user when a time slot is busy.
        This method handles the complete audio pipeline for conflict messages.
        """
        try:
            logger.info(f"[CUSTOM] 📅 Speaking conflict response: {text}")

            # Synthesize the conflict message
            response_audio, tts_time = await self._synthesize_response(text)

            if not response_audio:
                logger.error("[CUSTOM] ❌ Failed to synthesize conflict response")
                return

            # Determine input sample rate based on TTS provider
            input_sample_rate = 8000
            is_wav_format = False

            if self.tts_provider_name == 'elevenlabs':
                input_sample_rate = 16000
            elif self.tts_provider_name == 'openai':
                input_sample_rate = 24000
            elif self.tts_provider_name == 'sarvam':
                input_sample_rate = 8000
                is_wav_format = True

            # Extract PCM from WAV if needed
            if is_wav_format:
                try:
                    from app.voice_pipeline.helpers.utils import wav_bytes_to_pcm
                    response_audio = wav_bytes_to_pcm(response_audio)
                except Exception as wav_error:
                    logger.error(f"[CUSTOM] WAV extraction failed: {wav_error}")

            # Resample to 8kHz if needed
            if input_sample_rate != 8000:
                try:
                    converted_audio, _ = audioop.ratecv(response_audio, 2, 1, input_sample_rate, 8000, None)
                except Exception:
                    converted_audio = response_audio
            else:
                converted_audio = response_audio

            # Encode for platform
            if self.platform == "twilio":
                try:
                    converted_audio = audioop.lin2ulaw(converted_audio, 2)
                except Exception:
                    pass

            # Send audio
            if self.platform == "frejun":
                audio_b64 = base64.b64encode(converted_audio).decode('utf-8')
                await self.websocket.send_json({
                    "type": "audio",
                    "audio_b64": audio_b64
                })
            else:
                if self.stream_sid:
                    await self.mark_handler.send_audio_with_marks(
                        converted_audio,
                        text,
                        is_final=True
                    )

            logger.info(f"[CUSTOM] ✅ Conflict response sent successfully")

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error speaking conflict response: {e}", exc_info=True)

    async def generate_llm_response(self) -> str:
        """
        Generate response using LLM with real-time tool calling support (Vapi-like).

        This method supports:
        1. Regular text responses
        2. Tool/function calling during the conversation
        3. Multi-step tool execution loops
        """
        try:
            # Keep last 10 messages to avoid token limits
            messages = self.conversation_history[-10:]

            # Determine model to use
            llm_model = self.llm_model
            if not llm_model:
                # Default models based on provider
                if self.llm_provider == "openai":
                    llm_model = "gpt-4o-mini"
                elif self.llm_provider == "anthropic":
                    llm_model = "claude-3-5-sonnet-20241022"
                elif self.llm_provider == "groq":
                    llm_model = "llama-3.3-70b-versatile"
                else:
                    llm_model = "gpt-4o-mini"

            # Prepare tools if enabled
            tools = None
            if self.tools_enabled and self.tool_service and self.tools_config:
                tools = self.tool_service.get_openai_tools_schema(self.tools_config)
                logger.info(f"[CUSTOM] 🔧 Tools enabled: {len(tools)} tool(s) available")

            # Initial LLM call
            create_params = {
                "model": llm_model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.llm_max_tokens,
                "stream": False
            }

            if tools:
                create_params["tools"] = tools
                create_params["tool_choice"] = "auto"  # Let AI decide when to use tools

            response = await self.llm_client.chat.completions.create(**create_params)
            message = response.choices[0].message

            # Check if the model wants to call tools
            tool_calls_count = 0
            while message.tool_calls and tool_calls_count < self.max_tool_calls_per_turn:
                tool_calls_count += 1
                logger.info(f"[CUSTOM] 🔧 Tool call requested (turn {tool_calls_count}/{self.max_tool_calls_per_turn})")

                # Process each tool call
                tool_results = []
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}

                    logger.info(f"[CUSTOM] 🔧 Executing tool: {tool_name}")
                    logger.debug(f"[CUSTOM]   └─ Arguments: {tool_args}")

                    # Execute the tool
                    context = {
                        "call_id": self.call_id,
                        "assistant_id": str(self.assistant_id) if self.assistant_id else None,
                        "user_id": str(self.user_id) if self.user_id else None,
                        "conversation_history": self.conversation_history[-5:],  # Recent context
                        "platform": self.platform
                    }

                    result = await self.tool_service.execute_tool(
                        tool_name=tool_name,
                        tool_arguments=tool_args,
                        tool_configs=self.tools_config,
                        context=context
                    )

                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "result": result
                    })

                    logger.info(f"[CUSTOM] 🔧 Tool {tool_name} completed: {'success' if result.get('success') else 'failed'}")

                # Add assistant message with tool calls to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })

                # Add tool results to history
                for tr in tool_results:
                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": json.dumps(tr["result"])
                    })

                # Call LLM again with tool results
                messages = self.conversation_history[-15:]  # Allow more context for tool results
                create_params["messages"] = messages

                response = await self.llm_client.chat.completions.create(**create_params)
                message = response.choices[0].message

            # Return the final text response
            final_response = message.content or ""

            if tool_calls_count > 0:
                logger.info(f"[CUSTOM] 🔧 Completed {tool_calls_count} tool execution round(s)")

            return final_response

        except Exception as e:
            logger.error(f"[CUSTOM] Error generating LLM response: {e}", exc_info=True)
            return "I apologize, I'm having trouble processing that right now."

    async def _generate_and_stream_response(self) -> str:
        """
        OPTIMIZED: Stream LLM response and synthesize TTS sentence-by-sentence.
        This reduces first-response latency significantly by not waiting for full LLM response.

        Flow:
        1. Start streaming LLM response
        2. As each sentence completes, immediately send to TTS
        3. Send audio to caller while next sentence is being generated
        4. Check for interruption between sentences

        Returns:
            Full response text
        """
        import re

        try:
            messages = self.conversation_history[-10:]
            llm_model = self.llm_model or "gpt-4o-mini"

            logger.info(f"[CUSTOM] ⚡ Starting streaming LLM response...")

            response = await self.llm_client.chat.completions.create(
                model=llm_model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.llm_max_tokens,
                stream=True
            )

            buffer = ""
            full_response = ""
            sentence_count = 0
            # Pattern to match end of sentences
            sentence_pattern = re.compile(r'[.!?]+[\s\n]+|[.!?]+$')

            async for chunk in response:
                # Check for interruption - stop generating if user is speaking
                if self._is_interrupted:
                    logger.info(f"[CUSTOM] 🛑 LLM streaming interrupted by user")
                    break

                delta = chunk.choices[0].delta
                if delta.content:
                    token = delta.content
                    buffer += token
                    full_response += token

                    # Check for complete sentences
                    while True:
                        match = sentence_pattern.search(buffer)
                        if not match:
                            break

                        end_pos = match.end()
                        sentence = buffer[:end_pos].strip()
                        buffer = buffer[end_pos:]

                        if sentence:
                            sentence_count += 1
                            logger.info(f"[CUSTOM] ⚡ Sentence {sentence_count}: \"{sentence[:50]}...\"")

                            # Check for interruption before sending TTS
                            if self._is_interrupted:
                                logger.info(f"[CUSTOM] 🛑 Skipping TTS - user interrupted")
                                break

                            # Synthesize and send this sentence immediately
                            await self._stream_sentence_to_caller(sentence, is_final=False)

            # Handle remaining text in buffer
            if buffer.strip() and not self._is_interrupted:
                sentence_count += 1
                logger.info(f"[CUSTOM] ⚡ Final sentence {sentence_count}: \"{buffer.strip()[:50]}...\"")
                await self._stream_sentence_to_caller(buffer.strip(), is_final=True)

            logger.info(f"[CUSTOM] ⚡ Streaming complete: {sentence_count} sentences, {len(full_response)} chars")
            return full_response

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error in streaming LLM: {e}", exc_info=True)
            return "I apologize, I'm having trouble processing that right now."

    async def _stream_sentence_to_caller(self, sentence: str, is_final: bool = False):
        """
        Synthesize a single sentence and stream to caller.
        Used by streaming mode to send audio sentence-by-sentence.
        """
        try:
            # Synthesize this sentence
            start_time = datetime.now()
            response_audio = await self.tts_provider.synthesize(sentence)
            tts_time = (datetime.now() - start_time).total_seconds() * 1000

            if not response_audio:
                logger.warning(f"[CUSTOM] ⚠️ TTS returned no audio for sentence")
                return

            logger.debug(f"[CUSTOM] ⚡ TTS synthesized in {tts_time:.0f}ms ({len(response_audio)} bytes)")

            # Convert audio format
            input_sample_rate = 8000
            is_wav_format = False

            if self.tts_provider_name == 'elevenlabs':
                input_sample_rate = 16000
            elif self.tts_provider_name == 'openai':
                input_sample_rate = 24000
            elif self.tts_provider_name == 'sarvam':
                input_sample_rate = 8000
                is_wav_format = True

            # Extract PCM from WAV if needed
            if is_wav_format:
                try:
                    from app.voice_pipeline.helpers.utils import wav_bytes_to_pcm
                    response_audio = wav_bytes_to_pcm(response_audio)
                except Exception as wav_error:
                    logger.error(f"[CUSTOM] WAV extraction failed: {wav_error}")

            # Resample to 8kHz if needed
            if input_sample_rate != 8000:
                try:
                    converted_audio, _ = audioop.ratecv(response_audio, 2, 1, input_sample_rate, 8000, None)
                except Exception:
                    converted_audio = response_audio
            else:
                converted_audio = response_audio

            # Encode for platform
            if self.platform == "twilio":
                try:
                    converted_audio = audioop.lin2ulaw(converted_audio, 2)
                except Exception:
                    pass

            # Send audio
            if self.platform == "frejun":
                audio_b64 = base64.b64encode(converted_audio).decode('utf-8')
                await self.websocket.send_json({
                    "type": "audio",
                    "audio_b64": audio_b64
                })
            else:
                if self.stream_sid:
                    await self.mark_handler.send_audio_with_marks(
                        converted_audio,
                        sentence,
                        is_final=is_final
                    )

            # Track metrics
            self.metrics["tts_times"].append(tts_time)

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error streaming sentence: {e}", exc_info=True)

    async def generate_llm_response_streaming(self, on_sentence_callback=None) -> str:
        """
        OPTIMIZED: Stream LLM response and process sentence-by-sentence.
        This reduces first-response latency from ~1500ms to ~400ms.
        """
        import re
        
        try:
            messages = self.conversation_history[-10:]
            llm_model = self.llm_model or "gpt-4o-mini"
            
            response = await self.llm_client.chat.completions.create(
                model=llm_model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.llm_max_tokens,
                stream=True  # KEY: Enable streaming!
            )
            
            buffer = ""
            full_response = ""
            sentence_pattern = re.compile(r'[.!?]+[\s\n]+|[.!?]+$')
            
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    token = delta.content
                    buffer += token
                    full_response += token
                    
                    # Check for complete sentences
                    while True:
                        match = sentence_pattern.search(buffer)
                        if not match:
                            break
                        
                        end_pos = match.end()
                        sentence = buffer[:end_pos].strip()
                        buffer = buffer[end_pos:]
                        
                        if sentence and on_sentence_callback:
                            await on_sentence_callback(sentence)
            
            # Handle remaining text
            if buffer.strip() and on_sentence_callback:
                await on_sentence_callback(buffer.strip())
            
            return full_response
            
        except Exception as e:
            logger.error(f"[CUSTOM] Error in streaming LLM: {e}", exc_info=True)
            return "I apologize, I'm having trouble processing that right now."

    async def check_calendar_intent(self):
        """Check if conversation indicates an appointment should be scheduled"""
        try:
            if not self.calendar_intent_service or not self.calendar_service:
                return

            # Format conversation for intent service
            messages = [
                {"role": msg["role"], "text": msg["content"]}
                for msg in self.conversation_history
                if msg["role"] in ("user", "assistant")
            ]

            # Get OpenAI API key
            openai_api_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                logger.warning("[CUSTOM] ⚠️ No OpenAI API key for calendar intent detection")
                return

            # Check for scheduling intent
            logger.info(f"[CUSTOM] 📅 Analyzing conversation for appointment details...")
            result = await self.calendar_intent_service.extract_from_conversation(
                messages=messages,
                openai_api_key=openai_api_key,
                timezone="UTC"  # You can make this configurable
            )

            if result and result.get("should_schedule"):
                logger.info(f"[CUSTOM] ✅ Appointment detected! Reason: {result.get('reason')}")
                logger.info(f"[CUSTOM] 📅 Appointment details: {result.get('appointment')}")

                # Schedule asynchronously to avoid blocking the conversation
                self.scheduling_task = asyncio.create_task(self.schedule_appointment(result))
            else:
                logger.debug(f"[CUSTOM] ℹ️ No scheduling intent detected yet")

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error checking calendar intent: {e}", exc_info=True)

    async def schedule_appointment(self, intent_result: Dict[str, Any]):
        """Schedule an appointment based on extracted intent"""
        try:
            appointment_data = intent_result.get("appointment", {})
            logger.info(f"[CUSTOM] 📅 === APPOINTMENT SCHEDULING START ===")
            logger.info(f"[CUSTOM] 📅 Details: {appointment_data}")

            # Round-robin selection of calendar account
            if not self.calendar_account_ids:
                logger.error("[CUSTOM] ❌ No calendar accounts configured!")
                return

            calendar_account_id = self.calendar_account_ids[0]  # Use first for now
            logger.info(f"[CUSTOM] 📅 Using calendar account: {calendar_account_id}")

            # Get database connection
            db = Database.get_db()
            calendar_accounts_collection = db['calendar_accounts']

            # Retrieve calendar account
            from bson import ObjectId
            calendar_account = calendar_accounts_collection.find_one({
                "_id": ObjectId(calendar_account_id)
            })

            if not calendar_account:
                logger.error(f"[CUSTOM] ❌ Calendar account {calendar_account_id} not found!")
                return

            # Check availability using the correct method
            logger.info(f"[CUSTOM] 📅 Checking availability for time slot...")
            start_time = appointment_data.get("start_iso")
            end_time = appointment_data.get("end_iso")

            # Parse datetime strings for availability check
            from datetime import datetime as dt
            start_dt = dt.fromisoformat(start_time) if start_time else None
            end_dt = dt.fromisoformat(end_time) if end_time else None

            if start_dt and end_dt:
                availability_result = await self.calendar_service.check_availability_across_calendars(
                    calendar_account_ids=[calendar_account_id],
                    start_time=start_dt,
                    end_time=end_dt
                )

                if not availability_result.get("is_available"):
                    conflicts = availability_result.get("conflicts", [])
                    logger.warning(f"[CUSTOM] ⚠️ Time slot conflict detected! Conflicts: {conflicts}")

                    # Generate a response to inform the user about the conflict
                    conflict_time = start_dt.strftime('%I:%M %p on %B %d')
                    conflict_response = f"I'm sorry, but the time slot at {conflict_time} is already booked. Could you please suggest an alternative time?"

                    # Add this to conversation and speak it
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": conflict_response
                    })

                    # Synthesize and send the conflict response
                    await self._speak_conflict_response(conflict_response)
                    return
            else:
                logger.warning("[CUSTOM] ⚠️ Missing start_time or end_time, skipping availability check")

            # Get access token for the calendar account
            access_token = await self.calendar_service.ensure_access_token(calendar_account)
            if not access_token:
                logger.error("[CUSTOM] ❌ Failed to get access token for calendar account")
                return

            # Determine provider and create the event using correct method
            provider = calendar_account.get("provider", "google")
            logger.info(f"[CUSTOM] 📅 Creating {provider} calendar event...")

            event_id = None
            if provider == "google":
                event_id = await self.calendar_service.create_google_event(access_token, appointment_data)
            elif provider == "microsoft":
                event_id = await self.calendar_service.create_microsoft_event(access_token, appointment_data)

            # Build event result dict for compatibility
            event_result = {"id": event_id} if event_id else None

            if event_result:
                logger.info(f"[CUSTOM] ✅ Appointment scheduled successfully!")
                logger.info(f"[CUSTOM] 📅 Event ID: {event_result.get('id')}")

                self.appointment_scheduled = True
                self.appointment_metadata = {
                    "event_id": event_result.get("id"),
                    "start_time": start_time,
                    "end_time": end_time,
                    "title": appointment_data.get("title"),
                    "calendar_account_id": calendar_account_id,
                    "attendee_name": appointment_data.get("attendee_name"),
                    "attendee_email": appointment_data.get("attendee_email"),
                    "attendee_phone": appointment_data.get("attendee_phone"),
                }

                # Log to database - update call_logs
                call_logs_collection = db['call_logs']
                call_logs_collection.update_one(
                    {"frejun_call_id": self.call_id},
                    {
                        "$set": {
                            "appointment_scheduled": True,
                            "appointment_metadata": self.appointment_metadata,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )

                # Save appointment record for email confirmations
                appointments_collection = db['appointments']
                appointment_doc = {
                    "user_id": ObjectId(self.user_id) if self.user_id else None,
                    "assistant_id": ObjectId(self.assistant_id) if self.assistant_id else None,
                    "call_sid": self.call_id,
                    "provider": calendar_account.get("provider", "google"),
                    "provider_event_id": event_result.get("id"),
                    "title": appointment_data.get("title", "Scheduled Appointment"),
                    "start_time": datetime.fromisoformat(start_time) if start_time else None,
                    "end_time": datetime.fromisoformat(end_time) if end_time else None,
                    "timezone": appointment_data.get("timezone", "UTC"),
                    "duration_minutes": appointment_data.get("duration_minutes", 30),
                    # Customer contact info for email confirmations
                    "customer_name": appointment_data.get("attendee_name"),
                    "customer_email": appointment_data.get("attendee_email"),
                    "customer_phone": appointment_data.get("attendee_phone"),
                    "notes": appointment_data.get("notes"),
                    "meeting_link": event_result.get("hangoutLink") or event_result.get("webLink"),
                    "status": "confirmed",
                    "created_at": datetime.now(timezone.utc)
                }
                appointments_collection.insert_one(appointment_doc)
                logger.info(f"[CUSTOM] 📝 Appointment record saved to database")

                # Send email confirmation if enabled
                try:
                    from app.services.appointment_email_service import appointment_email_service
                    if self.assistant_id and appointment_data.get("attendee_email"):
                        email_result = await appointment_email_service.send_appointment_confirmation(
                            assistant_id=self.assistant_id,
                            appointment_data=appointment_doc,
                            call_sid=self.call_id
                        )
                        if email_result.get("success"):
                            logger.info(f"[CUSTOM] 📧 Appointment confirmation email sent")
                        else:
                            logger.warning(f"[CUSTOM] ⚠️ Email not sent: {email_result.get('error')}")
                except Exception as email_error:
                    logger.error(f"[CUSTOM] ❌ Error sending email confirmation: {email_error}")

                logger.info(f"[CUSTOM] 🎉 === APPOINTMENT SCHEDULING COMPLETE ===")
            else:
                logger.error(f"[CUSTOM] ❌ Failed to create calendar event")

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error scheduling appointment: {e}", exc_info=True)

    async def log_interaction(self, user_text: str, assistant_text: str):
        """Log conversation to database"""
        try:
            db = Database.get_db()
            call_logs_collection = db['call_logs']

            # Update call log with transcript
            call_logs_collection.update_one(
                {"frejun_call_id": self.call_id},
                {
                    "$push": {
                        "transcript": {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "user": user_text,
                            "assistant": assistant_text
                        }
                    },
                    "$set": {
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )

        except Exception as e:
            logger.error(f"[CUSTOM] Error logging interaction: {e}")

    async def _save_execution_logs(self):
        """Save execution logs and performance metrics to database"""
        try:
            from app.config.database import Database
            db = Database.get_db()
            call_logs_collection = db['call_logs']

            # Calculate performance stats
            asr_times = self.metrics.get("asr_times", [])
            llm_times = self.metrics.get("llm_times", [])
            tts_times = self.metrics.get("tts_times", [])
            total_times = self.metrics.get("total_times", [])

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
            max_turns = max(len(asr_times), len(llm_times), len(tts_times))
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

            execution_logs = {
                "call_id": self.call_sid or self.call_id,
                "providers": {
                    "asr": self.asr_provider_name,
                    "tts": self.tts_provider_name,
                    "llm": self.llm_provider
                },
                "models": {
                    "asr_model": self.asr_model,
                    "tts_model": self.tts_model,
                    "tts_voice": self.tts_voice or self.voice,
                    "llm_model": self.llm_model
                },
                "performance_metrics": {
                    "total_turns": len(asr_times),
                    "session_duration_ms": sum(total_times) if total_times else 0,
                    "stats": stats,
                    "metrics": metrics_array
                },
                "timeline": [],
                "handler_type": "custom_provider_stream",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Try to update existing call log
            search_query = {
                "$or": [
                    {"call_sid": self.call_sid or self.call_id},
                    {"frejun_call_id": self.call_id}
                ]
            }

            # Also try MongoDB ObjectId if call_id looks like one
            if len(self.call_id) == 24:
                try:
                    from bson import ObjectId
                    search_query["$or"].append({"_id": ObjectId(self.call_id)})
                except:
                    pass

            # Build plain-text transcript from real-time conversation
            # This uses the actual ASR transcription and LLM responses - no re-transcription needed
            transcript_text = "\n".join([
                f"{msg['speaker'].upper()}: {msg['text']}"
                for msg in self.full_transcript
            ])

            # Prepare update data
            update_data = {
                "execution_logs": execution_logs,
                # Save the real-time transcript (from Deepgram ASR + LLM responses)
                "transcript": transcript_text,  # Plain text format for workflows
                "full_transcript": self.full_transcript,  # Structured format with timestamps
                "conversation_log": self.full_transcript,  # Alias for compatibility
                "transcript_source": "realtime",  # Mark as real-time (not post-call re-transcription)
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
                logger.info(f"[CUSTOM] 💾 Execution logs and real-time transcript saved for call {self.call_id} ({len(self.full_transcript)} turns)")
            else:
                logger.warning(f"[CUSTOM] ⚠️ Call log not found for {self.call_id}")

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error saving execution logs: {e}", exc_info=True)

    async def _trigger_post_call_workflows(self):
        """Trigger assigned workflows after call ends"""
        try:
            # Skip if no workflows assigned
            if not self.assigned_workflows:
                logger.debug(f"[CUSTOM] No workflows assigned to assistant")
                return

            # Skip if user_id not available
            if not self.user_id:
                logger.warning(f"[CUSTOM] Cannot trigger workflows: user_id not available")
                return

            # Determine trigger event based on call status
            trigger_event_value = "call_completed"
            if self.call_status == "failed":
                trigger_event_value = "call_failed"
            elif self.call_status == "no_answer":
                trigger_event_value = "call_no_answer"

            # Map UI events to TriggerEvent values
            event_mapping = {
                "CALL_COMPLETED": "call_completed",
                "CALL_FAILED": "call_failed",
                "APPOINTMENT_SCHEDULED": "call_completed",  # Handle as completed with metadata
            }

            # Check if this event should trigger workflows
            should_trigger = False
            for ui_event in self.workflow_trigger_events:
                if event_mapping.get(ui_event) == trigger_event_value:
                    should_trigger = True
                    break
                # Special case: APPOINTMENT_SCHEDULED
                if ui_event == "APPOINTMENT_SCHEDULED" and self.appointment_scheduled:
                    should_trigger = True
                    break

            if not should_trigger:
                logger.info(f"[CUSTOM] 📋 Event '{trigger_event_value}' not in trigger events: {self.workflow_trigger_events}")
                return

            logger.info(f"[CUSTOM] 🚀 Triggering post-call workflows for event: {trigger_event_value}")

            # Import workflow engine and customer data extraction
            from app.services.integrations.workflow_engine import WorkflowEngine
            from app.models.workflow import TriggerEvent
            from app.utils.customer_data_extraction import extract_customer_data, normalize_spoken_email

            # Calculate call duration in seconds
            call_duration_seconds = None
            if self.call_start_time and self.call_end_time:
                call_duration_seconds = (self.call_end_time - self.call_start_time).total_seconds()

            # Build plain text transcript for extraction
            transcript_text = "\n".join([
                f"{msg['speaker'].upper()}: {msg['text']}"
                for msg in self.full_transcript
            ])

            # ⚡ Extract customer data (name, email, location) from real-time transcript
            customer_data = extract_customer_data(transcript_text)
            customer_email = customer_data.get("email", "")
            customer_name = customer_data.get("name", "")
            customer_location = customer_data.get("location", "")

            # Also try to extract email from appointment metadata if available
            if not customer_email and self.appointment_metadata:
                customer_email = self.appointment_metadata.get("attendee_email", "")

            # Log extracted customer data
            if customer_email or customer_name:
                logger.info(f"[CUSTOM] 📧 Extracted customer data - Name: {customer_name or 'N/A'}, Email: {customer_email or 'N/A'}")

            # Build trigger data with rich call context
            trigger_data = {
                "call_id": self.call_id or self.call_sid,
                "call_sid": self.call_sid,
                "assistant_id": str(self.assistant_id) if self.assistant_id else None,
                "assistant_name": self.assistant_config.get("name", "Unknown Assistant"),
                "user_id": str(self.user_id) if self.user_id else None,
                "call_status": self.call_status,
                "platform": self.platform,
                # Timing information
                "call_start_time": self.call_start_time.isoformat() if self.call_start_time else None,
                "call_end_time": self.call_end_time.isoformat() if self.call_end_time else None,
                "call_duration_seconds": call_duration_seconds,
                "call_duration_turns": len(self.metrics.get("asr_times", [])),
                # Customer data (extracted from real-time transcript)
                "customer_email": customer_email,
                "customer_name": customer_name,
                "customer_location": customer_location,
                "customer_data": customer_data,  # Full extracted data
                # Conversation data
                "conversation_history": self.conversation_history[-10:],  # Last 10 turns for context
                "full_transcript": self.full_transcript,  # Complete transcript with timestamps
                "transcript_text": transcript_text,  # Plain text transcript for easy use in templates
                "transcript": transcript_text,  # Alias for compatibility
                # Latency metrics
                "avg_response_time_ms": (
                    sum(self.metrics.get("total_times", [0])) / len(self.metrics.get("total_times", [1]))
                    if self.metrics.get("total_times") else None
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Add appointment metadata if available
            if self.appointment_scheduled and self.appointment_metadata:
                trigger_data["appointment"] = self.appointment_metadata
                trigger_data["appointment_scheduled"] = True
                # Use appointment email if customer_email not found
                if not customer_email and self.appointment_metadata.get("attendee_email"):
                    trigger_data["customer_email"] = self.appointment_metadata["attendee_email"]

            # Get the appropriate TriggerEvent enum
            try:
                trigger_event = TriggerEvent(trigger_event_value)
            except ValueError:
                trigger_event = TriggerEvent.CALL_COMPLETED

            # Execute workflows
            engine = WorkflowEngine()

            # Only trigger workflows that are in the assigned_workflows list
            from app.config.database import Database
            db = Database.get_db()

            for workflow_id in self.assigned_workflows:
                try:
                    # Get the workflow
                    workflow = db.workflows.find_one({
                        "_id": ObjectId(workflow_id),
                        "is_active": True
                    })

                    if not workflow:
                        logger.warning(f"[CUSTOM] Workflow {workflow_id} not found or inactive")
                        continue

                    # Execute the workflow
                    result = await engine.execute_workflow(workflow, trigger_data)
                    logger.info(f"[CUSTOM] ✅ Workflow {workflow_id} executed: {result.get('success', False)}")

                except Exception as wf_error:
                    logger.error(f"[CUSTOM] ❌ Error executing workflow {workflow_id}: {wf_error}")

        except Exception as e:
            logger.error(f"[CUSTOM] ❌ Error triggering post-call workflows: {e}", exc_info=True)

    async def handle_stream(self):
        """Main handler for WebSocket streaming - Bolna-style internal loop"""
        self.is_running = True
        self.call_start_time = datetime.now(timezone.utc)  # Record call start time
        logger.info(f"[CUSTOM] 🎬 Starting handle_stream() for platform: {self.platform}")

        try:
            # Initialize providers
            logger.info(f"[CUSTOM] 🔧 Initializing providers...")
            if not await self.initialize_providers():
                logger.error(f"[CUSTOM] ❌ Failed to initialize providers")
                await self.websocket.close(code=1011, reason="Provider initialization failed")
                return

            logger.info(f"[CUSTOM] ✅ Providers initialized successfully")

            # ⚡ OPTIMIZATION: Start pre-warming LLM immediately after providers init
            # This runs in background while we wait for start event / send greeting
            self.llm_warmup_task = asyncio.create_task(self.prewarm_llm())
            logger.info(f"[CUSTOM] 🔥 LLM pre-warming started in background")

            # ⚡ CRITICAL: Wait for greeting pre-synthesis to complete before entering message loop
            # This ensures the greeting audio is READY for IMMEDIATE playback when call connects
            if self.greeting_synthesis_task:
                try:
                    logger.info(f"[CUSTOM] ⏳ Waiting for greeting pre-synthesis to complete...")
                    await asyncio.wait_for(self.greeting_synthesis_task, timeout=5.0)
                    if self.greeting_audio_cache:
                        logger.info(f"[CUSTOM] ✅ Greeting audio ready: {len(self.greeting_audio_cache)} bytes cached")
                    else:
                        logger.warning(f"[CUSTOM] ⚠️ Greeting pre-synthesis completed but no audio cached")
                except asyncio.TimeoutError:
                    logger.warning(f"[CUSTOM] ⚠️ Greeting pre-synthesis timeout - will synthesize on-demand")

            # For Twilio, wait for start event before sending greeting
            # For FreJun, send greeting immediately
            greeting_sent = False
            if self.platform != "twilio":
                logger.info(f"[CUSTOM] 📢 Sending greeting immediately (platform: {self.platform})")
                await self.send_greeting()
                greeting_sent = True
            else:
                logger.info(f"[CUSTOM] ⏳ Waiting for Twilio 'start' event before sending greeting (audio pre-cached: {self.greeting_audio_cache is not None})")

            # Main message loop (Bolna-style: internal WebSocket loop)
            logger.info(f"[CUSTOM] 🔄 Entering main WebSocket message loop...")
            message_count = 0
            while self.is_running:
                try:
                    # Receive message from platform (FreJun or Twilio)
                    # Increased timeout to 300s (5 minutes) to prevent premature disconnections
                    # The WebSocket will stay alive for long conversations and silence periods
                    message = await asyncio.wait_for(
                        self.websocket.receive_json(),
                        timeout=300.0  # 5 minutes - prevents 2-minute mute issue
                    )
                    message_count += 1
                    logger.debug(f"[CUSTOM] 📨 Received message #{message_count}: {message.get('event', message.get('type', 'unknown'))}")

                    # Handle platform-specific message formats
                    if self.platform == "frejun":
                        # FreJun format: {"type": "audio", "data": {"audio_b64": "..."}}
                        msg_type = message.get("type")

                        if msg_type == "audio":
                            # Audio data from caller
                            data_obj = message.get("data", {})
                            audio_b64 = data_obj.get("audio_b64")

                            if audio_b64:
                                # Decode base64 audio
                                audio_data = base64.b64decode(audio_b64)
                                await self.process_audio_chunk(audio_data)

                        elif msg_type == "start":
                            logger.info(f"[CUSTOM] FreJun stream started: {message}")

                        elif msg_type == "stop":
                            logger.info(f"[CUSTOM] FreJun stream stopped")
                            self.is_running = False
                            break

                    else:
                        # Twilio format: {"event": "media", "media": {"payload": "..."}}
                        event = message.get("event")

                        if event == "media":
                            # Audio data from caller
                            media = message.get("media", {})
                            payload = media.get("payload")

                            if payload:
                                # Decode base64 audio (Twilio sends μ-law encoded)
                                audio_data = base64.b64decode(payload)
                                logger.debug(f"[CUSTOM] 🎤 Received audio chunk: {len(audio_data)} bytes (μ-law)")

                                # Convert μ-law to PCM for ASR processing
                                try:
                                    audio_data = audioop.ulaw2lin(audio_data, 2)
                                    logger.debug(f"[CUSTOM] ✅ Decoded μ-law to PCM ({len(audio_data)} bytes)")
                                except Exception as decode_error:
                                    logger.error(f"[CUSTOM] ❌ Failed to decode μ-law audio: {decode_error}")
                                    continue

                                await self.process_audio_chunk(audio_data)
                            else:
                                logger.warning(f"[CUSTOM] ⚠️ Received media event with no payload")

                        elif event == "start":
                            # Extract streamSid and callSid from start event
                            start_data = message.get("start", {})
                            self.stream_sid = start_data.get("streamSid")
                            self.call_sid = start_data.get("callSid")
                            media_format = start_data.get("mediaFormat", {})

                            logger.info(f"[CUSTOM] 📞 Twilio stream START event received")
                            logger.info(f"[CUSTOM]   └─ StreamSID: {self.stream_sid}")
                            logger.info(f"[CUSTOM]   └─ CallSID: {self.call_sid}")
                            logger.info(f"[CUSTOM]   └─ Media Format: {media_format}")

                            # Reset VAD state for new call
                            if self.vad_processor:
                                self.vad_processor.reset()
                                logger.info(f"[CUSTOM]   └─ VAD state reset for new call")

                            # Update mark handler with stream_sid
                            self.mark_handler.set_stream_sid(self.stream_sid)
                            logger.info(f"[CUSTOM] ✅ Mark handler configured with stream_sid")

                            # Send greeting now that we have streamSid
                            if not greeting_sent:
                                logger.info(f"[CUSTOM] 📢 Sending greeting to caller...")
                                await self.send_greeting()
                                greeting_sent = True
                                logger.info(f"[CUSTOM] ✅ Greeting sent successfully")
                            else:
                                logger.info(f"[CUSTOM] ℹ️ Greeting already sent, skipping")

                        elif event == "mark":
                            # Handle mark event confirmation from Twilio
                            mark_data = message.get("mark", {})
                            mark_id = mark_data.get("name")
                            if mark_id:
                                logger.debug(f"[CUSTOM] ✔️ Mark event received: {mark_id}")
                                self.mark_handler.process_mark_received(mark_id)
                            else:
                                logger.warning(f"[CUSTOM] ⚠️ Mark event with no name")

                        elif event == "stop":
                            logger.info(f"[CUSTOM] 🛑 Twilio stream STOP event received")
                            self.is_running = False
                            break

                        else:
                            logger.debug(f"[CUSTOM] ℹ️ Unhandled Twilio event: {event}")

                except asyncio.TimeoutError:
                    # No message received for 5 minutes - connection still alive, just waiting for audio
                    logger.debug(f"[CUSTOM] ⏱️ No message for 5min (connection alive, waiting for audio)")
                    continue

                except WebSocketDisconnect:
                    logger.info(f"[CUSTOM] WebSocket disconnected")
                    self.is_running = False
                    break

        except Exception as e:
            logger.error(f"[CUSTOM] Error in stream handler: {e}", exc_info=True)

        finally:
            # Record call end time for duration tracking
            self.call_end_time = datetime.now(timezone.utc)

            # Process any remaining audio
            if len(self.audio_buffer) > 0:
                await self.transcribe_and_respond()

            # Mark call as completed (unless already marked as failed/no_answer)
            if self.call_status == "in_progress":
                self.call_status = "completed"

            # Save execution logs to database
            await self._save_execution_logs()

            # Log call quality report at end of call
            if self.quality_monitor:
                quality_report = self.quality_monitor.get_quality_report()
                logger.info(f"[QUALITY] 📊 Call Quality Report for {self.call_id}:")
                logger.info(f"[QUALITY]   ├─ Overall Score: {quality_report.get('quality', {}).get('overall_quality', 'N/A')}")
                logger.info(f"[QUALITY]   ├─ MOS Score: {quality_report.get('quality', {}).get('mos', 0):.2f}")
                logger.info(f"[QUALITY]   ├─ Network: loss={quality_report.get('network', {}).get('packet_loss_percent', 0):.2f}%, jitter={quality_report.get('network', {}).get('jitter_ms', 0):.1f}ms")
                logger.info(f"[QUALITY]   ├─ Audio: SNR={quality_report.get('audio', {}).get('snr_db', 0):.1f}dB, silence={quality_report.get('audio', {}).get('silence_percent', 0):.1f}%")
                logger.info(f"[QUALITY]   └─ Alerts: {quality_report.get('quality', {}).get('alert_count', 0)} total")

                # Store quality metrics for post-call analysis
                self.call_quality_report = quality_report

            # Trigger post-call workflows if any are assigned
            await self._trigger_post_call_workflows()

            logger.info(f"[CUSTOM] Stream handler finished for call {self.call_id}")


async def handle_custom_provider_stream(
    websocket: WebSocket,
    assistant_id: str,
    call_id: str
):
    """
    WebSocket endpoint handler for custom provider streaming

    This is called when an AI assistant is configured with custom providers
    (not using OpenAI Realtime API)
    """
    await websocket.accept()
    logger.info(f"[CUSTOM] WebSocket connected for assistant {assistant_id}")

    try:
        # Get assistant configuration
        db = Database.get_db()
        assistants_collection = db['assistants']

        if not ObjectId.is_valid(assistant_id):
            logger.error(f"[CUSTOM] Invalid assistant ID: {assistant_id}")
            await websocket.close(code=1008, reason="Invalid assistant ID")
            return

        assistant = assistants_collection.find_one({"_id": ObjectId(assistant_id)})

        if not assistant:
            logger.error(f"[CUSTOM] Assistant {assistant_id} not found")
            await websocket.close(code=1008, reason="Assistant not found")
            return

        # Get user and OpenAI API key
        user_id = assistant.get("user_id")
        if not user_id or not ObjectId.is_valid(str(user_id)):
            logger.error(f"[CUSTOM] Invalid user ID for assistant {assistant_id}")
            await websocket.close(code=1008, reason="Invalid user configuration")
            return

        users_collection = db['users']
        user = users_collection.find_one({"_id": ObjectId(str(user_id))})

        if not user:
            logger.error(f"[CUSTOM] User not found for assistant {assistant_id}")
            await websocket.close(code=1008, reason="User not found")
            return

        user_obj_id = ObjectId(str(user_id))

        # Resolve provider keys (ASR/TTS/LLM)
        provider_keys = resolve_provider_keys(db, assistant, user_obj_id)

        # Ensure we have an OpenAI key available for fallbacks
        openai_api_key = provider_keys.get("openai")
        if not openai_api_key:
            try:
                openai_api_key, _ = resolve_assistant_api_key(db, assistant, required_provider="openai")
                provider_keys['openai'] = openai_api_key
            except HTTPException as key_error:
                env_openai_key = os.getenv("OPENAI_API_KEY")
                if env_openai_key:
                    provider_keys['openai'] = env_openai_key
                    openai_api_key = env_openai_key
                else:
                    logger.error(f"[CUSTOM] OpenAI API key not configured for assistant: {key_error.detail}")
                    await websocket.close(code=1008, reason="OpenAI API key not configured")
                    return

        # Build assistant config
        assistant_config = {
            "assistant_id": str(assistant["_id"]),
            "system_message": assistant.get("system_message", "You are a helpful AI assistant."),
            "voice": assistant.get("voice", "alloy"),
            "temperature": assistant.get("temperature", 0.8),
            # Use call_greeting if available, otherwise fallback to greeting field
            "greeting": assistant.get("call_greeting") or assistant.get("greeting", "Hello! Thanks for calling. How can I help you today?"),
            "asr_provider": assistant.get("asr_provider", "openai"),
            "tts_provider": assistant.get("tts_provider", "openai"),
            "asr_language": assistant.get("asr_language", "en"),
            "asr_model": assistant.get("asr_model"),
            "tts_model": assistant.get("tts_model"),
            "tts_voice": assistant.get("tts_voice") or assistant.get("voice", "alloy"),
            "tts_speed": assistant.get("tts_speed", 1.0),
            "enable_precise_transcript": assistant.get("enable_precise_transcript", False),
            "interruption_threshold": assistant.get("interruption_threshold", 2),
            "response_rate": assistant.get("response_rate", "balanced"),
            "check_user_online": assistant.get("check_user_online", True),
            "audio_buffer_size": assistant.get("audio_buffer_size", 200),
            "llm_provider": assistant.get("llm_provider", "openai"),
            "llm_model": assistant.get("llm_model"),
            "llm_max_tokens": assistant.get("llm_max_tokens", 150),
            "bot_language": assistant.get("bot_language", "en"),
            # VAD & Noise Suppression settings (Silero VAD for intelligent speech detection)
            # OPTIMIZED: Faster defaults for better interruption response
            "use_vad": assistant.get("use_vad", True),  # Enable Silero VAD by default
            "noise_suppression_level": assistant.get("noise_suppression_level", "medium"),
            "vad_threshold": assistant.get("vad_threshold", 0.4),  # More sensitive (was 0.5)
            "vad_min_speech_ms": assistant.get("vad_min_speech_ms", 150),  # Faster (was 250)
            "vad_min_silence_ms": assistant.get("vad_min_silence_ms", 200),  # Faster (was 300)
            "vad_prefix_padding_ms": assistant.get("vad_prefix_padding_ms", 300),
            "vad_silence_duration_ms": assistant.get("vad_silence_duration_ms", 500),
            # Real-time interruption settings
            "enable_interruption": assistant.get("enable_interruption", True),  # Enable by default
            "interruption_probability_threshold": assistant.get("interruption_probability_threshold", 0.6),
            "interruption_min_chunks": assistant.get("interruption_min_chunks", 2),
            # Streaming mode for lower latency
            "use_streaming_mode": assistant.get("use_streaming_mode", False),  # Opt-in for now
            # Calendar integration settings
            "calendar_enabled": assistant.get("calendar_enabled", False),
            "calendar_account_ids": assistant.get("calendar_account_ids", []),
            "provider_keys": provider_keys,
            # Real-time tool calling (Vapi-like functionality)
            "tools_enabled": assistant.get("tools_enabled", False),
            "tools": assistant.get("tools", []),
            "max_tool_calls_per_turn": assistant.get("max_tool_calls_per_turn", 5),
            "tool_execution_timeout": assistant.get("tool_execution_timeout", 30),
        }

        logger.info(f"[CUSTOM] Starting stream with providers: ASR={assistant_config['asr_provider']}, TTS={assistant_config['tts_provider']}")

        # Create and run stream handler (FreJun platform)
        handler = CustomProviderStreamHandler(
            websocket=websocket,
            assistant_config=assistant_config,
            openai_api_key=openai_api_key,
            call_id=call_id,
            platform="frejun",
            provider_keys=provider_keys
        )

        await handler.handle_stream()

    except Exception as e:
        logger.error(f"[CUSTOM] Error in custom provider stream: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except:
            pass

    logger.info(f"[CUSTOM] Custom provider stream ended for assistant {assistant_id}")
