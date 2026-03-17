"""
WebRTC Voice Call Handler

Handles voice calls over WebRTC for web and mobile clients.
Uses the same ASR → LLM → TTS pipeline as WebSocket handlers,
but with WebRTC for lower latency audio transport (20-50ms vs 100-300ms).

Architecture:
1. Client connects via WebSocket for signaling
2. WebRTC peer connection established
3. Audio flows over UDP (WebRTC data channel or media track)
4. Server processes: ASR (Deepgram) → LLM (OpenAI) → TTS (ElevenLabs)
5. Response audio sent back via WebRTC

Note: This is for web/mobile clients ONLY.
Phone calls (PSTN) must use WebSocket handlers (Twilio requirement).
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Callable, Awaitable

from fastapi import WebSocket, WebSocketDisconnect

from .signaling_server import WebRTCSignalingServer, WebRTCSession, signaling_server
from .ice_config import get_rtc_configuration

# Import streaming components (same as optimized handler)
from ..call_handlers.streaming_asr_handler import StreamingDeepgramASR
from ..call_handlers.streaming_llm_handler import StreamingLLMHandler, ConversationManager

logger = logging.getLogger(__name__)


class WebRTCVoiceHandler:
    """
    WebRTC-based voice call handler for web/mobile clients.

    Benefits over WebSocket:
    - Lower latency (UDP vs TCP): 20-50ms vs 100-300ms
    - Better handling of packet loss
    - Native browser support for audio
    - Adaptive bitrate

    Pipeline:
    - Audio input via WebRTC data channel (base64 encoded)
    - Deepgram streaming ASR for transcription
    - OpenAI streaming for LLM response
    - ElevenLabs/Sarvam/Cartesia for TTS
    - Audio output via WebRTC data channel
    """

    # Keepalive interval — prevents Deepgram from disconnecting on silence
    KEEPALIVE_INTERVAL = 15

    def __init__(
        self,
        session: WebRTCSession,
        assistant_config: Dict[str, Any],
        provider_keys: Dict[str, str]
    ):
        self.session = session
        self.config = assistant_config
        self.provider_keys = provider_keys

        # Pipeline components
        self.asr: Optional[StreamingDeepgramASR] = None
        self.llm: Optional[StreamingLLMHandler] = None
        self.tts = None  # TTS instance
        self.conversation: Optional[ConversationManager] = None

        # State
        self.is_running = False
        self.is_processing = False
        self.is_speaking = False
        self.pending_transcript = ""

        # Interruption control
        self.interrupted = False
        self.current_generation_id = 0

        # Energy-based barge-in
        self._energy_barge_in_count = 0

        # Client playback tracking: True from when we start sending audio
        # until client confirms playback is done (playback-complete message).
        # Prevents feeding echo to ASR while client is still playing audio.
        self._client_playback_active = False
        self._client_playback_start_time = 0.0

        # Predict-and-scrap state
        self._speculative_transcript = ""
        self._speculative_task: Optional[asyncio.Task] = None

        # Keepalive
        self.keepalive_task: Optional[asyncio.Task] = None
        self.last_activity_time = time.time()

        # Call timing
        self.call_start_time: Optional[float] = None

        # Metrics
        self.metrics = {
            "asr_latency_ms": [],
            "llm_latency_ms": [],
            "tts_latency_ms": [],
            "total_latency_ms": [],
            "ttft_ms": []  # Time to first token (audio)
        }

        # Conversation transcript (for saving)
        self.full_transcript: List[Dict] = []

        # LLM pre-warm
        self.llm_warmed_up = False

        # Calendar scheduling state (same as Twilio handler)
        self.calendar_enabled = self.config.get("calendar_enabled", False)
        self.calendar_account_ids = self.config.get("calendar_account_ids", [])
        self.calendar_account_id = self.config.get("calendar_account_id")
        self.calendar_provider = self.config.get("calendar_provider", "google")
        self.timezone = self.config.get("timezone", "America/New_York")
        self.assistant_id = self.config.get("assistant_id")
        self.user_id = self.config.get("user_id") or session.user_id
        self.appointment_scheduled = False

        if self.calendar_enabled:
            logger.info(f"[WEBRTC-HANDLER] Calendar enabled with {len(self.calendar_account_ids)} calendar(s)")

        logger.info(f"[WEBRTC-HANDLER] Initialized for session {session.session_id}")

    async def initialize(self):
        """Initialize pipeline components"""
        logger.info("[WEBRTC-HANDLER] Initializing voice pipeline...")

        # Initialize ASR — hardcoded to Deepgram Nova-2
        asr_provider = self.config.get("asr_provider", "deepgram").lower()

        if asr_provider == "whisper":
            from ..call_handlers.offline_asr_handler import OfflineWhisperASR
            self.asr = OfflineWhisperASR(
                model_size=self.config.get("asr_model", "base"),
                language=self.config.get("asr_language", "en"),
                sample_rate=16000,
                encoding="linear16",
                on_transcript=self._on_transcript,
                on_utterance_end=self._on_utterance_end,
                on_speech_started=self._on_speech_started,
                endpointing_ms=200,
            )
            logger.info(f"[WEBRTC-HANDLER] Using Whisper offline ASR (model: {self.config.get('asr_model', 'base')})")
        else:
            deepgram_key = self.provider_keys.get("deepgram") or os.getenv("DEEPGRAM_API_KEY")
            if not deepgram_key:
                raise ValueError("Deepgram API key required for streaming ASR")
            self.asr = StreamingDeepgramASR(
                api_key=deepgram_key,
                model=self.config.get("asr_model", "nova-2"),
                language=self.config.get("asr_language", "en"),
                sample_rate=16000,
                encoding="linear16",
                on_transcript=self._on_transcript,
                on_utterance_end=self._on_utterance_end,
                on_speech_started=self._on_speech_started,
                endpointing_ms=200
            )

        # Initialize LLM
        import openai
        llm_provider = self.config.get("llm_provider", "openai").lower()

        if llm_provider == "ollama":
            ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            llm_client = openai.AsyncOpenAI(base_url=ollama_base_url, api_key="ollama")
            default_model = "llama3.2"
            # Resolve model name against actually available Ollama models
            from app.utils.ollama_utils import resolve_ollama_model
            requested_model = self.config.get("llm_model") or default_model
            resolved_model = await resolve_ollama_model(requested_model)
            if resolved_model != requested_model:
                logger.info(f"[WEBRTC-HANDLER] Ollama model resolved: '{requested_model}' -> '{resolved_model}'")
            logger.info(f"[WEBRTC-HANDLER] Using Ollama LLM at {ollama_base_url}")
        else:
            openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise ValueError("OpenAI API key required")
            llm_client = openai.AsyncOpenAI(api_key=openai_key)
            default_model = "gpt-4-turbo"
            resolved_model = self.config.get("llm_model") or default_model

        self.llm = StreamingLLMHandler(
            openai_client=llm_client,
            model=resolved_model,
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("llm_max_tokens", 150)
        )

        # Initialize TTS (may need a separate OpenAI client if TTS uses OpenAI)
        openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
        openai_client_for_tts = openai.AsyncOpenAI(api_key=openai_key) if openai_key else None
        await self._initialize_tts(openai_client_for_tts)

        # Initialize conversation manager
        self.conversation = ConversationManager(
            system_message=self.config.get("system_message", "You are a helpful assistant."),
            max_history=50
        )

        # Set up callbacks for WebRTC session
        self.session.on_audio_data = self._handle_audio_data
        self.session.on_barge_in = self._handle_client_barge_in
        self.session.on_playback_complete = self._handle_playback_complete

        logger.info("[WEBRTC-HANDLER] Pipeline initialized")

    async def _initialize_tts(self, openai_client):
        """Initialize TTS provider"""
        from ..call_handlers.streaming_tts_handler import (
            StreamingElevenLabsTTS,
            StreamingSarvamTTS,
            StreamingCartesiaTTS,
            StreamingOpenAITTS
        )

        tts_provider = self.config.get("tts_provider", "elevenlabs").lower()
        tts_voice = self.config.get("tts_voice", "alloy")

        logger.info(f"[WEBRTC-HANDLER] Initializing TTS: {tts_provider}")

        if tts_provider == "sarvam":
            sarvam_key = self.provider_keys.get("sarvam") or os.getenv("SARVAM_API_KEY")
            if sarvam_key:
                self.tts = StreamingSarvamTTS(
                    api_key=sarvam_key,
                    voice=tts_voice or "manisha",
                    model=self.config.get("tts_model", "bulbul:v2"),
                    language=self.config.get("bot_language", "hi-IN"),
                    for_browser=True
                )
            elif openai_client:
                self.tts = StreamingOpenAITTS(client=openai_client, voice="alloy", for_browser=True)
            else:
                raise ValueError("No Sarvam API key and no OpenAI key for TTS fallback")

        elif tts_provider == "cartesia":
            cartesia_key = self.provider_keys.get("cartesia") or os.getenv("CARTESIA_API_KEY")
            if cartesia_key:
                self.tts = StreamingCartesiaTTS(
                    api_key=cartesia_key,
                    voice=tts_voice or "sonic",
                    model=self.config.get("tts_model", "sonic-english"),
                    for_browser=True
                )
            elif openai_client:
                self.tts = StreamingOpenAITTS(client=openai_client, voice="alloy", for_browser=True)
            else:
                raise ValueError("No Cartesia API key and no OpenAI key for TTS fallback")

        elif tts_provider == "openai":
            if not openai_client:
                raise ValueError("OpenAI API key required for OpenAI TTS")
            self.tts = StreamingOpenAITTS(
                client=openai_client,
                voice=tts_voice or "alloy",
                for_browser=True
            )
        elif tts_provider == "piper":
            from ..call_handlers.offline_tts_handler import OfflinePiperTTS
            self.tts = OfflinePiperTTS(
                voice=tts_voice or "en_US-lessac-medium",
                for_browser=True
            )
            logger.info(f"[WEBRTC-HANDLER] Using Piper offline TTS (voice: {tts_voice})")
        else:
            # Default to ElevenLabs Flash v2.5
            elevenlabs_key = self.provider_keys.get("elevenlabs") or os.getenv("ELEVENLABS_API_KEY")
            if elevenlabs_key:
                self.tts = StreamingElevenLabsTTS(
                    api_key=elevenlabs_key,
                    voice=tts_voice or "alloy",
                    model=self.config.get("tts_model", "eleven_flash_v2_5"),
                    output_format="pcm_24000"
                )
            elif openai_client:
                self.tts = StreamingOpenAITTS(
                    client=openai_client,
                    voice=tts_voice or "alloy",
                    for_browser=True
                )
            else:
                raise ValueError("No TTS provider available. Set an ElevenLabs or OpenAI API key.")

        logger.info(f"[WEBRTC-HANDLER] TTS initialized: {tts_provider}")

    async def start(self):
        """Start the voice call"""
        self.is_running = True
        self.call_start_time = time.time()

        # Connect to Deepgram ASR
        await self.asr.connect()

        # Pre-warm LLM in background
        asyncio.create_task(self._prewarm_llm())

        # Start keepalive loop (prevents Deepgram disconnect on silence)
        self.keepalive_task = asyncio.create_task(self._keepalive_loop())

        # Send greeting in background so the message loop isn't blocked —
        # this lets the server process audio immediately (user can barge-in
        # during the greeting).
        greeting = self.config.get("greeting", "Hello! How can I help you today?")
        if greeting:
            asyncio.create_task(self._send_greeting(greeting))

        logger.info(f"[WEBRTC-HANDLER] Call started: {self.session.session_id}")

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Strip markdown formatting so TTS doesn't read **, *, #, etc. aloud."""
        # Remove bold/italic markers: **text** → text, *text* → text
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
        # Remove heading markers: ### Heading → Heading
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
        # Remove bullet markers: * item or - item → item
        text = re.sub(r'^\s*[*\-+]\s+', '', text, flags=re.MULTILINE)
        # Remove numbered list markers: 1. item → item
        text = re.sub(r'^\s*\d+[.)]\s+', '', text, flags=re.MULTILINE)
        # Remove inline code backticks: `code` → code
        text = re.sub(r'`([^`]*)`', r'\1', text)
        # Remove link syntax: [text](url) → text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Collapse multiple spaces/newlines
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'  +', ' ', text)
        return text.strip()

    async def _send_greeting(self, greeting: str):
        """Send greeting in a background task (non-blocking)."""
        try:
            await signaling_server.send_transcript_to_client(
                self.session.session_id, greeting, is_final=True, speaker="assistant"
            )
            await self._speak(greeting)
            self.full_transcript.append({
                "speaker": "assistant",
                "text": greeting,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"[WEBRTC-HANDLER] Greeting error: {e}")

    async def _prewarm_llm(self):
        """Pre-warm LLM to eliminate cold start latency"""
        if self.llm_warmed_up:
            return

        try:
            warmup_start = time.time()
            logger.info("[WEBRTC-HANDLER] Pre-warming LLM...")

            warmup_messages = [
                {"role": "system", "content": "Respond with OK."},
                {"role": "user", "content": "Ready?"}
            ]

            response = await self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=warmup_messages,
                temperature=0.1,
                max_tokens=5,
                stream=False
            )

            warmup_time = (time.time() - warmup_start) * 1000
            self.llm_warmed_up = True
            logger.info(f"[WEBRTC-HANDLER] LLM pre-warmed in {warmup_time:.0f}ms")

        except Exception as e:
            logger.warning(f"[WEBRTC-HANDLER] LLM pre-warm failed: {e}")

    async def _keepalive_loop(self):
        """Send periodic keepalive to Deepgram ASR to prevent disconnect on silence"""
        logger.info("[WEBRTC-HANDLER] Keepalive loop started")
        while self.is_running:
            try:
                await asyncio.sleep(self.KEEPALIVE_INTERVAL)
                if not self.is_running:
                    break

                # Send keepalive to Deepgram (skip for offline ASR which has no WebSocket)
                if self.asr and self.asr.is_connected and self.asr.ws:
                    try:
                        keepalive_msg = json.dumps({"type": "KeepAlive"})
                        await self.asr.ws.send(keepalive_msg)
                    except Exception as e:
                        logger.warning(f"[WEBRTC-HANDLER] Deepgram keepalive failed: {e}")
                        await self._reconnect_asr()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WEBRTC-HANDLER] Keepalive error: {e}")
        logger.info("[WEBRTC-HANDLER] Keepalive loop stopped")

    async def _reconnect_asr(self):
        """Reconnect to ASR if connection is lost"""
        logger.info("[WEBRTC-HANDLER] Attempting ASR reconnect...")
        try:
            if self.asr:
                try:
                    await self.asr.close()
                except Exception:
                    pass

            asr_provider = self.config.get("asr_provider", "deepgram").lower()

            if asr_provider == "whisper":
                from ..call_handlers.offline_asr_handler import OfflineWhisperASR
                self.asr = OfflineWhisperASR(
                    model_size=self.config.get("asr_model", "base"),
                    language=self.config.get("asr_language", "en"),
                    sample_rate=16000,
                    encoding="linear16",
                    on_transcript=self._on_transcript,
                    on_utterance_end=self._on_utterance_end,
                    on_speech_started=self._on_speech_started,
                    endpointing_ms=200,
                )
            else:
                deepgram_key = self.provider_keys.get("deepgram") or os.getenv("DEEPGRAM_API_KEY")
                self.asr = StreamingDeepgramASR(
                    api_key=deepgram_key,
                    model=self.config.get("asr_model", "nova-2"),
                    language=self.config.get("asr_language", "en"),
                    sample_rate=16000,
                    encoding="linear16",
                    on_transcript=self._on_transcript,
                    on_utterance_end=self._on_utterance_end,
                    on_speech_started=self._on_speech_started,
                    endpointing_ms=200
                )

            await self.asr.connect()
            self.session.on_audio_data = self._handle_audio_data
            logger.info("[WEBRTC-HANDLER] ASR reconnected successfully")
        except Exception as e:
            logger.error(f"[WEBRTC-HANDLER] ASR reconnection failed: {e}")

    async def _handle_audio_data(self, audio_bytes: bytes):
        """Handle incoming audio from WebRTC"""
        self.last_activity_time = time.time()
        if not self.is_running:
            return

        # ── While AI is speaking OR client is still playing audio: ONLY check energy for barge-in ──
        # CRITICAL: Do NOT feed audio to ASR while speaking!
        # The mic picks up the AI's own audio (echo). If we feed that to
        # Whisper, it transcribes the echo as "user speech" and the AI
        # responds to itself in an infinite loop.
        # _client_playback_active covers the gap between "server done sending"
        # and "client done playing" — without this, echo leaks to ASR.
        #
        # Safety: force-reset _client_playback_active after 60s to prevent
        # permanent lockout if playback-complete message is lost.
        if self._client_playback_active and (time.time() - self._client_playback_start_time) > 60:
            logger.warning("[WEBRTC-HANDLER] _client_playback_active timeout (60s), force-resetting")
            self._client_playback_active = False

        if self.is_speaking or self.is_processing or self._client_playback_active:
            if len(audio_bytes) >= 4:
                try:
                    samples = np.frombuffer(audio_bytes, dtype=np.int16)
                    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
                except Exception:
                    rms = 0.0

                if rms > 300:
                    self._energy_barge_in_count += 1
                    if self._energy_barge_in_count >= 2:
                        logger.info(f"[WEBRTC-HANDLER] ENERGY BARGE-IN! RMS={rms:.0f}")
                        await self._handle_interruption()
                        self._energy_barge_in_count = 0
                else:
                    self._energy_barge_in_count = 0
            return  # ← STOP here — never feed to ASR while AI is active

        # ── AI is idle: normal ASR processing ──
        self._energy_barge_in_count = 0

        if self.asr:
            if not self.asr.is_connected:
                logger.warning("[WEBRTC-HANDLER] ASR disconnected, reconnecting...")
                await self._reconnect_asr()

            if self.asr.is_connected:
                await self.asr.send_audio(audio_bytes)

    async def _handle_client_barge_in(self):
        """Called when CLIENT detects user speaking during AI speech."""
        logger.info(f"[WEBRTC-HANDLER] CLIENT BARGE-IN (is_speaking={self.is_speaking}, "
                     f"client_playing={self._client_playback_active})")
        self._client_playback_active = False
        if self.is_speaking or self.is_processing:
            await self._handle_interruption()

    async def _handle_playback_complete(self):
        """Called when client finishes playing all buffered audio."""
        logger.info("[WEBRTC-HANDLER] Client playback complete — ready for ASR")
        self._client_playback_active = False

    async def _on_speech_started(self):
        """Called when user starts speaking"""
        logger.info(f"[WEBRTC-HANDLER] Speech started (is_speaking={self.is_speaking}, "
                     f"is_processing={self.is_processing})")
        # Check for barge-in
        if self.is_speaking:
            logger.info("[WEBRTC-HANDLER] BARGE-IN detected (via VAD)!")
            await self._handle_interruption()

    async def _on_transcript(self, transcript: str, is_final: bool):
        """Handle transcript from ASR"""
        if not transcript:
            return

        # Forward transcript to browser in real-time
        await signaling_server.send_transcript_to_client(
            self.session.session_id, transcript, is_final, speaker="user"
        )

        # Barge-in check
        if self.is_speaking and len(transcript.strip()) > 3:
            logger.info(f"[WEBRTC-HANDLER] BARGE-IN: {transcript[:30]}...")
            await self._handle_interruption()

        if is_final:
            logger.info(f"[WEBRTC-HANDLER] Final: {transcript}")

            # Check speculative processing
            if self._speculative_task and not self._speculative_task.done():
                if self._speculative_transcript != transcript:
                    logger.info("[WEBRTC-HANDLER] Scrapping speculative - transcript changed")
                    self._speculative_task.cancel()
                    self._speculative_task = None
                else:
                    logger.info("[WEBRTC-HANDLER] Using speculative response!")
                    self.pending_transcript = ""
                    return

            # Clear pending so _on_utterance_end doesn't duplicate
            self.pending_transcript = ""
            asyncio.create_task(self._process_user_input(transcript))

        else:
            # Interim - predict-and-scrap
            if (not self.is_processing
                and not self.is_speaking
                and len(transcript.strip()) > 10
                and self._looks_complete(transcript)):

                if self._speculative_task and not self._speculative_task.done():
                    self._speculative_task.cancel()

                self._speculative_transcript = transcript
                self._speculative_task = asyncio.create_task(
                    self._process_user_input_speculative(transcript)
                )
                logger.debug(f"[WEBRTC-HANDLER] Speculative: {transcript[:30]}...")

            self.pending_transcript = transcript

    def _looks_complete(self, transcript: str) -> bool:
        """Check if interim transcript looks complete"""
        text = transcript.strip().lower()

        question_words = ['what', 'when', 'where', 'who', 'why', 'how', 'can', 'could', 'would', 'is', 'are', 'do', 'does']
        if any(text.startswith(w) for w in question_words) and len(text.split()) >= 3:
            return True

        ending_patterns = ['please', 'thanks', 'thank you', 'okay', 'yes', 'no', 'sure', 'right']
        if any(text.endswith(p) for p in ending_patterns):
            return True

        if len(text.split()) >= 5:
            return True

        return False

    async def _process_user_input_speculative(self, text: str):
        """Speculative processing - can be cancelled"""
        try:
            await asyncio.sleep(0.15)  # 150ms delay
            await self._process_user_input(text)
        except asyncio.CancelledError:
            logger.debug("[WEBRTC-HANDLER] Speculative cancelled")
            raise

    async def _on_utterance_end(self):
        """User stopped speaking"""
        if self.pending_transcript and not self.is_processing:
            text = self.pending_transcript
            self.pending_transcript = ""
            logger.info(f"[WEBRTC-HANDLER] Utterance end: {text}")
            # MUST use create_task — awaiting here would block the message loop
            # and prevent audio processing (barge-in) during the AI response.
            asyncio.create_task(self._process_user_input(text))

    async def _handle_interruption(self):
        """Handle barge-in (user interruption)"""
        # Debounce: skip if already interrupted (multiple sources can fire at once)
        if self.interrupted and not self.is_speaking and not self.is_processing:
            return

        logger.info("[WEBRTC-HANDLER] Handling interruption...")

        self.interrupted = True
        self.current_generation_id += 1
        self.is_speaking = False
        self.is_processing = False
        self._client_playback_active = False

        # Reset ASR/VAD state so it starts fresh for the user's new utterance.
        # Without this, stale VAD buffers cause delayed speech detection.
        if self.asr:
            if hasattr(self.asr, '_is_speech_active'):
                self.asr._is_speech_active = False
                self.asr._speech_started_fired = False
                self.asr._audio_buffer = []
                self.asr._buffer_sample_count = 0
            if hasattr(self.asr, '_vad') and self.asr._vad:
                self.asr._vad.audio_buffer = []
                self.asr._vad.is_speaking = False
                self.asr._vad.silence_start_ms = 0

        # Notify client to stop audio playback
        if self.session.websocket:
            try:
                await self.session.websocket.send_json({
                    "type": "interrupt",
                    "sessionId": self.session.session_id
                })
            except Exception as e:
                logger.warning(f"[WEBRTC-HANDLER] Failed to send interrupt: {e}")

        await signaling_server.send_call_state_to_client(
            self.session.session_id, "listening"
        )

        logger.info("[WEBRTC-HANDLER] Interruption handled")

    async def _process_user_input(self, text: str):
        """Process user input through the pipeline"""
        if self.is_processing:
            return

        if not text or len(text.strip()) < 2:
            return

        self.is_processing = True
        self.interrupted = False
        self.current_generation_id += 1
        current_gen_id = self.current_generation_id

        pipeline_start = time.time()

        try:
            logger.info(f"[WEBRTC-HANDLER] Processing: {text}")

            # Add to transcript
            self.full_transcript.append({
                "speaker": "user",
                "text": text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            # Add to conversation
            self.conversation.add_user_message(text)

            first_audio_sent = False
            llm_start = time.time()

            async def on_sentence(sentence: str):
                """Process each sentence from LLM"""
                nonlocal first_audio_sent

                if self.interrupted or current_gen_id != self.current_generation_id:
                    return

                if not sentence.strip():
                    return

                self.is_speaking = True
                self._client_playback_active = True
                self._client_playback_start_time = time.time()
                await signaling_server.send_call_state_to_client(
                    self.session.session_id, "ai-speaking"
                )

                # Forward assistant text to client for transcript display
                await signaling_server.send_transcript_to_client(
                    self.session.session_id, sentence, is_final=True, speaker="assistant"
                )

                # Strip markdown for TTS (keep original for transcript above)
                speech_text = self._clean_for_speech(sentence)
                if not speech_text:
                    return

                tts_start = time.time()

                # Synthesize and send via WebRTC
                if hasattr(self.tts, 'synthesize_streaming'):
                    async def send_chunk(chunk: bytes):
                        if not self.interrupted and current_gen_id == self.current_generation_id:
                            await self._send_audio_to_client(chunk)

                    await self.tts.synthesize_streaming(speech_text, on_audio_chunk=send_chunk)
                else:
                    audio = await self.tts.synthesize(speech_text)
                    if audio and not self.interrupted:
                        await self._send_audio_to_client(audio)

                tts_time = (time.time() - tts_start) * 1000

                if not first_audio_sent:
                    first_audio_sent = True
                    ttft = (time.time() - pipeline_start) * 1000
                    logger.info(f"[WEBRTC-HANDLER] TTFT: {ttft:.0f}ms")
                    self.metrics["ttft_ms"].append(ttft)
                    self.metrics["total_latency_ms"].append(ttft)

                self.metrics["tts_latency_ms"].append(tts_time)

            # Stream LLM response (with early-abort on barge-in)
            full_response = await self.llm.stream_response(
                self.conversation.get_messages(),
                on_sentence=on_sentence,
                is_cancelled=lambda: self.interrupted or current_gen_id != self.current_generation_id
            )

            llm_time = (time.time() - llm_start) * 1000
            self.metrics["llm_latency_ms"].append(llm_time)

            # Save response
            if not self.interrupted and full_response:
                self.conversation.add_assistant_message(full_response)
                self.full_transcript.append({
                    "speaker": "assistant",
                    "text": full_response,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            # Notify client speech ended
            if self.session.websocket and not self.interrupted:
                try:
                    await self.session.websocket.send_json({
                        "type": "speech-end",
                        "sessionId": self.session.session_id
                    })
                    await signaling_server.send_call_state_to_client(
                        self.session.session_id, "listening"
                    )
                except Exception:
                    pass

            total_time = (time.time() - pipeline_start) * 1000
            logger.info(f"[WEBRTC-HANDLER] Pipeline complete: LLM={llm_time:.0f}ms, Total={total_time:.0f}ms")

            # Check for calendar scheduling intent (runs in background)
            if self.calendar_enabled and not self.appointment_scheduled:
                asyncio.create_task(self._maybe_schedule_from_conversation())

        except Exception as e:
            logger.error(f"[WEBRTC-HANDLER] Pipeline error: {e}", exc_info=True)
        finally:
            # Only clear state if this is still the active generation.
            # A stale task must NOT clobber a newer task's is_speaking/is_processing,
            # otherwise barge-in breaks for the new response.
            if current_gen_id == self.current_generation_id:
                self.is_processing = False
                self.is_speaking = False
                # NOTE: Do NOT send call-state:listening here — the client manages
                # its own state based on actual audio playback completion.
                # _client_playback_active stays True until client sends playback-complete.

    async def _speak(self, text: str):
        """Synthesize and send audio"""
        try:
            self.is_speaking = True
            self._client_playback_active = True
            self._client_playback_start_time = time.time()

            # Tell client we're speaking so it can:
            # 1) activate barge-in detection  2) accept audio for playback
            await signaling_server.send_call_state_to_client(
                self.session.session_id, "ai-speaking"
            )

            # Strip markdown for TTS
            speech_text = self._clean_for_speech(text)
            if not speech_text:
                return

            if hasattr(self.tts, 'synthesize_streaming'):
                async def send_chunk_if_not_interrupted(chunk: bytes):
                    if not self.interrupted:
                        await self._send_audio_to_client(chunk)

                await self.tts.synthesize_streaming(
                    speech_text,
                    on_audio_chunk=send_chunk_if_not_interrupted
                )
            else:
                audio = await self.tts.synthesize(speech_text)
                if audio and not self.interrupted:
                    await self._send_audio_to_client(audio)

            # Notify speech end (only if we weren't interrupted)
            if self.session.websocket and not self.interrupted:
                try:
                    await self.session.websocket.send_json({
                        "type": "speech-end",
                        "sessionId": self.session.session_id
                    })
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[WEBRTC-HANDLER] Speak error: {e}")
        finally:
            self.is_speaking = False

    async def _maybe_schedule_from_conversation(self):
        """Analyze conversation for calendar scheduling intent (runs in background)"""
        if self.appointment_scheduled:
            return

        try:
            # Lazy import calendar services
            from ..call_handlers.optimized_stream_handler import get_calendar_services
            calendar_service, calendar_intent_service = get_calendar_services()
            if not calendar_service or not calendar_intent_service:
                return

            conversation_messages = self.conversation.get_messages() if self.conversation else []
            if len(conversation_messages) < 3:
                return

            openai_key = self.provider_keys.get("openai") or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                return

            logger.info("[WEBRTC-CALENDAR] Analyzing conversation for scheduling intent...")

            result = await calendar_intent_service.extract_from_conversation(
                conversation_messages,
                openai_key,
                self.timezone,
            )

            if not result or not result.get("should_schedule"):
                return

            appointment = result.get("appointment") or {}
            start_iso = appointment.get("start_iso")
            end_iso = appointment.get("end_iso")

            if not start_iso or not end_iso:
                return

            logger.info(f"[WEBRTC-CALENDAR] Valid appointment: {appointment.get('title')} at {start_iso}")

            appointment.setdefault("timezone", self.timezone)
            provider = appointment.get("provider") or self.calendar_provider

            start_time = datetime.fromisoformat(start_iso)
            end_time = datetime.fromisoformat(end_iso)

            # Determine calendar account for booking
            calendar_account_id_for_booking = None

            if self.calendar_account_ids and len(self.calendar_account_ids) >= 1:
                availability = await calendar_service.check_availability_across_calendars(
                    self.calendar_account_ids, start_time, end_time
                )
                if not availability.get("is_available"):
                    await self._speak("I'm sorry, but that time slot is already occupied. Could you suggest an alternative time?")
                    return

                if len(self.calendar_account_ids) > 1:
                    from app.config.database import Database
                    db = Database.get_db()
                    assistant = db['assistants'].find_one({"_id": self.assistant_id}) if self.assistant_id else None
                    calendar_account_id_for_booking = await calendar_service.get_next_available_calendar_round_robin(
                        assistant, start_time, end_time
                    )
                else:
                    calendar_account_id_for_booking = self.calendar_account_ids[0]
            elif self.calendar_account_id:
                calendar_account_id_for_booking = self.calendar_account_id

            if not calendar_account_id_for_booking:
                return

            event_id = await calendar_service.book_inbound_appointment(
                call_sid=self.session.session_id,
                user_id=self.user_id,
                assistant_id=self.assistant_id,
                appointment=appointment,
                provider=provider,
                calendar_account_id=str(calendar_account_id_for_booking),
            )

            if event_id:
                self.appointment_scheduled = True
                logger.info(f"[WEBRTC-CALENDAR] Appointment booked: {event_id}")

        except Exception as e:
            logger.error(f"[WEBRTC-CALENDAR] Scheduling error: {e}", exc_info=True)

    async def _send_audio_to_client(self, audio_bytes: bytes):
        """Send audio to client via WebRTC signaling channel"""
        if not audio_bytes:
            return

        if self.interrupted:
            return

        # Send via signaling server
        await signaling_server.send_audio_to_client(
            self.session.session_id,
            audio_bytes
        )
        self.session.audio_packets_sent += 1

    async def close(self):
        """Clean up resources"""
        self.is_running = False

        # Cancel keepalive
        if self.keepalive_task and not self.keepalive_task.done():
            self.keepalive_task.cancel()

        # Close ASR
        if self.asr:
            await self.asr.close()

        # Log stats
        if self.call_start_time:
            duration = (time.time() - self.call_start_time) / 60
            logger.info(f"[WEBRTC-HANDLER] Call duration: {duration:.1f} minutes")

        if self.metrics["ttft_ms"]:
            avg_ttft = sum(self.metrics["ttft_ms"]) / len(self.metrics["ttft_ms"])
            logger.info(f"[WEBRTC-HANDLER] Average TTFT: {avg_ttft:.0f}ms")

        # Save call log
        await self._save_call_log()

        logger.info(f"[WEBRTC-HANDLER] Closed: {self.session.session_id}")

    async def _save_call_log(self):
        """Save call log to database"""
        try:
            from app.config.database import Database
            db = Database.get_db()

            # Build transcript
            transcript_text = "\n".join([
                f"{msg['speaker'].upper()}: {msg['text']}"
                for msg in self.full_transcript
            ])

            # Performance stats
            stats = {}
            if self.metrics["llm_latency_ms"]:
                stats["llm"] = {
                    "avg_ms": sum(self.metrics["llm_latency_ms"]) / len(self.metrics["llm_latency_ms"]),
                    "count": len(self.metrics["llm_latency_ms"])
                }
            if self.metrics["tts_latency_ms"]:
                stats["tts"] = {
                    "avg_ms": sum(self.metrics["tts_latency_ms"]) / len(self.metrics["tts_latency_ms"]),
                    "count": len(self.metrics["tts_latency_ms"])
                }
            if self.metrics["ttft_ms"]:
                stats["ttft"] = {
                    "avg_ms": sum(self.metrics["ttft_ms"]) / len(self.metrics["ttft_ms"]),
                    "min_ms": min(self.metrics["ttft_ms"]),
                    "max_ms": max(self.metrics["ttft_ms"])
                }

            call_log = {
                "call_sid": f"webrtc_{self.session.session_id}",
                "session_id": self.session.session_id,
                "assistant_id": self.config.get("assistant_id"),
                "user_id": self.session.user_id,
                "call_type": "webrtc",
                "direction": "inbound",
                "status": "completed",
                "transcript": transcript_text,
                "full_transcript": self.full_transcript,
                "transcript_source": "realtime",
                "duration_seconds": (time.time() - self.call_start_time) if self.call_start_time else 0,
                "performance_stats": stats,
                "audio_packets_received": self.session.audio_packets_received,
                "audio_packets_sent": self.session.audio_packets_sent,
                "handler_type": "webrtc",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }

            db['call_logs'].insert_one(call_log)
            logger.info(f"[WEBRTC-HANDLER] Call log saved: {self.session.session_id}")

        except Exception as e:
            logger.error(f"[WEBRTC-HANDLER] Failed to save call log: {e}")


async def handle_webrtc_call(
    websocket: WebSocket,
    assistant_id: str,
    user_id: str,
    assistant_config: Dict[str, Any],
    provider_keys: Dict[str, str]
):
    """
    Entry point for WebRTC voice calls.

    Used for web/mobile clients (NOT phone calls).
    Phone calls must use WebSocket handlers via Twilio.

    Args:
        websocket: WebSocket for signaling
        assistant_id: AI assistant ID
        user_id: User ID
        assistant_config: Assistant configuration
        provider_keys: API keys for providers
    """
    handler: Optional[WebRTCVoiceHandler] = None

    async def on_session_ready(session: WebRTCSession):
        """Called when WebRTC session is established"""
        nonlocal handler

        logger.info(f"[WEBRTC] Session ready: {session.session_id}")

        # Create voice handler
        handler = WebRTCVoiceHandler(session, assistant_config, provider_keys)
        await handler.initialize()
        await handler.start()

    try:
        # Handle WebRTC signaling (this manages the connection)
        await signaling_server.handle_connection(
            websocket,
            assistant_id,
            user_id,
            on_session_ready=on_session_ready
        )

    except WebSocketDisconnect:
        logger.info("[WEBRTC] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[WEBRTC] Error: {e}", exc_info=True)
    finally:
        if handler:
            await handler.close()
