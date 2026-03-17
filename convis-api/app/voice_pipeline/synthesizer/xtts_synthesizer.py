"""
Coqui XTTS v2 Synthesizer for Voice Pipeline
Uses the XTTS streaming server running locally or on a remote server.
"""
import asyncio
import io
import os
import time
import json
import struct
try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop
import aiohttp
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample as scipy_resample

from .base_synthesizer import BaseSynthesizer
from app.voice_pipeline.helpers.logger_config import configure_logger
from app.voice_pipeline.helpers.utils import create_ws_data_packet

logger = configure_logger(__name__)


class XTTSSynthesizer(BaseSynthesizer):
    """
    Coqui XTTS v2 TTS Synthesizer
    Connects to an XTTS streaming server for text-to-speech conversion.
    """

    def __init__(
        self,
        voice='default',
        voice_id=None,
        model='xtts_v2',
        synthesizer_key=None,
        stream=True,
        use_mulaw=True,
        speed=1.0,
        task_manager_instance=None,
        **kwargs
    ):
        super().__init__(task_manager_instance=task_manager_instance, stream=stream)

        # XTTS server URL
        self.xtts_url = synthesizer_key or os.getenv("XTTS_API_URL", "http://localhost:5500")
        self.xtts_url = self.xtts_url.rstrip("/")

        self.voice = voice
        self.voice_id = voice_id
        self.model = model
        self.use_mulaw = use_mulaw
        self.speed = speed
        self.language = kwargs.get('language', 'en')

        # Speaker embedding (will be fetched from studio speakers or cloned)
        self.speaker_embedding = None
        self.gpt_cond_latent = None
        self.speaker_ready = False

        # Track synthesized characters
        self.synthesized_chars = 0

        logger.info(f"[XTTS] Initialized with URL: {self.xtts_url}, voice: {self.voice}")

    async def _ensure_speaker(self):
        """Ensure we have speaker embeddings (from studio speakers)"""
        if self.speaker_ready:
            return

        try:
            async with aiohttp.ClientSession() as session:
                # Try to get studio speakers first
                async with session.get(f"{self.xtts_url}/studio_speakers", timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        speakers = await response.json()
                        if speakers:
                            # Use first available speaker or match by name
                            speaker_name = None
                            if self.voice and self.voice != 'default':
                                for name in speakers:
                                    if self.voice.lower() in name.lower():
                                        speaker_name = name
                                        break

                            if not speaker_name:
                                speaker_name = list(speakers.keys())[0]

                            speaker_data = speakers[speaker_name]
                            self.speaker_embedding = speaker_data.get('speaker_embedding')
                            self.gpt_cond_latent = speaker_data.get('gpt_cond_latent')
                            self.speaker_ready = True
                            logger.info(f"[XTTS] Using studio speaker: {speaker_name}")
                            return

                # If no studio speakers, use a default reference audio
                logger.warning("[XTTS] No studio speakers found. Will use default voice.")
                # Create a minimal speaker embedding request
                self.speaker_ready = False

        except Exception as e:
            logger.error(f"[XTTS] Error getting speaker: {e}")
            self.speaker_ready = False

    async def generate(self):
        """Main generation loop - reads from internal queue, synthesizes, outputs audio"""
        while True:
            try:
                message = await self.internal_queue.get()

                if not message or not isinstance(message, dict):
                    continue

                text = message.get('data', '')
                meta_info = message.get('meta_info', {})
                sequence_id = meta_info.get('sequence_id')

                if not text or not text.strip():
                    continue

                if not self.should_synthesize_response(sequence_id):
                    logger.info(f"[XTTS] Skipping synthesis for outdated sequence {sequence_id}")
                    continue

                logger.info(f"[XTTS] Synthesizing: '{text[:50]}...'")
                start_time = time.time()

                # Synthesize text
                audio_data = await self._synthesize_text(text)

                if audio_data:
                    elapsed = time.time() - start_time
                    logger.info(f"[XTTS] Synthesis took {elapsed:.2f}s for {len(text)} chars")
                    self.synthesized_chars += len(text)

                    # Put audio in output queue
                    output_message = create_ws_data_packet(
                        data=audio_data,
                        meta_info=meta_info
                    )
                    await self.synthesizer_output_queue.put(output_message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[XTTS] Error in generate loop: {e}", exc_info=True)

    async def _synthesize_text(self, text):
        """Send text to XTTS server and get audio back"""
        await self._ensure_speaker()

        try:
            if self.speaker_ready and self.speaker_embedding and self.gpt_cond_latent:
                return await self._synthesize_with_embeddings(text)
            else:
                return await self._synthesize_with_streaming(text)
        except Exception as e:
            logger.error(f"[XTTS] Synthesis error: {e}", exc_info=True)
            return None

    async def _synthesize_with_embeddings(self, text):
        """Synthesize using speaker embeddings via /tts endpoint"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": text,
                    "language": self.language,
                    "speaker_embedding": self.speaker_embedding,
                    "gpt_cond_latent": self.gpt_cond_latent
                }

                async with session.post(
                    f"{self.xtts_url}/tts",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        audio_bytes = await response.read()
                        return self._convert_audio_for_twilio(audio_bytes)
                    else:
                        error = await response.text()
                        logger.error(f"[XTTS] TTS failed: {response.status} - {error}")
                        return None

        except Exception as e:
            logger.error(f"[XTTS] Error in embeddings synthesis: {e}")
            return None

    async def _synthesize_with_streaming(self, text):
        """Synthesize using /tts_stream endpoint"""
        try:
            if not self.speaker_embedding or not self.gpt_cond_latent:
                logger.warning("[XTTS] No speaker embeddings available, cannot synthesize")
                return None

            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": text,
                    "language": self.language,
                    "speaker_embedding": self.speaker_embedding,
                    "gpt_cond_latent": self.gpt_cond_latent,
                    "add_wav_header": True,
                    "stream_chunk_size": "20"
                }

                audio_chunks = []
                async with session.post(
                    f"{self.xtts_url}/tts_stream",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        async for chunk in response.content.iter_any():
                            if chunk:
                                audio_chunks.append(chunk)

                if audio_chunks:
                    combined = b''.join(audio_chunks)
                    return self._convert_audio_for_twilio(combined)

                return None

        except Exception as e:
            logger.error(f"[XTTS] Error in streaming synthesis: {e}")
            return None

    def _convert_audio_for_twilio(self, audio_bytes):
        """Convert XTTS audio output to Twilio-compatible format (μ-law 8kHz)"""
        try:
            # Read the WAV data
            wav_buffer = io.BytesIO(audio_bytes)
            try:
                sample_rate, audio_data = wavfile.read(wav_buffer)
            except Exception:
                # If not a valid WAV, try treating as raw PCM (24kHz 16-bit)
                audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
                sample_rate = 24000

            # Convert to float for resampling
            if audio_data.dtype == np.int16:
                audio_float = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.float32:
                audio_float = audio_data
            else:
                audio_float = audio_data.astype(np.float32)

            # Handle stereo to mono
            if len(audio_float.shape) > 1:
                audio_float = audio_float.mean(axis=1)

            # Resample to 8kHz for Twilio
            if sample_rate != 8000:
                num_samples = int(len(audio_float) * 8000 / sample_rate)
                audio_float = scipy_resample(audio_float, num_samples)

            # Convert back to int16
            audio_int16 = (audio_float * 32767).astype(np.int16)
            pcm_bytes = audio_int16.tobytes()

            # Convert to μ-law if needed
            if self.use_mulaw:
                mulaw_bytes = audioop.lin2ulaw(pcm_bytes, 2)
                return mulaw_bytes
            else:
                return pcm_bytes

        except Exception as e:
            logger.error(f"[XTTS] Audio conversion error: {e}", exc_info=True)
            return None

    def get_synthesized_characters(self):
        return self.synthesized_chars

    def push(self, text):
        """Push text to internal queue for synthesis"""
        if text and text.strip():
            self.internal_queue.put_nowait({
                'data': text,
                'meta_info': {}
            })

    async def cleanup(self):
        """Clean up resources"""
        logger.info("[XTTS] Cleaned up")

    async def handle_interruption(self):
        """Handle user interruption"""
        self.clear_internal_queue()
        logger.info("[XTTS] Handling interruption - cleared queue")
