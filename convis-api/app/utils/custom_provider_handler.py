"""
Custom Provider WebSocket Handler
Handles Audio → ASR → LLM → TTS → Audio pipeline
With Silero VAD for intelligent speech detection.
"""
import json
import asyncio
import logging
import base64
from typing import Dict, Any, Optional
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

# Try to import Silero VAD (optional dependency)
try:
    from app.utils.silero_vad import SileroVADProcessor
    SILERO_VAD_AVAILABLE = True
    logger.info("[CUSTOM_HANDLER] Silero VAD available")
except ImportError:
    SILERO_VAD_AVAILABLE = False
    logger.warning("[CUSTOM_HANDLER] Silero VAD not available, using time-based buffering")

class CustomProviderHandler:
    """
    Manages custom provider pipeline for voice calls
    """

    def __init__(
        self,
        twilio_ws,
        assistant_config: Dict[str, Any],
        api_keys: Dict[str, str]
    ):
        self.twilio_ws = twilio_ws
        self.assistant_config = assistant_config
        self.api_keys = api_keys

        # Provider configurations
        self.asr_provider = assistant_config.get('asr_provider', 'deepgram')
        self.asr_model = assistant_config.get('asr_model', 'nova-2')
        self.asr_language = assistant_config.get('asr_language', 'en')

        self.llm_provider = assistant_config.get('llm_provider', 'openai')
        self.llm_model = assistant_config.get('llm_model', 'gpt-4-turbo')
        self.llm_max_tokens = assistant_config.get('llm_max_tokens', 150)
        self.temperature = assistant_config.get('temperature', 0.7)

        self.tts_provider = assistant_config.get('tts_provider', 'elevenlabs')
        self.tts_voice = assistant_config.get('tts_voice', 'alloy')
        self.tts_model = assistant_config.get('tts_model', 'eleven_flash_v2_5')

        # Conversation state
        self.conversation_history = []
        self.system_message = assistant_config.get('system_message', '')
        self.stream_sid = None
        self.call_sid = None

        # Audio buffer for accumulating chunks before sending to ASR
        self.audio_buffer = b''
        self.buffer_duration_ms = 500  # Fallback: 500ms buffering if VAD not available
        self.last_buffer_send = datetime.now()
        self.min_audio_threshold = 4000  # Minimum 4KB audio before sending (prevents empty transcriptions)

        # VAD configuration
        self.use_vad = assistant_config.get('use_vad', True) and SILERO_VAD_AVAILABLE
        self.vad_processor = None
        self.vad_threshold = assistant_config.get('vad_threshold', 0.5)
        self.vad_min_speech_ms = assistant_config.get('vad_min_speech_ms', 250)
        self.vad_min_silence_ms = assistant_config.get('vad_min_silence_ms', 300)

        if self.use_vad:
            try:
                self.vad_processor = SileroVADProcessor(
                    threshold=self.vad_threshold,
                    min_speech_duration_ms=self.vad_min_speech_ms,
                    min_silence_duration_ms=self.vad_min_silence_ms
                )
                logger.info(f"[CUSTOM_HANDLER] VAD enabled: threshold={self.vad_threshold}, "
                           f"min_speech={self.vad_min_speech_ms}ms, min_silence={self.vad_min_silence_ms}ms")
            except Exception as e:
                logger.error(f"[CUSTOM_HANDLER] Failed to initialize VAD: {e}")
                self.use_vad = False
                self.vad_processor = None

        logger.info(f"[CUSTOM_HANDLER] Initialized: ASR={self.asr_provider}, LLM={self.llm_provider}, "
                   f"TTS={self.tts_provider}, VAD={'enabled' if self.use_vad else 'disabled'}")

    async def handle_twilio_message(self, message: Dict[str, Any]):
        """
        Handle incoming message from Twilio WebSocket
        """
        event = message.get('event')

        if event == 'start':
            await self.handle_start(message)
        elif event == 'media':
            await self.handle_media(message)
        elif event == 'stop':
            await self.handle_stop(message)

    async def handle_start(self, message: Dict[str, Any]):
        """Handle call start event"""
        start_info = message.get('start', {})
        self.stream_sid = start_info.get('streamSid')
        self.call_sid = start_info.get('callSid')

        logger.info(f"[CUSTOM_HANDLER] Call started: {self.call_sid}")

        # Reset VAD state for new call
        if self.vad_processor:
            self.vad_processor.reset()

        # Send greeting
        greeting = self.assistant_config.get('call_greeting', 'Hello! How can I help you today?')
        await self.synthesize_and_send(greeting)

    async def handle_media(self, message: Dict[str, Any]):
        """Handle incoming audio from caller"""
        media = message.get('media', {})
        payload = media.get('payload')

        if payload:
            # Decode audio (Twilio sends base64 encoded mulaw)
            audio_data = base64.b64decode(payload)
            self.audio_buffer += audio_data

            if self.use_vad and self.vad_processor:
                # Use Silero VAD for intelligent speech detection
                await self._handle_media_with_vad(audio_data)
            else:
                # Fallback to time-based buffering
                await self._handle_media_time_based()

    async def _handle_media_with_vad(self, audio_chunk: bytes):
        """
        Handle media using Silero VAD for speech detection.
        Only triggers processing when speech segment ends.
        """
        # Process audio chunk through VAD
        is_speech, speech_prob = self.vad_processor.process_chunk(audio_chunk)

        # Check if a valid speech segment has ended (using the proper method)
        if self.vad_processor.is_speech_ended() and len(self.audio_buffer) >= self.min_audio_threshold:
            speech_duration = self.vad_processor.get_speech_duration_ms()
            logger.info(f"[VAD] Speech ended after {speech_duration}ms, processing buffer "
                       f"({len(self.audio_buffer)} bytes)")
            await self.process_audio_buffer()
            self.audio_buffer = b''
            self.last_buffer_send = datetime.now()
            self.vad_processor.reset()

        # Emergency flush to prevent memory buildup
        if len(self.audio_buffer) >= 32000:  # 4 seconds at 8kHz
            logger.warning("[VAD] Emergency buffer flush (32KB limit)")
            await self.process_audio_buffer()
            self.audio_buffer = b''
            self.last_buffer_send = datetime.now()
            self.vad_processor.reset()

    async def _handle_media_time_based(self):
        """
        Fallback: Handle media using time-based buffering.
        Used when VAD is not available.
        """
        current_time = datetime.now()
        elapsed_ms = (current_time - self.last_buffer_send).total_seconds() * 1000
        buffer_size = len(self.audio_buffer)

        # Process if: (time threshold reached AND has minimum audio) OR buffer is very large
        should_process = (
            (elapsed_ms >= self.buffer_duration_ms and buffer_size >= self.min_audio_threshold) or
            buffer_size >= 16000  # Emergency flush at 16KB to prevent memory buildup
        )

        if should_process:
            await self.process_audio_buffer()
            self.audio_buffer = b''
            self.last_buffer_send = current_time

    async def handle_stop(self, message: Dict[str, Any]):
        """Handle call end event"""
        logger.info(f"[CUSTOM_HANDLER] Call ended: {self.call_sid}")

    async def process_audio_buffer(self):
        """
        Process accumulated audio buffer:
        1. Transcribe with ASR
        2. Generate response with LLM
        3. Synthesize with TTS
        4. Send back to caller
        """
        try:
            # Step 1: Transcribe
            transcript = await self.transcribe_audio(self.audio_buffer)
            if not transcript or transcript.strip() == '':
                return

            logger.info(f"[TRANSCRIPTION] User: {transcript}")

            # Step 2: Generate LLM response
            response_text = await self.generate_llm_response(transcript)
            if not response_text:
                return

            logger.info(f"[LLM_RESPONSE] Assistant: {response_text}")

            # Step 3: Synthesize and send
            await self.synthesize_and_send(response_text)

        except Exception as e:
            logger.error(f"[PIPELINE_ERROR] {e}", exc_info=True)

    async def transcribe_audio(self, audio_data: bytes) -> Optional[str]:
        """Transcribe audio using configured ASR provider"""
        try:
            if self.asr_provider == 'deepgram':
                return await self.transcribe_deepgram(audio_data)
            elif self.asr_provider == 'openai':
                return await self.transcribe_openai(audio_data)
            elif self.asr_provider == 'azure':
                return await self.transcribe_azure(audio_data)
            elif self.asr_provider == 'sarvam':
                return await self.transcribe_sarvam(audio_data)
            elif self.asr_provider == 'assembly':
                return await self.transcribe_assembly(audio_data)
            elif self.asr_provider == 'google':
                return await self.transcribe_google(audio_data)
            else:
                logger.error(f"[ASR] Unsupported provider: {self.asr_provider}")
                return None
        except Exception as e:
            logger.error(f"[ASR_ERROR] {e}")
            return None

    async def transcribe_deepgram(self, audio_data: bytes) -> Optional[str]:
        """Transcribe using Deepgram"""
        api_key = self.api_keys.get('deepgram')
        if not api_key:
            logger.error("[DEEPGRAM] No API key configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.deepgram.com/v1/listen?model={self.asr_model}&language={self.asr_language}",
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": "audio/mulaw"
                    },
                    content=audio_data,
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    transcript = result.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', '')
                    return transcript.strip()
                else:
                    logger.error(f"[DEEPGRAM] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[DEEPGRAM] Exception: {e}")
            return None

    async def transcribe_openai(self, audio_data: bytes) -> Optional[str]:
        """Transcribe using OpenAI Whisper"""
        api_key = self.api_keys.get('openai')
        if not api_key:
            logger.error("[OPENAI_WHISPER] No API key configured")
            return None

        try:
            # Convert audio to file-like object for multipart upload
            import io
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.mulaw"

            async with httpx.AsyncClient() as client:
                files = {
                    "file": ("audio.mulaw", audio_file, "audio/mulaw")
                }
                data = {
                    "model": self.asr_model or "whisper-1",
                    "language": self.asr_language
                }

                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={
                        "Authorization": f"Bearer {api_key}"
                    },
                    files=files,
                    data=data,
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get('text', '').strip()
                else:
                    logger.error(f"[OPENAI_WHISPER] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[OPENAI_WHISPER] Exception: {e}")
            return None

    async def transcribe_azure(self, audio_data: bytes) -> Optional[str]:
        """Transcribe using Azure Speech Services"""
        api_key = self.api_keys.get('azure')
        region = self.assistant_config.get('azure_region', 'eastus')

        if not api_key:
            logger.error("[AZURE_ASR] No API key configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1",
                    headers={
                        "Ocp-Apim-Subscription-Key": api_key,
                        "Content-Type": "audio/mulaw; samplerate=8000"
                    },
                    params={
                        "language": self.asr_language,
                        "format": "detailed"
                    },
                    content=audio_data,
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get('DisplayText', '').strip()
                else:
                    logger.error(f"[AZURE_ASR] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[AZURE_ASR] Exception: {e}")
            return None

    async def transcribe_sarvam(self, audio_data: bytes) -> Optional[str]:
        """Transcribe using Sarvam AI"""
        api_key = self.api_keys.get('sarvam')
        if not api_key:
            logger.error("[SARVAM_ASR] No API key configured")
            return None

        try:
            import io
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.mulaw"

            async with httpx.AsyncClient() as client:
                files = {
                    "file": ("audio.mulaw", audio_file, "audio/mulaw")
                }
                data = {
                    "language_code": self.asr_language,
                    "model": self.asr_model or "saarika:v1"
                }

                response = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers={
                        "api-subscription-key": api_key,
                        "api-key": api_key,
                        "x-api-key": api_key,
                        "Authorization": f"Bearer {api_key}"
                    },
                    files=files,
                    data=data,
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get('transcript', '').strip()
                else:
                    logger.error(f"[SARVAM_ASR] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[SARVAM_ASR] Exception: {e}")
            return None

    async def transcribe_assembly(self, audio_data: bytes) -> Optional[str]:
        """Transcribe using AssemblyAI"""
        api_key = self.api_keys.get('assembly')
        if not api_key:
            logger.error("[ASSEMBLY_ASR] No API key configured")
            return None

        try:
            # AssemblyAI requires upload first, then transcription
            async with httpx.AsyncClient() as client:
                # Step 1: Upload audio
                upload_response = await client.post(
                    "https://api.assemblyai.com/v2/upload",
                    headers={
                        "authorization": api_key
                    },
                    content=audio_data,
                    timeout=10.0
                )

                if upload_response.status_code != 200:
                    logger.error(f"[ASSEMBLY_ASR] Upload error: {upload_response.status_code}")
                    return None

                upload_url = upload_response.json()['upload_url']

                # Step 2: Create transcription job
                transcript_response = await client.post(
                    "https://api.assemblyai.com/v2/transcript",
                    headers={
                        "authorization": api_key,
                        "content-type": "application/json"
                    },
                    json={
                        "audio_url": upload_url,
                        "language_code": self.asr_language
                    },
                    timeout=10.0
                )

                if transcript_response.status_code != 200:
                    logger.error(f"[ASSEMBLY_ASR] Transcript error: {transcript_response.status_code}")
                    return None

                transcript_id = transcript_response.json()['id']

                # Step 3: Poll for completion (wait up to 5 seconds)
                for _ in range(10):
                    await asyncio.sleep(0.5)

                    status_response = await client.get(
                        f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                        headers={"authorization": api_key},
                        timeout=5.0
                    )

                    if status_response.status_code == 200:
                        result = status_response.json()
                        if result['status'] == 'completed':
                            return result.get('text', '').strip()
                        elif result['status'] == 'error':
                            logger.error(f"[ASSEMBLY_ASR] Transcription failed")
                            return None

                logger.warning("[ASSEMBLY_ASR] Transcription timeout")
                return None

        except Exception as e:
            logger.error(f"[ASSEMBLY_ASR] Exception: {e}")
            return None

    async def transcribe_google(self, audio_data: bytes) -> Optional[str]:
        """Transcribe using Google Speech-to-Text"""
        api_key = self.api_keys.get('google')
        if not api_key:
            logger.error("[GOOGLE_ASR] No API key configured")
            return None

        try:
            import base64
            audio_content = base64.b64encode(audio_data).decode('utf-8')

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}",
                    headers={
                        "Content-Type": "application/json"
                    },
                    json={
                        "config": {
                            "encoding": "MULAW",
                            "sampleRateHertz": 8000,
                            "languageCode": self.asr_language,
                            "model": self.asr_model or "default"
                        },
                        "audio": {
                            "content": audio_content
                        }
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    results = result.get('results', [])
                    if results and len(results) > 0:
                        alternatives = results[0].get('alternatives', [])
                        if alternatives and len(alternatives) > 0:
                            return alternatives[0].get('transcript', '').strip()
                    return None
                else:
                    logger.error(f"[GOOGLE_ASR] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[GOOGLE_ASR] Exception: {e}")
            return None

    async def generate_llm_response(self, user_text: str) -> Optional[str]:
        """Generate response using LLM"""
        # Add user message to conversation
        self.conversation_history.append({
            "role": "user",
            "content": user_text
        })

        try:
            response = None
            if self.llm_provider == 'openai':
                response = await self.generate_openai_response()
            elif self.llm_provider == 'azure':
                response = await self.generate_azure_response()
            elif self.llm_provider == 'anthropic':
                response = await self.generate_anthropic_response()
            elif self.llm_provider == 'deepseek':
                response = await self.generate_deepseek_response()
            elif self.llm_provider == 'openrouter':
                response = await self.generate_openrouter_response()
            elif self.llm_provider == 'groq':
                response = await self.generate_groq_response()
            else:
                logger.error(f"Unsupported LLM provider: {self.llm_provider}")
                return None

            if response:
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
            return response
        except Exception as e:
            logger.error(f"[LLM_ERROR] {e}")
            return None

    async def generate_openai_response(self) -> Optional[str]:
        """Generate response using OpenAI"""
        api_key = self.api_keys.get('openai')
        if not api_key:
            logger.error("[OPENAI_LLM] No API key configured")
            return None

        try:
            messages = [
                {"role": "system", "content": self.system_message}
            ] + self.conversation_history

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.llm_model,
                        "messages": messages,
                        "max_tokens": self.llm_max_tokens,
                        "temperature": self.temperature
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"[OPENAI_LLM] Error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"[OPENAI_LLM] Exception: {e}")
            return None

    async def generate_azure_response(self) -> Optional[str]:
        """Generate response using Azure OpenAI"""
        api_key = self.api_keys.get('azure')
        if not api_key:
            logger.error("[AZURE_LLM] No API key configured")
            return None
        # Placeholder - needs Azure endpoint configuration
        logger.info("[AZURE_LLM] Not yet fully implemented")
        return None

    async def generate_anthropic_response(self) -> Optional[str]:
        """Generate response using Anthropic Claude"""
        api_key = self.api_keys.get('anthropic')
        if not api_key:
            logger.error("[ANTHROPIC_LLM] No API key configured")
            return None

        try:
            messages = self.conversation_history

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.llm_model,
                        "max_tokens": self.llm_max_tokens,
                        "temperature": self.temperature,
                        "system": self.system_message,
                        "messages": messages
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result['content'][0]['text']
                else:
                    logger.error(f"[ANTHROPIC_LLM] Error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"[ANTHROPIC_LLM] Exception: {e}")
            return None

    async def generate_deepseek_response(self) -> Optional[str]:
        """Generate response using Deepseek"""
        api_key = self.api_keys.get('deepseek')
        if not api_key:
            logger.error("[DEEPSEEK_LLM] No API key configured")
            return None

        try:
            messages = [
                {"role": "system", "content": self.system_message}
            ] + self.conversation_history

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.llm_model,
                        "messages": messages,
                        "max_tokens": self.llm_max_tokens,
                        "temperature": self.temperature
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"[DEEPSEEK_LLM] Error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"[DEEPSEEK_LLM] Exception: {e}")
            return None

    async def generate_openrouter_response(self) -> Optional[str]:
        """Generate response using OpenRouter"""
        api_key = self.api_keys.get('openrouter')
        if not api_key:
            logger.error("[OPENROUTER_LLM] No API key configured")
            return None

        try:
            messages = [
                {"role": "system", "content": self.system_message}
            ] + self.conversation_history

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.llm_model,
                        "messages": messages,
                        "max_tokens": self.llm_max_tokens,
                        "temperature": self.temperature
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"[OPENROUTER_LLM] Error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"[OPENROUTER_LLM] Exception: {e}")
            return None

    async def generate_groq_response(self) -> Optional[str]:
        """Generate response using Groq"""
        api_key = self.api_keys.get('groq')
        if not api_key:
            logger.error("[GROQ_LLM] No API key configured")
            return None

        try:
            messages = [
                {"role": "system", "content": self.system_message}
            ] + self.conversation_history

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.llm_model,
                        "messages": messages,
                        "max_tokens": self.llm_max_tokens,
                        "temperature": self.temperature
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"[GROQ_LLM] Error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"[GROQ_LLM] Exception: {e}")
            return None

    async def synthesize_and_send(self, text: str):
        """Synthesize speech and send to caller"""
        try:
            if self.tts_provider == 'openai':
                audio_data = await self.synthesize_openai(text)
            elif self.tts_provider == 'cartesia':
                audio_data = await self.synthesize_cartesia(text)
            elif self.tts_provider == 'sarvam':
                audio_data = await self.synthesize_sarvam(text)
            elif self.tts_provider == 'azuretts':
                audio_data = await self.synthesize_azuretts(text)
            elif self.tts_provider == 'elevenlabs':
                audio_data = await self.synthesize_elevenlabs(text)
            elif self.tts_provider == 'piper':
                audio_data = await self.synthesize_piper(text)
            else:
                logger.error(f"[TTS] Unsupported provider: {self.tts_provider}")
                return

            if audio_data:
                await self.send_audio_to_twilio(audio_data)
        except Exception as e:
            logger.error(f"[TTS_ERROR] {e}")

    async def synthesize_piper(self, text: str) -> Optional[bytes]:
        """Synthesize using local Piper TTS (offline, no API key required)."""
        try:
            from app.services.call_handlers.offline_tts_handler import OfflinePiperTTS

            # Cache instance to avoid model reload on every utterance
            if not hasattr(self, "_piper_tts") or self._piper_tts is None:
                voice = self.tts_voice or "en_US-lessac-medium"
                self._piper_tts = OfflinePiperTTS(voice=voice, for_browser=False)

            audio = await self._piper_tts.synthesize(text)
            if not audio:
                logger.error("[PIPER_TTS] No audio generated")
                return None
            return audio
        except Exception as e:
            logger.error(f"[PIPER_TTS] Exception: {e}", exc_info=True)
            return None

    async def synthesize_openai(self, text: str) -> Optional[bytes]:
        """Synthesize using OpenAI TTS"""
        api_key = self.api_keys.get('openai')
        if not api_key:
            logger.error("[OPENAI_TTS] No API key configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.tts_model,
                        "voice": self.tts_voice,
                        "input": text,
                        "response_format": "pcm"  # Get PCM, will convert to mulaw
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    pcm_audio = response.content
                    # Convert PCM to μ-law for Twilio (like Bolna does)
                    import audioop
                    mulaw_audio = audioop.lin2ulaw(pcm_audio, 2)
                    return mulaw_audio
                else:
                    logger.error(f"[OPENAI_TTS] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[OPENAI_TTS] Exception: {e}")
            return None

    async def synthesize_cartesia(self, text: str) -> Optional[bytes]:
        """Synthesize using Cartesia"""
        api_key = self.api_keys.get('cartesia')
        if not api_key:
            logger.error("[CARTESIA_TTS] No API key configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.cartesia.ai/tts/bytes",
                    headers={
                        "X-API-Key": api_key,
                        "Cartesia-Version": "2024-06-10",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model_id": self.tts_model or "sonic-english",
                        "transcript": text,
                        "voice": {
                            "mode": "id",
                            "id": self.tts_voice or "a0e99841-438c-4a64-b679-ae501e7d6091"
                        },
                        "output_format": {
                            "container": "raw",
                            "encoding": "pcm_mulaw",
                            "sample_rate": 8000
                        }
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    return response.content
                else:
                    logger.error(f"[CARTESIA_TTS] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[CARTESIA_TTS] Exception: {e}")
            return None

    async def synthesize_sarvam(self, text: str) -> Optional[bytes]:
        """Synthesize using Sarvam AI"""
        api_key = self.api_keys.get('sarvam')
        if not api_key:
            logger.error("[SARVAM_TTS] No API key configured")
            return None

        try:
            # Get TTS speed from config, default to 1.0
            tts_speed = self.assistant_config.get('tts_speed', 1.0)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers={
                        "api-subscription-key": api_key,
                        "api-key": api_key,
                        "x-api-key": api_key,
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "inputs": [text],
                        "target_language_code": self.asr_language or "en-IN",
                        "speaker": self.tts_voice or "manisha",
                        "pitch": 0,
                        "pace": tts_speed,
                        "loudness": 1.5,
                        "speech_sample_rate": 8000,
                        "enable_preprocessing": True,
                        "model": self.tts_model or "bulbul:v2"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    # Sarvam returns base64 encoded PCM audio at 8kHz
                    if 'audios' in result and len(result['audios']) > 0:
                        audio_base64 = result['audios'][0]
                        import base64
                        pcm_audio = base64.b64decode(audio_base64)
                        # Convert PCM to μ-law for Twilio
                        import audioop
                        mulaw_audio = audioop.lin2ulaw(pcm_audio, 2)
                        return mulaw_audio
                    else:
                        logger.error("[SARVAM_TTS] No audio in response")
                        return None
                else:
                    logger.error(f"[SARVAM_TTS] Error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"[SARVAM_TTS] Exception: {e}")
            return None

    async def synthesize_azuretts(self, text: str) -> Optional[bytes]:
        """Synthesize using Azure Text-to-Speech"""
        api_key = self.api_keys.get('azure')
        region = self.assistant_config.get('azure_region', 'eastus')

        if not api_key:
            logger.error("[AZURE_TTS] No API key configured")
            return None

        try:
            # Get voice name from config
            voice_name = self.tts_voice or "en-US-JennyNeural"

            # Construct SSML
            ssml = f"""<speak version='1.0' xml:lang='en-US'>
                <voice name='{voice_name}'>{text}</voice>
            </speak>"""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                    headers={
                        "Ocp-Apim-Subscription-Key": api_key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": "raw-8khz-8bit-mono-mulaw"
                    },
                    content=ssml,
                    timeout=30.0
                )

                if response.status_code == 200:
                    return response.content
                else:
                    logger.error(f"[AZURE_TTS] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[AZURE_TTS] Exception: {e}")
            return None

    async def synthesize_elevenlabs(self, text: str) -> Optional[bytes]:
        """Synthesize using ElevenLabs"""
        api_key = self.api_keys.get('elevenlabs')
        if not api_key:
            logger.error("[ELEVENLABS_TTS] No API key configured")
            return None

        try:
            voice_id = self.tts_voice or "21m00Tcm4TlvDq8ikWAM"  # Default Rachel voice

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json"
                    },
                    json={
                        "text": text,
                        "model_id": self.tts_model or "eleven_monolingual_v1",
                        "output_format": "ulaw_8000"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    return response.content
                else:
                    logger.error(f"[ELEVENLABS_TTS] Error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"[ELEVENLABS_TTS] Exception: {e}")
            return None

    async def send_audio_to_twilio(self, audio_data: bytes):
        """Send audio back to Twilio"""
        if not self.stream_sid:
            return

        # Encode to base64 for Twilio
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        # Send in chunks (Twilio expects ~20ms chunks)
        chunk_size = 320  # bytes for mulaw at 8kHz
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            chunk_base64 = base64.b64encode(chunk).decode('utf-8')

            media_message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {
                    "payload": chunk_base64
                }
            }

            await self.twilio_ws.send(json.dumps(media_message))
            await asyncio.sleep(0.02)  # 20ms delay between chunks
