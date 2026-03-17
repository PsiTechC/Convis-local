"""
OpenAI TTS Synthesizer for Convis
Adapted from Bolna architecture
Uses OpenAI's text-to-speech API with HTTP streaming
"""
import asyncio
import io
import os
from collections import deque
from openai import AsyncOpenAI

from .base_synthesizer import BaseSynthesizer
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.helpers.utils import (
    convert_audio_to_wav,
    create_ws_data_packet,
    resample,
    wav_bytes_to_pcm,
    pcm16_to_mulaw,
)

logger = configure_logger(__name__)


class OpenAISynthesizer(BaseSynthesizer):
    """
    OpenAI TTS synthesizer using HTTP streaming
    Supports: tts-1 (fast), tts-1-hd (high quality)
    Voices: alloy, echo, fable, onyx, nova, shimmer
    """

    def __init__(
        self,
        voice,
        audio_format="mp3",
        model="tts-1",
        stream=False,
        sampling_rate=8000,
        buffer_size=400,
        synthesizer_key=None,
        use_mulaw=False,
        speed=1.0,
        **kwargs
    ):
        super().__init__(kwargs.get("task_manager_instance", None), stream, buffer_size)

        self.format = self.get_format(audio_format.lower())
        self.voice = voice
        self.sample_rate = sampling_rate
        self.use_mulaw = use_mulaw
        self.speed = speed

        # OpenAI client
        api_key = synthesizer_key or os.getenv("OPENAI_API_KEY")
        self.async_client = AsyncOpenAI(api_key=api_key)
        self.model = model

        # Streaming state
        self.first_chunk_generated = False
        self.text_queue = deque()
        self.stream = stream
        self.synthesized_characters = 0

        if isinstance(self.sample_rate, str):
            self.sample_rate = int(self.sample_rate)

        logger.info(f"[OPENAI_TTS] Initialized with voice={voice}, model={model}, speed={speed}, sample_rate={self.sample_rate}")

    def get_format(self, format):
        # OpenAI supports: mp3, opus, aac, flac, wav, pcm
        # For Twilio μ-law compatibility, we use mp3 and convert
        return "mp3"

    def get_engine(self):
        return self.model

    def supports_websocket(self):
        # OpenAI TTS uses HTTP streaming, not WebSocket
        return False

    async def synthesize(self, text):
        """
        One-off synthesis for use cases like voice lab and IVR
        """
        audio = await self.__generate_http(text)
        return audio

    async def __generate_http(self, text):
        """
        Generate audio using OpenAI HTTP API (non-streaming)
        """
        try:
            spoken_response = await self.async_client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                response_format=self.format,
                speed=self.speed,
                input=text
            )

            buffer = io.BytesIO()
            for chunk in spoken_response.iter_bytes(chunk_size=4096):
                buffer.write(chunk)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            logger.error(f"[OPENAI_TTS] HTTP generation error: {e}")
            raise

    async def __generate_stream(self, text):
        """
        Generate audio using OpenAI streaming
        """
        try:
            spoken_response = await self.async_client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                response_format="mp3",
                speed=self.speed,
                input=text
            )

            for chunk in spoken_response.iter_bytes(chunk_size=4096):
                yield chunk
        except Exception as e:
            logger.error(f"[OPENAI_TTS] Stream generation error: {e}")
            raise

    async def sender(self, text, sequence_id, end_of_llm_stream=False):
        """
        Compatibility method for pipeline integration
        OpenAI uses HTTP, so we queue the text for processing
        """
        if not text or len(text.strip()) == 0:
            return

        if not self.should_synthesize_response(sequence_id):
            logger.info(
                f"[OPENAI_TTS] Not synthesizing - sequence_id {sequence_id} not in current_ids"
            )
            return

        logger.info(f"[OPENAI_TTS] Queuing text for synthesis: {text[:50]}...")
        self.synthesized_characters += len(text)

        # Queue for generate method
        message = {
            "data": text,
            "meta_info": {
                "sequence_id": sequence_id,
                "end_of_llm_stream": end_of_llm_stream,
                "text": text
            }
        }
        await self.internal_queue.put(message)

    async def receiver(self):
        """
        Compatibility method for pipeline integration
        OpenAI doesn't use separate receiver - all handled in generate()
        """
        # Not used for HTTP-based synthesis
        pass

    async def generate(self):
        """
        Main synthesis loop - processes queued text and generates audio
        """
        try:
            while True:
                message = await self.internal_queue.get()
                logger.info(f"[OPENAI_TTS] Generating TTS response")

                meta_info = message.get("meta_info", {})
                text = message.get("data", "")

                if not text:
                    continue

                meta_info["text"] = text

                if not self.should_synthesize_response(meta_info.get('sequence_id')):
                    logger.info(
                        f"[OPENAI_TTS] Not synthesizing - sequence_id not in current_ids"
                    )
                    continue

                if self.stream:
                    # Streaming mode
                    async for chunk in self.__generate_stream(text):
                        if not self.first_chunk_generated:
                            meta_info["is_first_chunk"] = True
                            self.first_chunk_generated = True
                        else:
                            meta_info["is_first_chunk"] = False

                        # Convert mp3 to wav and resample to target sample rate
                        try:
                            wav_audio = convert_audio_to_wav(chunk, 'mp3')
                            resampled_audio = resample(wav_audio, self.sample_rate, format="wav")
                            pcm_audio = wav_bytes_to_pcm(resampled_audio)

                            if self.use_mulaw:
                                audio_bytes = pcm16_to_mulaw(pcm_audio)
                                meta_info["format"] = "mulaw"
                            else:
                                audio_bytes = pcm_audio
                                meta_info["format"] = "pcm"

                            yield create_ws_data_packet(audio_bytes, meta_info)
                        except Exception as e:
                            logger.error(f"[OPENAI_TTS] Audio conversion error: {e}")
                            continue

                    # End of stream marker
                    if "end_of_llm_stream" in meta_info and meta_info["end_of_llm_stream"]:
                        meta_info["end_of_synthesizer_stream"] = True
                        self.first_chunk_generated = False
                        yield create_ws_data_packet(b"\x00", meta_info)

                else:
                    # Non-streaming mode
                    logger.info(f"[OPENAI_TTS] Generating without stream")
                    audio = await self.__generate_http(text)

                    if not self.first_chunk_generated:
                        meta_info["is_first_chunk"] = True
                        self.first_chunk_generated = True

                    if "end_of_llm_stream" in meta_info and meta_info["end_of_llm_stream"]:
                        meta_info["end_of_synthesizer_stream"] = True
                        self.first_chunk_generated = False

                    # Convert mp3 to wav and resample
                    try:
                        wav_audio = convert_audio_to_wav(audio, 'mp3')
                        resampled_audio = resample(wav_audio, self.sample_rate, format="wav")
                        pcm_audio = wav_bytes_to_pcm(resampled_audio)

                        if self.use_mulaw:
                            audio_bytes = pcm16_to_mulaw(pcm_audio)
                            meta_info["format"] = "mulaw"
                        else:
                            audio_bytes = pcm_audio
                            meta_info["format"] = "pcm"

                        yield create_ws_data_packet(audio_bytes, meta_info)
                    except Exception as e:
                        logger.error(f"[OPENAI_TTS] Audio conversion error: {e}")

        except Exception as e:
            logger.error(f"[OPENAI_TTS] Error in generate: {e}", exc_info=True)

    async def establish_connection(self):
        """
        Compatibility method - OpenAI TTS doesn't need WebSocket connection
        """
        logger.info("[OPENAI_TTS] No WebSocket connection needed (HTTP-based)")
        return None

    async def monitor_connection(self):
        """
        Compatibility method - no connection monitoring needed for HTTP
        """
        pass

    async def push(self, message):
        """
        Push text to synthesis queue
        """
        logger.info(f"[OPENAI_TTS] Pushed message to internal queue")
        await self.internal_queue.put(message)

    def get_synthesized_characters(self):
        return self.synthesized_characters

    async def cleanup(self):
        """
        Cleanup resources
        """
        logger.info("[OPENAI_TTS] Cleaning up synthesizer")
        await self.async_client.close()
