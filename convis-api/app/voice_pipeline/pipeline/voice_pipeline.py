"""
Advanced Voice Pipeline for Convis
Real-time voice processing with WebSocket streaming for minimal latency
Orchestrates: Twilio Audio → Deepgram → OpenAI LLM → ElevenLabs/Cartesia → Twilio
"""
import asyncio
import base64
import json
import uuid
from typing import Dict, Any
from datetime import datetime
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.helpers.utils import create_ws_data_packet, timestamp_ms
from app.voice_pipeline.helpers.mark_event_meta_data import MarkEventMetaData
from app.voice_pipeline.transcriber import DeepgramTranscriber, SarvamTranscriber, GoogleTranscriber, OpenAITranscriber
from app.voice_pipeline.llm import OpenAiLLM
from app.voice_pipeline.synthesizer import ElevenlabsSynthesizer, CartesiaSynthesizer, OpenAISynthesizer, SarvamSynthesizer

logger = configure_logger(__name__)


class SimpleTaskManager:
    """Simple task manager for voice pipeline - allows all sequence IDs"""
    def is_sequence_id_in_current_ids(self, sequence_id):
        # For simple pipeline, always allow synthesis
        return True


class VoicePipeline:
    """
    Simplified pipeline orchestrator based on Bolna architecture
    Manages async queues between: Transcriber → LLM → Synthesizer → Twilio
    """

    def __init__(self, assistant_config: Dict[str, Any], api_keys: Dict[str, str], twilio_ws, call_sid=None, stream_sid=None, db=None, conversation_history=None):
        self.assistant_config = assistant_config
        self.api_keys = api_keys
        self.twilio_ws = twilio_ws
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.db = db
        self.conversation_history = conversation_history if conversation_history is not None else []

        # Call timing for timestamped conversation log
        self.call_start_time = None  # Set when pipeline starts
        self.conversation_log = []  # Structured log with timestamps: [{role, text, timestamp, elapsed}]

        # Async queues for inter-component communication
        self.audio_input_queue = asyncio.Queue()  # Twilio → Transcriber
        self.transcriber_output_queue = asyncio.Queue()  # Transcriber → LLM
        self.llm_output_queue = asyncio.Queue()  # LLM → Synthesizer
        self.synthesizer_output_queue = asyncio.Queue()  # Synthesizer → Twilio

        # Component instances
        self.transcriber = None
        self.llm = None
        self.synthesizer = None

        # Mark event tracking for audio playback monitoring
        self.mark_event_meta_data = MarkEventMetaData()
        self.is_audio_being_played = False
        self.response_heard_by_user = ""

        # Pipeline control
        self.running = False
        self.tasks = []
        
        # Interruption handling - flag to stop LLM/TTS generation
        self.interrupted = False
        self.current_response_id = None  # Track current response for cancellation

        logger.info(f"[VOICE_PIPELINE] Initialized with assistant: {assistant_config.get('assistant_name', 'Unknown')}")

    def _get_elapsed_time(self) -> str:
        """Get elapsed time since call start in MM:SS format"""
        if not self.call_start_time:
            return "00:00"
        elapsed_seconds = (datetime.utcnow() - self.call_start_time).total_seconds()
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _add_to_conversation_log(self, role: str, text: str, is_interrupted: bool = False):
        """Add a message to the structured conversation log with timestamp"""
        elapsed = self._get_elapsed_time()
        log_entry = {
            "role": role,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed": elapsed,
            "is_interrupted": is_interrupted
        }
        self.conversation_log.append(log_entry)
        logger.info(f"[VOICE_PIPELINE] 📋 [{elapsed}] {role.upper()}: {text[:100]}{'...' if len(text) > 100 else ''}")

    def _get_endpointing_from_noise_level(self, noise_level: str) -> str:
        """
        Map noise suppression level to endpointing value.
        OPTIMIZED FOR LOW LATENCY - faster end-of-speech detection
        
        Noise Level Mapping (BALANCED for speed + stability):
        - off: 200ms (fast, may pick up some noise)
        - low: 250ms (fast response)
        - medium: 300ms (balanced, fast - DEFAULT)
        - high: 400ms (moderate filtering)
        - maximum: 500ms (strong filtering for noisy environments)
        """
        mapping = {
            'off': '200',
            'low': '250',
            'medium': '300',
            'high': '400',
            'maximum': '500'
        }
        return mapping.get(noise_level, '300')  # Default to balanced fast

    def _is_meaningful_speech(self, text: str) -> bool:
        """
        Determine if text is meaningful user speech vs background noise.
        Returns True for real speech that should trigger interruption.
        
        NOISE FILTERING:
        - Ignores short utterances (< 3 chars)
        - Ignores common filler/noise sounds
        - Ignores single repeated characters
        - Requires at least 2 words OR 6+ characters of real content
        """
        if not text:
            return False
            
        text_lower = text.lower().strip()
        char_count = len(text_lower)
        words = text_lower.split()
        word_count = len(words)
        
        # Too short - likely noise
        if char_count < 3:
            return False
        
        # Common noise artifacts and filler sounds to ignore
        noise_patterns = {
            # Filler sounds
            'um', 'uh', 'ah', 'oh', 'hmm', 'mm', 'hm', 'mhm', 'uhh', 'umm', 'ahh',
            'er', 'erm', 'eh', 'huh', 'hmm', 'mmm',
            # Background noise transcriptions
            'the', 'a', 'an', 'and', 'i', 'it', 'in', 'on', 'is', 'to',
            # Music/TV bleed
            'yeah', 'ya', 'yep', 'nah', 'na',
            # Single letters
            'a', 'i', 'o', 'e', 'u', 'n', 'm', 's', 't',
            # Common misrecognitions  
            'okay', 'ok', 'so', 'like', 'just',
        }
        
        # If entire text is a noise pattern, ignore
        if text_lower in noise_patterns:
            return False
        
        # Check if all words are noise patterns (e.g., "um um" or "the the")
        if all(word in noise_patterns for word in words):
            return False
        
        # Check for repeated characters (e.g., "aaa" or "mmm")
        if len(set(text_lower.replace(' ', ''))) <= 2:
            return False
        
        # MEANINGFUL SPEECH CRITERIA:
        # 1. At least 2 real words, OR
        # 2. At least 6 characters with some variety
        meaningful_words = [w for w in words if w not in noise_patterns and len(w) > 1]
        
        if len(meaningful_words) >= 2:
            return True
        
        if char_count >= 6 and len(set(text_lower)) >= 4:
            return True
        
        return False

    def _create_transcriber(self):
        """Create transcriber with WebSocket/gRPC streaming"""
        transcriber_provider = self.assistant_config.get('transcriber', {}).get('provider', 'deepgram')
        
        # Get noise suppression settings
        noise_level = self.assistant_config.get('noise_suppression_level', 'medium')
        endpointing = self._get_endpointing_from_noise_level(noise_level)
        
        logger.info(f"[VOICE_PIPELINE] Noise suppression level: {noise_level} → endpointing: {endpointing}ms")

        if transcriber_provider == 'deepgram':
            logger.info("[VOICE_PIPELINE] Creating Deepgram transcriber (WebSocket streaming)")
            # Use nova-2 as default - it's more stable and widely available
            model = self.assistant_config.get('transcriber', {}).get('model', 'nova-2')
            logger.info(f"[VOICE_PIPELINE] Deepgram model: {model}")

            # Build keywords list - combine user keywords with default email domain boosting
            user_keywords = self.assistant_config.get('asr_keywords', [])
            # Default keywords for better email/domain recognition (with boost weights)
            default_keywords = [
                "gmail:100", "yahoo:100", "outlook:100", "hotmail:100",
                "icloud:80", "protonmail:80", "aol:80",
                "@:50", "dot com:80", "dot in:80", "dot org:80", "dot net:80",
                "at the rate:50", "at sign:50"
            ]
            # Combine: user keywords take precedence
            all_keywords = list(user_keywords) if user_keywords else []
            for kw in default_keywords:
                kw_base = kw.split(":")[0].lower()
                if not any(kw_base in ukw.lower() for ukw in all_keywords):
                    all_keywords.append(kw)

            keywords_str = ",".join(all_keywords) if all_keywords else None
            if keywords_str:
                logger.info(f"[VOICE_PIPELINE] Deepgram keywords: {keywords_str}")

            return DeepgramTranscriber(
                telephony_provider='twilio',  # Twilio uses μ-law 8kHz
                input_queue=self.audio_input_queue,
                output_queue=self.transcriber_output_queue,
                model=model,
                language=self.assistant_config.get('transcriber', {}).get('language', 'en'),
                endpointing=endpointing,  # Dynamic based on noise suppression level
                transcriber_key=self.api_keys.get('deepgram'),
                noise_suppression_level=noise_level,  # Pass to transcriber for additional settings
                keywords=keywords_str  # Boost email domains and common terms
            )
        elif transcriber_provider == 'sarvam':
            logger.info("[VOICE_PIPELINE] Creating Sarvam transcriber (WebSocket streaming)")
            return SarvamTranscriber(
                telephony_provider='twilio',  # Twilio uses μ-law 8kHz
                input_queue=self.audio_input_queue,
                output_queue=self.transcriber_output_queue,
                model=self.assistant_config.get('transcriber', {}).get('model', 'saarika:v2'),
                language=self.assistant_config.get('transcriber', {}).get('language', 'en-IN'),
                endpointing=endpointing,  # Dynamic based on noise suppression level
                transcriber_key=self.api_keys.get('sarvam'),
                noise_suppression_level=noise_level
            )
        elif transcriber_provider == 'google':
            logger.info("[VOICE_PIPELINE] Creating Google transcriber (gRPC streaming)")
            return GoogleTranscriber(
                telephony_provider='twilio',  # Twilio uses μ-law 8kHz
                input_queue=self.audio_input_queue,
                output_queue=self.transcriber_output_queue,
                model=self.assistant_config.get('transcriber', {}).get('model', 'latest_long'),
                language=self.assistant_config.get('transcriber', {}).get('language', 'en-US'),
                endpointing=endpointing,  # Dynamic based on noise suppression level
                transcriber_key=self.api_keys.get('google'),
                noise_suppression_level=noise_level
            )
        elif transcriber_provider == 'openai':
            logger.info("[VOICE_PIPELINE] Creating OpenAI Whisper transcriber (buffered with VAD)")
            return OpenAITranscriber(
                telephony_provider='twilio',  # Twilio uses μ-law 8kHz
                input_queue=self.audio_input_queue,
                output_queue=self.transcriber_output_queue,
                model=self.assistant_config.get('transcriber', {}).get('model', 'whisper-1'),
                language=self.assistant_config.get('transcriber', {}).get('language', 'en'),
                endpointing=endpointing,  # Dynamic based on noise suppression level
                transcriber_key=self.api_keys.get('openai'),
                noise_suppression_level=noise_level
            )
        else:
            raise ValueError(f"Unsupported transcriber provider: {transcriber_provider}")

    def _create_llm(self):
        """Create OpenAI LLM with streaming support"""
        llm_provider = self.assistant_config.get('llm', {}).get('provider', 'openai')

        if llm_provider == 'openai':
            model = self.assistant_config.get('llm', {}).get('model', 'gpt-4o-mini')
            logger.info(f"[VOICE_PIPELINE] Creating OpenAI LLM with model: {model}")
            return OpenAiLLM(
                model=model,
                max_tokens=self.assistant_config.get('llm', {}).get('max_tokens', 100),  # Shorter responses
                temperature=self.assistant_config.get('llm', {}).get('temperature', 0.9),  # More natural variation
                buffer_size=40,  # Legacy fallback
                llm_key=self.api_keys.get('openai'),
                # ULTRA-FAST STREAMING: Don't wait for sentences - stream immediately
                # Options: "ultra_fast" (8+ chars), "fast" (clause boundaries), "natural" (sentences)
                streaming_mode="ultra_fast",  # Fastest possible - yield at word boundaries
                min_chunk_chars=8,  # Very low threshold for fastest first response
                max_buffer_chars=60  # Force yield quickly if no word boundary
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")

    def _create_synthesizer(self):
        """Create TTS synthesizer with WebSocket/HTTP streaming"""
        synthesizer_provider = self.assistant_config.get('synthesizer', {}).get('provider', 'elevenlabs')

        # Create simple task manager for synthesis control
        task_manager = SimpleTaskManager()

        if synthesizer_provider == 'elevenlabs':
            logger.info("[VOICE_PIPELINE] Creating ElevenLabs synthesizer (WebSocket streaming)")
            return ElevenlabsSynthesizer(
                voice=self.assistant_config.get('synthesizer', {}).get('voice', 'default'),
                voice_id=self.assistant_config.get('synthesizer', {}).get('voice_id'),
                model=self.assistant_config.get('synthesizer', {}).get('model', 'eleven_turbo_v2_5'),
                synthesizer_key=self.api_keys.get('elevenlabs'),
                stream=True,
                use_mulaw=True,  # Twilio requires μ-law
                task_manager_instance=task_manager,
                # HUMAN-LIKE voice settings
                temperature=0.3,  # Lower stability = MORE expressive, emotional, human-like
                similarity_boost=0.6,  # Lower = more natural variation in voice
                speed=self.assistant_config.get('tts_speed', 1.0)  # User-configurable speed
            )
        elif synthesizer_provider == 'cartesia':
            logger.info("[VOICE_PIPELINE] Creating Cartesia synthesizer (WebSocket streaming)")
            return CartesiaSynthesizer(
                voice=self.assistant_config.get('synthesizer', {}).get('voice', 'default'),
                voice_id=self.assistant_config.get('synthesizer', {}).get('voice_id'),
                model=self.assistant_config.get('synthesizer', {}).get('model', 'sonic-english'),
                synthesizer_key=self.api_keys.get('cartesia'),
                stream=True,
                use_mulaw=True,
                speed=self.assistant_config.get('tts_speed', 1.0),  # User-configurable speed
                task_manager_instance=task_manager
            )
        elif synthesizer_provider == 'openai':
            logger.info("[VOICE_PIPELINE] Creating OpenAI TTS synthesizer (HTTP streaming)")
            return OpenAISynthesizer(
                voice=self.assistant_config.get('synthesizer', {}).get('voice', 'alloy'),
                model=self.assistant_config.get('synthesizer', {}).get('model', 'tts-1'),
                synthesizer_key=self.api_keys.get('openai'),
                stream=True,
                sampling_rate=8000,
                use_mulaw=True,  # Twilio requires μ-law
                speed=self.assistant_config.get('tts_speed', 1.0),  # User-configurable speed
                task_manager_instance=task_manager
            )
        elif synthesizer_provider == 'sarvam':
            logger.info("[VOICE_PIPELINE] Creating Sarvam TTS synthesizer (WebSocket streaming)")
            return SarvamSynthesizer(
                voice_id=self.assistant_config.get('synthesizer', {}).get('voice', 'manisha'),
                model=self.assistant_config.get('synthesizer', {}).get('model', 'bulbul:v2'),
                language=self.assistant_config.get('synthesizer', {}).get('language', 'hi-IN'),
                synthesizer_key=self.api_keys.get('sarvam'),
                stream=True,
                sampling_rate=8000,
                use_mulaw=True,  # Twilio requires μ-law
                speed=self.assistant_config.get('tts_speed', 1.0),  # User-configurable speed
                task_manager_instance=task_manager
            )
        else:
            raise ValueError(f"Unsupported synthesizer provider: {synthesizer_provider}")

    async def start(self):
        """Initialize and start all pipeline components"""
        if self.running:
            logger.warning("[VOICE_PIPELINE] Pipeline already running")
            return

        try:
            logger.info("[VOICE_PIPELINE] Starting pipeline...")

            # Record call start time for timestamped conversation log
            self.call_start_time = datetime.utcnow()
            logger.info(f"[VOICE_PIPELINE] 🕐 Call started at {self.call_start_time.isoformat()}")

            # Create components
            self.transcriber = self._create_transcriber()
            self.llm = self._create_llm()
            self.synthesizer = self._create_synthesizer()

            self.running = True

            # Start all components in parallel
            self.tasks = [
                asyncio.create_task(self._run_transcriber()),
                asyncio.create_task(self._run_llm()),
                asyncio.create_task(self._run_synthesizer()),
                asyncio.create_task(self._send_audio_to_twilio())
            ]

            logger.info("[VOICE_PIPELINE] ✅ Pipeline started successfully")
            logger.info(f"[VOICE_PIPELINE] Components: Deepgram → OpenAI → {self.assistant_config.get('synthesizer', {}).get('provider', 'ElevenLabs').title()} → Twilio")

            # Send greeting message if configured
            greeting = self.assistant_config.get('greeting_message')
            if greeting:
                await self._send_greeting(greeting)

        except Exception as e:
            logger.error(f"[VOICE_PIPELINE] Failed to start pipeline: {e}", exc_info=True)
            await self.stop()
            raise

    async def _send_greeting(self, greeting_text: str):
        """
        Send greeting message through the pipeline
        Synthesizes greeting and sends to Twilio immediately after pipeline starts

        Args:
            greeting_text: The greeting message to synthesize and play
        """
        try:
            logger.info(f"[VOICE_PIPELINE] 👋 Sending greeting: '{greeting_text}'")

            # Add greeting to conversation history (legacy)
            self.conversation_history.append({
                "role": "assistant",
                "text": greeting_text
            })

            # Add to structured conversation log with timestamp
            self._add_to_conversation_log("assistant", greeting_text)

            # Create metadata for greeting
            meta_info = {
                'sequence_id': str(timestamp_ms()),
                'message_category': 'agent_welcome_message',
                'is_greeting': True
            }

            # Queue greeting text to LLM output (which goes to synthesizer)
            await self.llm_output_queue.put({
                'text': greeting_text,
                'meta_info': meta_info,
                'is_final': True
            })

            logger.info("[VOICE_PIPELINE] ✅ Greeting queued for synthesis")

        except Exception as e:
            logger.error(f"[VOICE_PIPELINE] Failed to send greeting: {e}", exc_info=True)

    async def _run_transcriber(self):
        """Run transcriber and forward output to LLM"""
        try:
            logger.info("[VOICE_PIPELINE] Transcriber task started")
            await self.transcriber.run()
        except Exception as e:
            logger.error(f"[VOICE_PIPELINE] Transcriber error: {e}", exc_info=True)

    async def _save_transcript(self):
        """Save conversation transcript to database in real-time"""
        if self.db is None or not self.call_sid:
            return

        try:
            # Build full transcript from conversation log with timestamps
            full_transcript = "\n\n".join([
                f"[{msg['elapsed']}] {'User' if msg['role'] == 'user' else 'Assistant'}: {msg['text']}"
                for msg in self.conversation_log
            ])

            # Update call log with transcript and structured conversation log
            self.db["call_logs"].update_one(
                {"call_sid": self.call_sid},
                {"$set": {
                    "transcript": full_transcript,
                    "conversation_log": self.conversation_log,  # Structured log with timestamps
                    "transcript_updated_at": datetime.utcnow()
                }}
            )
            logger.debug(f"[VOICE_PIPELINE] 💾 Transcript saved to database (length: {len(full_transcript)} chars, {len(self.conversation_log)} messages)")
        except Exception as e:
            logger.error(f"[VOICE_PIPELINE] Error saving transcript: {e}", exc_info=True)

    async def _run_llm(self):
        """Process transcripts through LLM and forward to synthesizer"""
        try:
            logger.info("[VOICE_PIPELINE] LLM task started")
            while self.running:
                # Get transcript from transcriber
                data_packet = await self.transcriber_output_queue.get()

                if data_packet.get('data') == 'transcriber_connection_closed':
                    logger.info("[VOICE_PIPELINE] Transcriber closed, stopping LLM")
                    break

                transcript_data = data_packet.get('data', {})
                
                # Handle speech_started event - prepare for potential interruption
                if transcript_data == 'speech_started':
                    if self.is_audio_being_played:
                        logger.info("[VOICE_PIPELINE] 👂 Speech detected during AI response - monitoring...")
                    continue
                
                # Handle interim transcript events for faster barge-in
                if isinstance(transcript_data, dict) and transcript_data.get('type') == 'interim_transcript_received':
                    interim_text = transcript_data.get('content', '').strip()
                    if interim_text and self.is_audio_being_played:
                        # FAST BARGE-IN: Detect real speech in interim results
                        if self._is_meaningful_speech(interim_text):
                            logger.info(f"[VOICE_PIPELINE] 🛑 FAST BARGE-IN: '{interim_text}' - stopping AI NOW!")
                            await self.handle_interruption()
                    continue
                
                if isinstance(transcript_data, dict) and transcript_data.get('type') == 'transcript':
                    transcript = transcript_data.get('content', '').strip()
                    is_final = transcript_data.get('is_final', True)

                    if transcript:
                        logger.info(f"[VOICE_PIPELINE] 📝 Transcript ({'final' if is_final else 'interim'}): {transcript}")

                        # BARGE-IN DETECTION - Also check final transcripts
                        if self.is_audio_being_played:
                            if self._is_meaningful_speech(transcript):
                                logger.info(f"[VOICE_PIPELINE] 🛑 User interruption: '{transcript}' - stopping AI")
                                await self.handle_interruption()
                                await asyncio.sleep(0.05)  # Brief pause for cleanup

                        # Only process final transcripts for LLM response
                        if not is_final:
                            logger.debug(f"[VOICE_PIPELINE] Skipping interim transcript: {transcript}")
                            continue

                        # Add user message to conversation history (legacy)
                        self.conversation_history.append({
                            "role": "user",
                            "text": transcript
                        })

                        # Add to structured conversation log with timestamp
                        self._add_to_conversation_log("user", transcript)

                        # Build conversation messages for LLM
                        system_message = self.assistant_config.get('system_message', 'You are a helpful AI assistant.')
                        
                        # HUMAN CONVERSATION STYLE
                        voice_guidance = """

You're a REAL PERSON on a phone call, NOT a robot or AI assistant. Talk like a friendly human would:

SPEAK NATURALLY:
- Say "yeah" not "yes", "gonna" not "going to", "wanna" not "want to"
- Use "hmm", "well", "so", "actually", "you know what" naturally
- React genuinely: "Oh nice!", "Ah I see", "That makes sense"
- Keep it SHORT - 1-2 sentences max, then let them talk

DON'T sound robotic:
- Never say "I'd be happy to help" or "Is there anything else"
- Never list things or give long explanations
- Never repeat back what they said word-for-word
- Don't be overly formal or polite

BE HUMAN:
- Sound interested and engaged
- Match their energy - casual if they're casual
- It's okay to be brief: "Sure thing", "Got it", "No problem"
- Ask follow-up questions naturally"""
                        enhanced_system_message = system_message + voice_guidance
                        
                        messages = [{"role": "system", "content": enhanced_system_message}]

                        # Add conversation history
                        for msg in self.conversation_history:
                            messages.append({
                                "role": msg["role"],
                                "content": msg["text"]
                            })

                        # Generate LLM response using streaming
                        # PARALLEL PROCESSING: Each sentence is immediately sent to TTS
                        # while LLM continues generating the next sentence
                        llm_response = ""
                        meta_info = data_packet.get('meta_info', {})
                        meta_info['sequence_id'] = meta_info.get('sequence_id', str(timestamp_ms()))
                        meta_info['turn_id'] = meta_info.get('turn_id', '1')

                        # Reset interrupted flag before starting new response
                        self.interrupted = False
                        self.current_response_id = meta_info.get('sequence_id')
                        sentence_count = 0
                        first_sentence_time = None

                        try:
                            async for chunk, is_final, latency, is_function_call, func_name, pre_call_msg in self.llm.generate_stream(
                                messages=messages,
                                synthesize=True,
                                request_json=False,
                                meta_info=meta_info
                            ):
                                # CHECK FOR INTERRUPTION - stop generating if user interrupted
                                if self.interrupted:
                                    logger.warning(f"[VOICE_PIPELINE] 🛑 LLM generation interrupted by user! Stopping after: '{llm_response[:50]}...'")
                                    break

                                if isinstance(chunk, dict):  # Function call
                                    continue

                                if chunk and len(chunk.strip()) > 0:
                                    llm_response += chunk
                                    sentence_count += 1

                                    # Log first sentence timing for latency tracking
                                    if sentence_count == 1:
                                        first_sentence_time = timestamp_ms()
                                        logger.info(f"[VOICE_PIPELINE] ⚡ FIRST SENTENCE → TTS (parallel pipeline started): '{chunk[:60]}...'")
                                    else:
                                        logger.debug(f"[VOICE_PIPELINE] 📝 Sentence #{sentence_count} → TTS: '{chunk[:40]}...'")

                                    # Forward chunk to synthesizer IMMEDIATELY for streaming TTS
                                    # This enables true parallel processing - TTS starts while LLM continues
                                    await self.llm_output_queue.put({
                                        'text': chunk,
                                        'meta_info': meta_info,
                                        'is_final': is_final
                                    })
                        except Exception as e:
                            logger.error(f"[VOICE_PIPELINE] LLM generation error: {e}", exc_info=True)
                            if not self.interrupted:  # Only send error if not interrupted
                                llm_response = "I apologize, I'm having trouble processing that right now."
                                await self.llm_output_queue.put({
                                    'text': llm_response,
                                    'meta_info': meta_info,
                                    'is_final': True
                                })

                        logger.info(f"[VOICE_PIPELINE] 🤖 LLM complete: {sentence_count} sentences streamed to TTS | Response: {llm_response[:100]}...")

                        # Add assistant response to conversation history (legacy)
                        self.conversation_history.append({
                            "role": "assistant",
                            "text": llm_response
                        })

                        # Add to structured conversation log with timestamp
                        self._add_to_conversation_log("assistant", llm_response)

                        # Save transcript to database in real-time
                        await self._save_transcript()

        except Exception as e:
            logger.error(f"[VOICE_PIPELINE] LLM error: {e}", exc_info=True)

    async def _run_synthesizer(self):
        """
        Synthesize LLM responses to audio with PARALLEL STREAMING

        Key optimization: TTS starts generating audio for sentence 1 while LLM is still
        generating sentence 2, 3, etc. This enables true parallel pipeline processing.
        """
        try:
            logger.info("[VOICE_PIPELINE] Synthesizer task started (parallel streaming enabled)")

            # Establish WebSocket connection to synthesizer (ElevenLabs/Cartesia)
            self.synthesizer.websocket_holder["websocket"] = await self.synthesizer.establish_connection()

            # Start monitoring task to maintain connection
            monitor_task = asyncio.create_task(self.synthesizer.monitor_connection())

            # Track current synthesis metadata
            current_meta_info = {}
            current_text_parts = []
            first_chunk_received = False

            # Start receiver task to get audio from synthesizer and forward to Twilio
            # This runs IN PARALLEL with the sender - audio streams out as it's generated
            async def synthesizer_receiver():
                nonlocal first_chunk_received
                try:
                    async for audio_chunk, text_spoken in self.synthesizer.receiver():
                        if audio_chunk and len(audio_chunk) > 0 and audio_chunk != b'\x00':
                            if not first_chunk_received:
                                first_chunk_received = True
                                logger.info(f"[VOICE_PIPELINE] ⚡ FIRST AUDIO CHUNK from TTS → Twilio (streaming started)")

                            # Attach metadata to audio chunk
                            audio_message = {
                                'data': audio_chunk,
                                'meta_info': {
                                    'text_synthesized': text_spoken or '',
                                    'sequence_id': current_meta_info.get('sequence_id', ''),
                                    'is_final_chunk': False  # Will be updated on end_of_llm_stream
                                }
                            }
                            # Forward audio with metadata to Twilio output queue IMMEDIATELY
                            await self.synthesizer_output_queue.put(audio_message)
                            logger.debug(f"[VOICE_PIPELINE] 🎵 Audio chunk → Twilio ({len(audio_chunk)} bytes)")
                except Exception as e:
                    logger.error(f"[VOICE_PIPELINE] Synthesizer receiver error: {e}", exc_info=True)

            receiver_task = asyncio.create_task(synthesizer_receiver())

            sentence_count = 0

            # Process LLM text chunks - each sentence triggers TTS immediately
            while self.running:
                # Get text from LLM (this blocks until a sentence is ready)
                llm_output = await self.llm_output_queue.get()

                # CHECK FOR INTERRUPTION - skip synthesizing if interrupted
                if self.interrupted:
                    logger.debug("[VOICE_PIPELINE] 🛑 Skipping synthesis - interrupted")
                    first_chunk_received = False  # Reset for next response
                    continue

                text = llm_output.get('text', '')
                meta_info = llm_output.get('meta_info', {})
                is_final = llm_output.get('is_final', False)

                # Update shared metadata for the receiver task
                current_meta_info.update(meta_info)
                if is_final:
                    current_meta_info['is_final_chunk'] = True

                if text and len(text.strip()) > 0:
                    # Double-check interruption before synthesis
                    if self.interrupted:
                        logger.debug(f"[VOICE_PIPELINE] 🛑 Skipping synthesis (interrupted): {text[:30]}...")
                        continue

                    sentence_count += 1
                    current_text_parts.append(text)

                    # PARALLEL STREAMING: Send to TTS immediately - don't wait for full response
                    # TTS will start generating audio while LLM continues with next sentence
                    if sentence_count == 1:
                        logger.info(f"[VOICE_PIPELINE] 🔊 TTS STARTED: First sentence being synthesized while LLM continues...")
                    logger.info(f"[VOICE_PIPELINE] 🔊 Synthesizing sentence #{sentence_count}: '{text[:50]}...'")

                    try:
                        # Send text to synthesizer with sequence_id
                        sequence_id = meta_info.get('sequence_id', str(timestamp_ms()))
                        await self.synthesizer.sender(
                            text=text,
                            sequence_id=sequence_id,
                            end_of_llm_stream=is_final
                        )
                    except Exception as e:
                        logger.error(f"[VOICE_PIPELINE] Synthesizer sender error: {e}", exc_info=True)

                # Reset metadata after final chunk
                if is_final:
                    logger.info(f"[VOICE_PIPELINE] ✅ All {sentence_count} sentences sent to TTS")
                    current_meta_info = {}
                    current_text_parts = []
                    sentence_count = 0
                    first_chunk_received = False

            # Cleanup
            monitor_task.cancel()
            receiver_task.cancel()

        except Exception as e:
            logger.error(f"[VOICE_PIPELINE] Synthesizer error: {e}", exc_info=True)

    async def _send_mark_message(self, mark_id: str):
        """Send mark event to Twilio for audio playback tracking"""
        if not self.stream_sid:
            logger.warning("[VOICE_PIPELINE] Missing streamSid, cannot send mark event")
            return

        mark_message = {
            'event': 'mark',
            'streamSid': self.stream_sid,
            'mark': {
                'name': mark_id
            }
        }
        await self.twilio_ws.send_text(json.dumps(mark_message))
        logger.debug(f"[VOICE_PIPELINE] Sent mark event: {mark_id}")

    async def _send_audio_to_twilio(self):
        """
        Send synthesized audio back to Twilio WebSocket with mark events
        Pattern: Pre-Mark → Media → Post-Mark (like Bolna)
        """
        try:
            logger.info("[VOICE_PIPELINE] Twilio audio sender task started")
            chunk_counter = 0

            while self.running:
                # Get audio from synthesizer queue
                # Audio comes with metadata attached by synthesizer
                message = await self.synthesizer_output_queue.get()
                
                # CHECK FOR INTERRUPTION - discard audio if user interrupted
                if self.interrupted:
                    logger.debug("[VOICE_PIPELINE] 🛑 Discarding audio chunk - user interrupted")
                    continue

                # Handle different message formats
                if isinstance(message, bytes):
                    # Simple byte format (backward compatibility)
                    audio_chunk = message
                    meta_info = {'sequence_id': str(timestamp_ms()), 'chunk_id': chunk_counter}
                    text_synthesized = ""
                    is_final_chunk = False
                elif isinstance(message, dict):
                    # Rich format with metadata
                    audio_chunk = message.get('data', message.get('audio', b''))
                    meta_info = message.get('meta_info', {})
                    text_synthesized = meta_info.get('text_synthesized', '')
                    is_final_chunk = meta_info.get('is_final_chunk', False)
                else:
                    logger.warning(f"[VOICE_PIPELINE] Unknown message format: {type(message)}")
                    continue

                if not self.stream_sid:
                    logger.warning("[VOICE_PIPELINE] Missing streamSid, cannot send audio to Twilio")
                    continue

                if not audio_chunk or len(audio_chunk) == 0:
                    logger.debug("[VOICE_PIPELINE] Skipping empty audio chunk")
                    continue
                    
                # Final interruption check before sending
                if self.interrupted:
                    logger.debug("[VOICE_PIPELINE] 🛑 Not sending audio - interrupted")
                    continue

                # Calculate audio duration (mulaw @ 8kHz)
                duration = len(audio_chunk) / 8000.0

                # Send Pre-Mark
                pre_mark_id = str(uuid.uuid4())
                pre_mark_metadata = {
                    'type': 'pre_mark_message',
                    'counter': chunk_counter
                }
                self.mark_event_meta_data.update_data(pre_mark_id, pre_mark_metadata)
                await self._send_mark_message(pre_mark_id)

                # Set audio playing flag when we send audio chunks
                # This ensures we detect interruptions even if mark events are delayed
                if not self.is_audio_being_played:
                    self.is_audio_being_played = True
                    logger.info("[VOICE_PIPELINE] 🔊 Audio playback started")

                # Send Media (audio payload)
                media_message = {
                    'event': 'media',
                    'streamSid': self.stream_sid,
                    'media': {
                        'payload': base64.b64encode(audio_chunk).decode('utf-8')
                    }
                }
                await self.twilio_ws.send_text(json.dumps(media_message))

                # Send Post-Mark with metadata
                post_mark_id = str(uuid.uuid4())
                post_mark_metadata = {
                    'type': 'agent_response',
                    'text_synthesized': text_synthesized,
                    'is_final_chunk': is_final_chunk,
                    'sequence_id': meta_info.get('sequence_id', ''),
                    'duration': duration,
                    'counter': chunk_counter
                }
                self.mark_event_meta_data.update_data(post_mark_id, post_mark_metadata)
                await self._send_mark_message(post_mark_id)

                logger.info(f"[VOICE_PIPELINE] ✅ Sent audio chunk #{chunk_counter} ({len(audio_chunk)} bytes, {duration:.2f}s)")
                chunk_counter += 1

        except Exception as e:
            logger.error(f"[VOICE_PIPELINE] Twilio sender error: {e}", exc_info=True)

    async def handle_interruption(self):
        """
        Handle user interruption (barge-in)
        Stops TTS immediately and clears all pending audio
        SIMPLIFIED to avoid breaking synthesizer connection
        """
        logger.info("[VOICE_PIPELINE] ⚠️ INTERRUPTION - stopping AI speech")

        # Set interrupted flag FIRST - stops all generation immediately
        self.interrupted = True
        self.is_audio_being_played = False
        
        if not self.stream_sid:
            logger.warning("[VOICE_PIPELINE] Missing streamSid, cannot send clear event")
            return

        # 1. SEND CLEAR TO TWILIO to stop audio playback
        try:
            clear_message = json.dumps({
                'event': 'clear',
                'streamSid': self.stream_sid
            })
            await self.twilio_ws.send_text(clear_message)
            logger.info("[VOICE_PIPELINE] 🧹 Clear event sent to Twilio")
        except Exception as e:
            logger.warning(f"[VOICE_PIPELINE] Error sending clear: {e}")

        # 2. Flush synthesizer buffer (but keep connection alive)
        try:
            if self.synthesizer and hasattr(self.synthesizer, 'handle_interruption'):
                await self.synthesizer.handle_interruption()
                logger.info("[VOICE_PIPELINE] 🔇 Synthesizer flushed")
        except Exception as e:
            logger.warning(f"[VOICE_PIPELINE] Error flushing synthesizer: {e}")

        # 3. Clear queues
        cleared = 0
        while not self.synthesizer_output_queue.empty():
            try:
                self.synthesizer_output_queue.get_nowait()
                cleared += 1
            except:
                break
        while not self.llm_output_queue.empty():
            try:
                self.llm_output_queue.get_nowait()
                cleared += 1
            except:
                break
        if cleared > 0:
            logger.debug(f"[VOICE_PIPELINE] Cleared {cleared} queued items")

        # 4. Mark conversation as interrupted
        if self.conversation_log and self.conversation_log[-1]['role'] == 'assistant':
            self.conversation_log[-1]['is_interrupted'] = True

        # 5. Clear tracking state
        self.mark_event_meta_data.clear_data()
        self.response_heard_by_user = ""
        
        logger.info("[VOICE_PIPELINE] ✅ Ready for user response")

    def process_mark_event(self, mark_id: str):
        """
        Process mark event received from Twilio
        Called when Twilio acknowledges audio playback

        Args:
            mark_id: UUID of the mark event
        """
        mark_data = self.mark_event_meta_data.fetch_data(mark_id)
        if not mark_data:
            logger.debug(f"[VOICE_PIPELINE] Mark {mark_id} not found (may have been cleared)")
            return

        mark_type = mark_data.get('type')

        if mark_type == 'pre_mark_message':
            # Audio chunk started playing
            self.is_audio_being_played = True
            logger.debug(f"[VOICE_PIPELINE] Audio playback started (chunk #{mark_data.get('counter')})")

        elif mark_type == 'agent_response':
            # Audio chunk finished playing
            text_synthesized = mark_data.get('text_synthesized', '')
            if text_synthesized:
                self.response_heard_by_user += text_synthesized

            if mark_data.get('is_final_chunk'):
                self.is_audio_being_played = False
                logger.info(f"[VOICE_PIPELINE] ✅ Final audio chunk played, user heard: '{self.response_heard_by_user}'")
                self.response_heard_by_user = ""  # Reset for next response

            logger.debug(f"[VOICE_PIPELINE] Audio chunk #{mark_data.get('counter')} played ({mark_data.get('duration', 0):.2f}s)")

    async def feed_audio(self, audio_chunk: bytes):
        """
        Feed audio from Twilio into the pipeline
        Called from WebSocket handler when receiving 'media' events
        """
        if not self.running:
            logger.warning("[VOICE_PIPELINE] Pipeline not running, ignoring audio")
            return

        # Create data packet with metadata
        data_packet = create_ws_data_packet(audio_chunk, meta_info={
            'timestamp': timestamp_ms(),
            'source': 'twilio'
        })

        # Feed to transcriber
        await self.audio_input_queue.put(data_packet)

    async def stop(self):
        """Stop all pipeline components gracefully"""
        if not self.running:
            return

        logger.info("[VOICE_PIPELINE] Stopping pipeline...")
        self.running = False

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to finish
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        # Stop components
        if self.transcriber:
            await self.transcriber.toggle_connection()

        logger.info("[VOICE_PIPELINE] ❌ Pipeline stopped")
