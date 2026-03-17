"""
Streaming TTS Handler for VAPI-like Low Latency
Uses ElevenLabs streaming API for real-time audio generation
"""

import asyncio
import logging
import base64
from typing import Optional, Callable, Awaitable, AsyncIterator
import aiohttp

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop

logger = logging.getLogger(__name__)


class StreamingElevenLabsTTS:
    """
    Real-time streaming TTS using ElevenLabs WebSocket API.
    
    Key features for low latency:
    1. WebSocket streaming (audio starts playing before generation completes)
    2. Chunked audio delivery (first audio chunk in ~100ms)
    3. Optimized for Turbo v2.5 model (fastest)
    """
    
    # ElevenLabs voice IDs for common voices
    VOICE_IDS = {
        "rachel": "21m00Tcm4TlvDq8ikWAM",
        "domi": "AZnzlk1XvdvUeBnXmlld",
        "bella": "EXAVITQu4vr4xnSDxMaL",
        "antoni": "ErXwobaYiN019PkySvjV",
        "josh": "TxGEqnHWrfWFTfGW9XjX",
        "arnold": "VR6AewLTigWG4xSOukaG",
        "adam": "pNInz6obpgDQGcFmaJgB",
        "sam": "yoZ06aMxZJJ28mfd3POQ",
        "shimmer": "N2lVS1w4EtoT3dr4eOWO",
    }
    
    def __init__(
        self,
        api_key: str,
        voice: str = "alloy",
        model: str = "eleven_flash_v2_5",
        output_format: str = "ulaw_8000"  # ulaw_8000 for Twilio, pcm_16000 for browser
    ):
        self.api_key = api_key
        self.voice_id = self.VOICE_IDS.get(voice.lower(), voice)  # Support both name and ID
        self.model = model
        self.output_format = output_format
        
    async def synthesize_streaming(
        self,
        text: str,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None
    ) -> bytes:
        """
        Stream TTS audio using ElevenLabs streaming API.
        
        Calls on_audio_chunk for each audio chunk as it arrives,
        allowing playback to start before synthesis completes.
        
        Returns:
            Complete audio bytes (already converted to Twilio format)
        """
        try:
            # Use configured output format (ulaw_8000 for Twilio, pcm_16000 for browser)
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?output_format={self.output_format}"
            
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "text": text,
                "model_id": self.model,
                "voice_settings": {
                    "stability": 0.5,  # Balanced — avoids robotic sound
                    "similarity_boost": 0.75,  # Higher = clearer voice clone
                    "style": 0.0,
                    "use_speaker_boost": True  # Boost clarity for laptop speakers
                }
            }
            
            all_audio = bytearray()
            chunk_count = 0
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error = await response.text()
                        logger.error(f"[STREAMING_TTS] ElevenLabs error {response.status}: {error}")
                        return bytes()
                    
                    logger.info(f"[STREAMING_TTS] 🎤 Starting audio stream for: {text[:50]}...")
                    
                    # Stream audio chunks as they arrive
                    # 4096 bytes = ~128ms at 16kHz PCM or ~256ms at 8kHz μ-law — good balance
                    # between first-byte latency and smooth playback
                    async for chunk in response.content.iter_chunked(4096):
                        if chunk:
                            chunk_count += 1
                            all_audio.extend(chunk)
                            
                            # Send directly to Twilio - no conversion needed!
                            if on_audio_chunk:
                                await on_audio_chunk(chunk)
                                if chunk_count == 1:
                                    logger.info(f"[STREAMING_TTS] ⚡ First audio chunk sent!")
            
            logger.info(f"[STREAMING_TTS] ✅ Synthesized {len(all_audio)} bytes in {chunk_count} chunks")
            return bytes(all_audio)
            
        except Exception as e:
            logger.error(f"[STREAMING_TTS] Error: {e}", exc_info=True)
            return bytes()
    
    async def synthesize_chunks(self, text: str) -> AsyncIterator[bytes]:
        """
        Generator version - yields audio chunks as they're ready.
        Perfect for pipeline architectures.
        """
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?output_format={self.output_format}"
            
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "text": text,
                "model_id": self.model,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        async for chunk in response.content.iter_chunked(4096):
                            if chunk:
                                yield chunk
                    else:
                        error = await response.text()
                        logger.error(f"[STREAMING_TTS] Error: {error}")
                        
        except Exception as e:
            logger.error(f"[STREAMING_TTS] Generator error: {e}")
    
    async def synthesize(self, text: str) -> bytes:
        """
        Non-streaming synthesis for fallback scenarios.
        Returns complete audio in Twilio format (8kHz μ-law).
        """
        return await self.synthesize_streaming(text, on_audio_chunk=None)


class StreamingOpenAITTS:
    """
    OpenAI TTS with pseudo-streaming (faster first response).
    OpenAI TTS doesn't support true streaming, but we can optimize.
    """

    def __init__(
        self,
        client,  # AsyncOpenAI client
        voice: str = "alloy",
        model: str = "tts-1",  # tts-1 is faster than tts-1-hd
        for_browser: bool = False  # True = PCM 16kHz output for browser, False = μ-law 8kHz for Twilio
    ):
        self.client = client
        self.voice = voice
        self.model = model
        self.for_browser = for_browser

    async def synthesize(self, text: str) -> bytes:
        """Synthesize with OpenAI TTS"""
        try:
            response = await self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format="pcm",
                speed=1.0
            )

            audio_bytes = response.content

            if self.for_browser:
                # Return native 24kHz PCM for browser playback (best quality)
                return audio_bytes
            else:
                # Convert 24kHz PCM to 8kHz μ-law for Twilio
                resampled, _ = audioop.ratecv(audio_bytes, 2, 1, 24000, 8000, None)
                mulaw = audioop.lin2ulaw(resampled, 2)
                return mulaw

        except Exception as e:
            logger.error(f"[OPENAI_TTS] Error: {e}")
            return bytes()


class StreamingSarvamTTS:
    """
    Sarvam AI TTS for Indian languages.
    Uses HTTP API with μ-law output for Twilio compatibility.
    """

    # Available Sarvam voices
    VOICES = {
        "anushka": "anushka",
        "manisha": "manisha",
        "vidya": "vidya",
        "arya": "arya",
        "abhilash": "abhilash",
        "karun": "karun",
        "hitesh": "hitesh"
    }

    def __init__(
        self,
        api_key: str,
        voice: str = "manisha",
        model: str = "bulbul:v2",
        language: str = "hi-IN",
        for_browser: bool = False  # True = PCM 16kHz for browser, False = μ-law 8kHz for Twilio
    ):
        self.api_key = api_key
        self.voice = self.VOICES.get(voice.lower(), voice)
        self.model = model
        self.language = language
        self.for_browser = for_browser
        self.api_url = "https://api.sarvam.ai/text-to-speech"

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize speech using Sarvam AI HTTP API.
        Returns audio in configured format (μ-law 8kHz for Twilio, PCM 16kHz for browser).
        """
        try:
            logger.info(f"[SARVAM_TTS] Synthesizing: {text[:50]}...")

            sample_rate = 24000 if self.for_browser else 8000

            payload = {
                "target_language_code": self.language,
                "text": text,
                "speaker": self.voice,
                "pitch": 0.0,
                "loudness": 1.0,
                "speech_sample_rate": sample_rate,
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
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        audios = data.get("audios", [])

                        if audios and isinstance(audios, list) and len(audios) > 0:
                            # Sarvam returns base64 encoded audio
                            audio_b64 = audios[0]
                            audio_bytes = base64.b64decode(audio_b64)

                            if self.for_browser:
                                # Return PCM directly for browser playback
                                logger.info(f"[SARVAM_TTS] Synthesized {len(audio_bytes)} bytes (PCM for browser)")
                                return audio_bytes
                            else:
                                # Convert PCM to μ-law for Twilio
                                try:
                                    mulaw = audioop.lin2ulaw(audio_bytes, 2)
                                    logger.info(f"[SARVAM_TTS] Synthesized {len(mulaw)} bytes (mulaw for Twilio)")
                                    return mulaw
                                except Exception as conv_error:
                                    logger.warning(f"[SARVAM_TTS] Audio conversion failed, returning raw: {conv_error}")
                                    return audio_bytes
                        else:
                            logger.error(f"[SARVAM_TTS] ❌ No audio in response: {data}")
                            return bytes()
                    else:
                        error_text = await response.text()
                        logger.error(f"[SARVAM_TTS] ❌ API error ({response.status}): {error_text}")
                        return bytes()

        except Exception as e:
            logger.error(f"[SARVAM_TTS] ❌ Synthesis error: {e}", exc_info=True)
            return bytes()


class StreamingCartesiaTTS:
    """
    Cartesia TTS for low-latency voice synthesis.
    Uses HTTP streaming API.
    """

    def __init__(
        self,
        api_key: str,
        voice: str = "sonic",
        model: str = "sonic-english",
        for_browser: bool = False  # True = PCM 16kHz for browser, False = μ-law 8kHz for Twilio
    ):
        self.api_key = api_key
        self.voice = voice
        self.model = model
        self.for_browser = for_browser
        self.api_url = "https://api.cartesia.ai/tts/bytes"

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize speech using Cartesia AI HTTP API.
        Returns audio in configured format (μ-law 8kHz for Twilio, PCM 16kHz for browser).
        """
        try:
            logger.info(f"[CARTESIA_TTS] Synthesizing: {text[:50]}...")

            if self.for_browser:
                output_format = {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": 24000
                }
            else:
                output_format = {
                    "container": "raw",
                    "encoding": "pcm_mulaw",
                    "sample_rate": 8000
                }

            payload = {
                "model_id": self.model,
                "transcript": text,
                "voice": {
                    "mode": "id",
                    "id": self.voice
                },
                "output_format": output_format
            }

            headers = {
                "X-API-Key": self.api_key,
                "Cartesia-Version": "2024-06-10",
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        audio_bytes = await response.read()
                        logger.info(f"[CARTESIA_TTS] ✅ Synthesized {len(audio_bytes)} bytes")
                        return audio_bytes
                    else:
                        error_text = await response.text()
                        logger.error(f"[CARTESIA_TTS] ❌ API error ({response.status}): {error_text}")
                        return bytes()

        except Exception as e:
            logger.error(f"[CARTESIA_TTS] ❌ Synthesis error: {e}", exc_info=True)
            return bytes()

