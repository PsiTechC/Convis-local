"""
ASR (Automatic Speech Recognition) Provider Abstraction
"""

import logging
import asyncio
import io
import wave
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
import os

logger = logging.getLogger(__name__)


class ASRProvider(ABC):
    """Base class for all ASR providers"""

    def __init__(self, api_key: str, model: str = "default", language: str = "en"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """
        Transcribe streaming audio in real-time

        Args:
            audio_stream: Async iterator of audio chunks (PCM bytes)

        Yields:
            Transcribed text chunks
        """
        pass

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe complete audio file

        Args:
            audio_bytes: Complete audio data (PCM bytes)

        Returns:
            Complete transcription text
        """
        pass

    @abstractmethod
    def get_latency_ms(self) -> int:
        """Get average latency in milliseconds"""
        pass

    @abstractmethod
    def get_cost_per_minute(self) -> float:
        """Get cost per minute in USD"""
        pass


class DeepgramASR(ASRProvider):
    """
    Deepgram Nova-2 ASR Provider

    Latency: 50-100ms
    Cost: $0.0043/min
    Best for: Fast, accurate transcription
    """

    # Default keywords for better email/domain recognition (with boost weights)
    DEFAULT_KEYWORDS = [
        "gmail:100", "yahoo:100", "outlook:100", "hotmail:100",
        "icloud:80", "protonmail:80", "aol:80",
        "@:50", "dot com:80", "dot in:80", "dot org:80", "dot net:80",
        "at the rate:50", "at sign:50"
    ]

    def __init__(self, api_key: Optional[str] = None, model: str = "nova-2", language: str = "en", keywords: Optional[str] = None):
        super().__init__(
            api_key=api_key or os.getenv("DEEPGRAM_API_KEY"),
            model=model,
            language=language
        )
        self.deepgram = None
        # Build keywords list - combine user keywords with defaults
        self.keywords = self._build_keywords(keywords)
        self._init_client()

    def _build_keywords(self, user_keywords: Optional[str]) -> Optional[str]:
        """
        Build keywords list by combining user keywords with defaults.
        User keywords take precedence over defaults.

        Args:
            user_keywords: Comma-separated keywords from user config

        Returns:
            Combined keywords string or None if empty
        """
        # Parse user keywords
        user_kw_list = []
        if user_keywords:
            user_kw_list = [kw.strip() for kw in user_keywords.split(',') if kw.strip()]

        # Combine with defaults (user keywords take precedence)
        all_keywords = list(user_kw_list)
        for default_kw in self.DEFAULT_KEYWORDS:
            # Extract base keyword (without boost weight)
            kw_base = default_kw.split(":")[0].lower()
            # Only add default if not already in user keywords
            if not any(kw_base in ukw.lower() for ukw in all_keywords):
                all_keywords.append(default_kw)

        keywords_str = ",".join(all_keywords) if all_keywords else None
        if keywords_str:
            self.logger.info(f"Deepgram keywords configured: {keywords_str}")

        return keywords_str

    def _init_client(self):
        """Initialize Deepgram client"""
        try:
            from deepgram import DeepgramClient
            self.deepgram = DeepgramClient(api_key=self.api_key)
            self.logger.info(f"Deepgram ASR initialized with model: {self.model}")
            if self.keywords:
                self.logger.info(f"Deepgram keyword boosting enabled")
        except ImportError:
            self.logger.error("deepgram-sdk not installed. Run: pip install deepgram-sdk")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Deepgram: {e}")
            raise

    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """
        Stream transcription using Deepgram Live API
        """
        try:
            # Deepgram live transcription options
            options = {
                'punctuate': True,
                'model': self.model,
                'language': self.language,
                'encoding': 'linear16',
                'sample_rate': 8000,  # Twilio uses 8kHz
                'channels': 1,
                'interim_results': False,  # Only final results
                'endpointing': 300  # End of speech detection (300ms)
            }

            # Add keyword boosting if configured
            if self.keywords:
                options['keywords'] = self.keywords
                self.logger.info(f"Deepgram streaming with keywords: {self.keywords}")

            # Create live transcription connection
            deepgramLive = await self.deepgram.transcription.live(options)

            # Handle transcription results
            async def handle_transcript(transcript):
                if transcript:
                    text = transcript.get('channel', {}).get('alternatives', [{}])[0].get('transcript', '')
                    if text:
                        yield text

            deepgramLive.registerHandler(
                deepgramLive.event.TRANSCRIPT_RECEIVED,
                handle_transcript
            )

            # Stream audio chunks
            async for audio_chunk in audio_stream:
                deepgramLive.send(audio_chunk)

            # Close connection
            deepgramLive.finish()

        except Exception as e:
            self.logger.error(f"Deepgram streaming error: {e}")
            raise

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe complete audio using Deepgram Pre-recorded API
        """
        try:
            from deepgram import PrerecordedOptions, FileSource

            # Build options with keyword boosting
            options_dict = {
                'model': self.model,
                'punctuate': True,
                'language': self.language
            }

            # Add keywords if configured
            if self.keywords:
                options_dict['keywords'] = self.keywords.split(',')
                self.logger.info(f"Deepgram transcription with keyword boosting enabled")

            options = PrerecordedOptions(**options_dict)

            payload = FileSource(buffer=audio_bytes)

            response = await self.deepgram.listen.asyncrest.v("1").transcribe_file(
                payload,
                options
            )

            transcript = response['results']['channels'][0]['alternatives'][0]['transcript']
            return transcript

        except Exception as e:
            self.logger.error(f"Deepgram transcription error: {e}")
            raise

    def get_latency_ms(self) -> int:
        """Average latency: 50-100ms"""
        return 75

    def get_cost_per_minute(self) -> float:
        """Cost: $0.0043/min"""
        return 0.0043


class OpenAIASR(ASRProvider):
    """
    OpenAI Whisper ASR Provider

    Latency: 200-300ms
    Cost: $0.006/min (Whisper API)
    Best for: High accuracy, multiple languages
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1", language: str = "en"):
        super().__init__(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            model=model,
            language=language
        )
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize OpenAI client"""
        try:
            import openai
            self.client = openai.AsyncOpenAI(api_key=self.api_key)
            self.logger.info(f"OpenAI ASR initialized with model: {self.model}")
        except ImportError:
            self.logger.error("openai package not installed. Run: pip install openai")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI: {e}")
            raise

    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """
        OpenAI Whisper doesn't support true streaming,
        so we accumulate chunks and transcribe periodically
        """
        buffer = bytearray()
        chunk_size = 16000 * 2  # 1 second at 16kHz, 16-bit

        async for audio_chunk in audio_stream:
            buffer.extend(audio_chunk)

            # Transcribe every 1 second of audio
            if len(buffer) >= chunk_size:
                try:
                    # Save to temporary file (Whisper requires file)
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                        temp_file.write(bytes(buffer))
                        temp_path = temp_file.name

                    # Transcribe
                    with open(temp_path, "rb") as audio_file:
                        transcript = await self.client.audio.transcriptions.create(
                            model=self.model,
                            file=audio_file,
                            language=self.language
                        )

                    # Clean up
                    os.unlink(temp_path)

                    if transcript.text:
                        yield transcript.text

                    buffer.clear()

                except Exception as e:
                    self.logger.error(f"OpenAI transcription error: {e}")

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe complete audio"""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            with open(temp_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=self.language
                )

            os.unlink(temp_path)
            return transcript.text

        except Exception as e:
            self.logger.error(f"OpenAI transcription error: {e}")
            raise

    def get_latency_ms(self) -> int:
        """Average latency: 200-300ms"""
        return 250

    def get_cost_per_minute(self) -> float:
        """Cost: $0.006/min"""
        return 0.006


class SarvamASR(ASRProvider):
    """
    Sarvam AI ASR Provider for Indian Languages

    Latency: 100-200ms
    Cost: $0.005/min
    Best for: Hindi, Tamil, Telugu, and other Indian languages
    """

    # Map short codes to Sarvam locale codes
    LANGUAGE_MAP = {
        "en": "en-IN", "hi": "hi-IN", "bn": "bn-IN", "ta": "ta-IN",
        "te": "te-IN", "mr": "mr-IN", "gu": "gu-IN", "kn": "kn-IN",
        "ml": "ml-IN", "pa": "pa-IN", "ur": "ur-IN", "od": "od-IN",
    }

    # Force all deprecated models to the latest working version
    VALID_MODELS = {"saarika:v2.5", "saaras:v3"}

    def __init__(self, api_key: Optional[str] = None, model: str = "saarika:v2.5", language: str = "hi-IN"):
        # Auto-correct deprecated models (v1, v2 → v2.5)
        if model not in self.VALID_MODELS:
            logger.warning(f"[SARVAM_ASR] Model '{model}' is deprecated, using 'saarika:v2.5'")
            model = "saarika:v2.5"
        super().__init__(
            api_key=api_key or os.getenv("SARVAM_API_KEY"),
            model=model,
            language=language
        )
        self.base_url = "https://api.sarvam.ai"

    # All language codes Sarvam API actually accepts
    SUPPORTED_LOCALES = {
        "unknown", "hi-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN",
        "pa-IN", "ta-IN", "te-IN", "en-IN", "gu-IN", "as-IN", "ur-IN",
        "ne-IN", "kok-IN", "ks-IN", "sd-IN", "sa-IN", "sat-IN", "mni-IN",
        "brx-IN", "mai-IN", "doi-IN",
    }

    def set_language(self, language: str):
        """Update ASR language for next transcription (called on mid-call language switch)."""
        old = self.language
        normalized = self.LANGUAGE_MAP.get(language.lower(), language)
        # Accept full locale codes as-is (e.g., "hi-IN")
        if "-" in language and language not in self.LANGUAGE_MAP:
            normalized = language
        # Only set if Sarvam supports this language, otherwise use 'unknown' for auto-detect
        if normalized not in self.SUPPORTED_LOCALES:
            self.logger.warning(f"[SARVAM_ASR] Language '{normalized}' not supported by Sarvam, using 'unknown'")
            normalized = "unknown"
        self.language = normalized
        self.logger.info(f"[SARVAM_ASR] Language switched: {old} → {self.language}")

    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """
        Sarvam streaming transcription via WebSocket
        Falls back to buffered transcription if streaming not available
        """
        import aiohttp

        buffer = bytearray()
        chunk_size = 8000 * 2  # 1 second at 8kHz μ-law

        async for audio_chunk in audio_stream:
            buffer.extend(audio_chunk)

            if len(buffer) >= chunk_size:
                try:
                    text = await self.transcribe(bytes(buffer))
                    if text:
                        yield text
                    buffer.clear()
                except Exception as e:
                    self.logger.error(f"Sarvam transcription error: {e}")

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe complete audio using Sarvam API"""
        import aiohttp

        try:
            headers = {
                "api-subscription-key": self.api_key,
            }

            # Twilio/custom handlers pass raw 8kHz mono PCM. Wrap it in a WAV
            # container because Sarvam expects multipart file uploads.
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(8000)
                wav_file.writeframes(audio_bytes)
            wav_bytes = wav_buffer.getvalue()

            self.logger.debug(f"[SARVAM_ASR] WAV size: {len(wav_bytes)} bytes, PCM input: {len(audio_bytes)} bytes")

            form = aiohttp.FormData()
            form.add_field(
                "file",
                wav_bytes,
                filename="audio.wav",
                content_type="audio/wav",
            )
            form.add_field("model", self.model)
            # Only send language_code if it's a valid Sarvam locale
            if self.language and self.language not in ("auto", ""):
                lang_to_send = self.language if self.language in self.SUPPORTED_LOCALES else "unknown"
                form.add_field("language_code", lang_to_send)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/speech-to-text",
                    headers=headers,
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return (result.get("transcript") or result.get("text") or "").strip()
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Sarvam API error: {response.status} - {error_text}")
                        return ""

        except Exception as e:
            self.logger.error(f"Sarvam transcription error: {e}")
            raise

    def get_latency_ms(self) -> int:
        """Average latency: 100-200ms"""
        return 150

    def get_cost_per_minute(self) -> float:
        """Cost: $0.005/min"""
        return 0.005


class GoogleASR(ASRProvider):
    """
    Google Cloud Speech-to-Text ASR Provider

    Latency: 100-200ms
    Cost: $0.006/min
    Best for: High accuracy, many languages, enterprise features
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "latest_long", language: str = "en-US"):
        super().__init__(
            api_key=api_key or os.getenv("GOOGLE_API_KEY"),
            model=model,
            language=language
        )
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Google Speech client"""
        try:
            from google.cloud import speech
            # Google uses Application Default Credentials or GOOGLE_APPLICATION_CREDENTIALS
            self.client = speech.SpeechClient()
            self.speech = speech
            self.logger.info(f"Google ASR initialized with model: {self.model}")
        except ImportError:
            self.logger.error("google-cloud-speech package not installed. Run: pip install google-cloud-speech")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Speech: {e}")
            self.logger.info("Make sure GOOGLE_APPLICATION_CREDENTIALS environment variable is set")
            raise

    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """
        Google Cloud Speech streaming transcription
        """
        import asyncio

        config = self.speech.RecognitionConfig(
            encoding=self.speech.RecognitionConfig.AudioEncoding.MULAW,
            sample_rate_hertz=8000,
            language_code=self.language,
            model=self.model,
            enable_automatic_punctuation=True,
        )

        streaming_config = self.speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        async def request_generator():
            yield self.speech.StreamingRecognizeRequest(streaming_config=streaming_config)
            async for chunk in audio_stream:
                yield self.speech.StreamingRecognizeRequest(audio_content=chunk)

        try:
            # Run in executor since Google client is sync
            loop = asyncio.get_event_loop()
            responses = await loop.run_in_executor(
                None,
                lambda: list(self.client.streaming_recognize(streaming_config, request_generator()))
            )

            for response in responses:
                for result in response.results:
                    if result.is_final:
                        yield result.alternatives[0].transcript

        except Exception as e:
            self.logger.error(f"Google streaming transcription error: {e}")

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe complete audio using Google Speech API"""
        import asyncio

        try:
            config = self.speech.RecognitionConfig(
                encoding=self.speech.RecognitionConfig.AudioEncoding.MULAW,
                sample_rate_hertz=8000,
                language_code=self.language,
                model=self.model,
                enable_automatic_punctuation=True,
            )

            audio = self.speech.RecognitionAudio(content=audio_bytes)

            # Run in executor since Google client is sync
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.recognize(config=config, audio=audio)
            )

            if response.results:
                return response.results[0].alternatives[0].transcript
            return ""

        except Exception as e:
            self.logger.error(f"Google transcription error: {e}")
            raise

    def get_latency_ms(self) -> int:
        """Average latency: 100-200ms"""
        return 150

    def get_cost_per_minute(self) -> float:
        """Cost: $0.006/min"""
        return 0.006
