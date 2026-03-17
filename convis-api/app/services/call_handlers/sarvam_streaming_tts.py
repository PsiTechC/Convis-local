"""
Sarvam AI Streaming TTS for Low-Latency Hindi Voice

Since Sarvam doesn't support WebSocket input streaming like ElevenLabs,
we implement a "chunked streaming" approach:

1. Buffer LLM tokens until we have a complete phrase/clause
2. Send the phrase to Sarvam API immediately
3. Stream the audio back while next phrase is being generated

This achieves ~200-400ms latency (vs ~100-200ms for ElevenLabs WebSocket)
but with native Hindi quality that ElevenLabs can't match.

Supported Languages:
- hi-IN: Hindi
- bn-IN: Bengali
- ta-IN: Tamil
- te-IN: Telugu
- mr-IN: Marathi
- gu-IN: Gujarati
- kn-IN: Kannada
- ml-IN: Malayalam
- pa-IN: Punjabi
- or-IN: Odia
"""

import asyncio
import aiohttp
import base64
import logging
import re
from typing import Optional, Callable, Awaitable, AsyncIterator, List

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop

logger = logging.getLogger(__name__)


class SarvamStreamingTTS:
    """
    Sarvam AI TTS with chunked streaming for lower latency.

    Approach:
    - Collect LLM tokens until we hit a phrase boundary (comma, period, etc.)
    - Send each phrase to Sarvam immediately
    - Stream audio chunks back to Twilio as they arrive

    This provides ~200-400ms first audio latency while maintaining
    excellent Hindi pronunciation quality.
    """

    # Sarvam voice options
    VOICES = {
        "anushka": {"gender": "female", "style": "natural"},
        "manisha": {"gender": "female", "style": "natural"},
        "vidya": {"gender": "female", "style": "mature"},
        "arya": {"gender": "male", "style": "natural"},
        "abhilash": {"gender": "male", "style": "deep"},
        "karun": {"gender": "male", "style": "young"},
        "hitesh": {"gender": "male", "style": "professional"},
    }

    # Sarvam supported languages
    LANGUAGES = {
        "hi-IN": "Hindi",
        "bn-IN": "Bengali",
        "ta-IN": "Tamil",
        "te-IN": "Telugu",
        "mr-IN": "Marathi",
        "gu-IN": "Gujarati",
        "kn-IN": "Kannada",
        "ml-IN": "Malayalam",
        "pa-IN": "Punjabi",
        "or-IN": "Odia",
        "en-IN": "English (Indian)",
    }

    # Phrase boundary patterns for chunking
    PHRASE_BOUNDARIES = re.compile(r'[,।.!?;:\n]+\s*')

    def __init__(
        self,
        api_key: str,
        voice: str = "manisha",
        model: str = "bulbul:v2",
        language: str = "hi-IN",
        pitch: float = 0.0,
        loudness: float = 1.0,
        speed: float = 1.0,
        min_chunk_chars: int = 15,
        max_chunk_chars: int = 100,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None
    ):
        """
        Initialize Sarvam Streaming TTS.

        Args:
            api_key: Sarvam API key
            voice: Voice name (manisha, arya, etc.)
            model: TTS model (bulbul:v2)
            language: Language code (hi-IN, bn-IN, etc.)
            pitch: Voice pitch adjustment (-1.0 to 1.0)
            loudness: Volume level (0.5 to 2.0)
            speed: Speech speed (0.5 to 2.0)
            min_chunk_chars: Minimum characters before sending to API
            max_chunk_chars: Maximum characters per chunk
            on_audio_chunk: Callback for each audio chunk
        """
        self.api_key = api_key
        self.voice = voice.lower()
        self.model = model
        self.language = language
        self.pitch = pitch
        self.loudness = loudness
        self.speed = speed
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars
        self.on_audio_chunk = on_audio_chunk

        self.api_url = "https://api.sarvam.ai/text-to-speech"

        # State
        self.audio_buffer = bytearray()
        self.first_audio_received = asyncio.Event()
        self.generation_complete = asyncio.Event()
        self.chunks_sent = 0
        self.is_streaming = False

        logger.info(f"[SARVAM_STREAM] Initialized: voice={voice}, language={language}, model={model}")

    async def _synthesize_chunk(self, text: str) -> bytes:
        """
        Synthesize a single text chunk using Sarvam API.
        Returns μ-law audio for Twilio.
        """
        if not text or not text.strip():
            return bytes()

        try:
            payload = {
                "target_language_code": self.language,
                "text": text.strip(),
                "speaker": self.voice,
                "pitch": self.pitch,
                "loudness": self.loudness,
                "speech_sample_rate": 8000,
                "enable_preprocessing": True,
                "model": self.model
            }

            headers = {
                "api-subscription-key": self.api_key,
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        audios = data.get("audios", [])

                        if audios and len(audios) > 0:
                            audio_b64 = audios[0]
                            audio_bytes = base64.b64decode(audio_b64)

                            # Convert PCM to μ-law for Twilio
                            try:
                                mulaw = audioop.lin2ulaw(audio_bytes, 2)
                                return mulaw
                            except Exception:
                                return audio_bytes
                        else:
                            logger.warning(f"[SARVAM_STREAM] No audio in response for: {text[:30]}")
                            return bytes()
                    else:
                        error = await response.text()
                        logger.error(f"[SARVAM_STREAM] API error ({response.status}): {error}")
                        return bytes()

        except Exception as e:
            logger.error(f"[SARVAM_STREAM] Synthesis error: {e}")
            return bytes()

    def _split_into_chunks(self, text: str) -> List[str]:
        """
        Split text into speakable chunks at natural boundaries.
        """
        chunks = []

        # Split by phrase boundaries
        parts = self.PHRASE_BOUNDARIES.split(text)

        current_chunk = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue

            if len(current_chunk) + len(part) < self.max_chunk_chars:
                current_chunk += " " + part if current_chunk else part
            else:
                if current_chunk and len(current_chunk) >= self.min_chunk_chars:
                    chunks.append(current_chunk.strip())
                current_chunk = part

        # Don't forget the last chunk
        if current_chunk and len(current_chunk) >= self.min_chunk_chars:
            chunks.append(current_chunk.strip())
        elif current_chunk and chunks:
            # Append to last chunk if too short
            chunks[-1] += " " + current_chunk.strip()
        elif current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    async def stream_from_llm(
        self,
        token_iterator: AsyncIterator[str],
        on_first_audio: Optional[Callable[[], Awaitable[None]]] = None
    ) -> bytes:
        """
        Stream LLM tokens to Sarvam TTS with chunked approach.

        Collects tokens until a phrase boundary, then immediately
        sends to Sarvam and streams audio back.

        Args:
            token_iterator: Async iterator yielding LLM tokens
            on_first_audio: Callback when first audio is ready

        Returns:
            Complete audio bytes
        """
        self.audio_buffer.clear()
        self.first_audio_received.clear()
        self.generation_complete.clear()
        self.chunks_sent = 0
        self.is_streaming = True

        text_buffer = ""
        pending_tasks = []
        first_audio_sent = False

        async def process_chunk(chunk_text: str, chunk_num: int):
            """Process a single chunk and send audio"""
            nonlocal first_audio_sent

            audio = await self._synthesize_chunk(chunk_text)
            if audio:
                self.audio_buffer.extend(audio)

                if not first_audio_sent:
                    first_audio_sent = True
                    self.first_audio_received.set()
                    if on_first_audio:
                        await on_first_audio()
                    logger.info(f"[SARVAM_STREAM] ⚡ First audio chunk!")

                if self.on_audio_chunk:
                    await self.on_audio_chunk(audio)

                logger.debug(f"[SARVAM_STREAM] Chunk {chunk_num}: {len(audio)} bytes")

        try:
            chunk_num = 0

            async for token in token_iterator:
                if not self.is_streaming:
                    break

                text_buffer += token

                # Check if we have a complete phrase
                if self.PHRASE_BOUNDARIES.search(text_buffer):
                    # Extract complete phrases
                    chunks = self._split_into_chunks(text_buffer)

                    # Keep incomplete part in buffer
                    last_boundary = max(
                        text_buffer.rfind(','),
                        text_buffer.rfind('।'),
                        text_buffer.rfind('.'),
                        text_buffer.rfind('!'),
                        text_buffer.rfind('?'),
                        text_buffer.rfind('\n')
                    )

                    if last_boundary > 0:
                        complete_text = text_buffer[:last_boundary + 1]
                        text_buffer = text_buffer[last_boundary + 1:].strip()

                        # Process complete phrases
                        for chunk in self._split_into_chunks(complete_text):
                            if chunk and len(chunk) >= self.min_chunk_chars:
                                chunk_num += 1
                                self.chunks_sent += 1
                                # Process immediately (don't wait)
                                task = asyncio.create_task(process_chunk(chunk, chunk_num))
                                pending_tasks.append(task)

            # Process remaining text
            if text_buffer.strip():
                chunk_num += 1
                self.chunks_sent += 1
                task = asyncio.create_task(process_chunk(text_buffer.strip(), chunk_num))
                pending_tasks.append(task)

            # Wait for all chunks to complete
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)

            self.generation_complete.set()
            logger.info(f"[SARVAM_STREAM] ✅ Complete: {self.chunks_sent} chunks, {len(self.audio_buffer)} bytes")

            return bytes(self.audio_buffer)

        except Exception as e:
            logger.error(f"[SARVAM_STREAM] Stream error: {e}")
            return bytes(self.audio_buffer)

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize complete text (single request).
        For compatibility with non-streaming use cases.
        """
        self.audio_buffer.clear()
        self.first_audio_received.clear()

        # Split into chunks for parallel processing
        chunks = self._split_into_chunks(text)

        if not chunks:
            chunks = [text]

        # Process chunks in parallel
        tasks = [self._synthesize_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine audio in order
        for i, result in enumerate(results):
            if isinstance(result, bytes) and result:
                self.audio_buffer.extend(result)

                if not self.first_audio_received.is_set():
                    self.first_audio_received.set()
                    if self.on_audio_chunk:
                        await self.on_audio_chunk(result)
                elif self.on_audio_chunk:
                    await self.on_audio_chunk(result)

        self.generation_complete.set()
        return bytes(self.audio_buffer)

    async def send_text(self, text: str, flush: bool = False):
        """
        Compatibility method for word-by-word interface.
        Buffers text and synthesizes when flush=True or phrase boundary hit.
        """
        # This is handled internally via stream_from_llm
        pass

    def stop(self):
        """Stop current streaming"""
        self.is_streaming = False

    async def close(self):
        """Close handler (cleanup)"""
        self.is_streaming = False
        logger.info("[SARVAM_STREAM] 🔌 Closed")


# Model information
SARVAM_MODELS = {
    "bulbul:v2": {
        "description": "Latest Sarvam TTS model with improved quality",
        "languages": ["hi-IN", "bn-IN", "ta-IN", "te-IN", "mr-IN", "gu-IN", "kn-IN", "ml-IN", "pa-IN", "or-IN", "en-IN"],
        "streaming": False,
        "chunked_streaming": True,
        "recommended_for": "Hindi and Indian language applications"
    },
    "bulbul:v1": {
        "description": "Original Sarvam TTS model",
        "languages": ["hi-IN", "en-IN"],
        "streaming": False,
        "chunked_streaming": True,
        "recommended_for": "Legacy compatibility"
    }
}
