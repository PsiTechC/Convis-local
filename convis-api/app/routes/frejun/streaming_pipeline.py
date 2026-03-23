"""
VAPI-Style Streaming Pipeline for Ultra-Low Latency (Target: 600-900ms)

This module implements a fully streaming architecture similar to VAPI:
- Streaming ASR: Real-time speech-to-text with partial results
- Streaming LLM: Incremental response generation
- Streaming TTS: Sentence-by-sentence audio synthesis
- Parallel processing: Everything happens concurrently

Target Performance:
- Average latency: 600-900ms (matching VAPI)
- First response: <500ms
- 100% responses under 2 seconds
"""

import asyncio
import json
import logging
import re
import time
import base64
try:
    import audioop  # Python < 3.13
except ModuleNotFoundError:
    import audioop_lts as audioop  # Python 3.13+
from typing import Optional, Dict, Any, AsyncIterator
from datetime import datetime

logger = logging.getLogger(__name__)


class StreamingPipeline:
    """
    VAPI-style streaming pipeline that processes audio → text → LLM → TTS → audio
    with minimal latency through continuous streaming.
    """

    def __init__(
        self,
        asr_provider,
        llm_provider,
        tts_provider,
        websocket,
        platform: str = "frejun",
        stream_sid: Optional[str] = None,
        mark_handler=None
    ):
        self.asr_provider = asr_provider
        self.llm_provider = llm_provider
        self.tts_provider = tts_provider
        self.websocket = websocket
        self.platform = platform
        self.stream_sid = stream_sid
        self.mark_handler = mark_handler

        # Streaming state
        self.is_streaming = False
        self.current_transcript = ""
        self.partial_transcript = ""

        # Interruption handling - CRITICAL for natural conversation
        self.is_ai_speaking = False  # Track if AI is currently responding
        self.current_response_task = None  # Task handle for cancelling responses
        self.should_stop_response = False  # Flag to stop ongoing response

        # Performance tracking
        self.metrics = {
            'asr_latency': [],
            'llm_latency': [],
            'tts_latency': [],
            'total_latency': []
        }

        # Deepgram streaming connection
        self.deepgram_ws = None
        self.deepgram_task = None

        logger.info("[STREAMING] 🚀 Streaming pipeline initialized")

    async def start_streaming_asr(self):
        """
        Start Deepgram streaming WebSocket for real-time ASR.
        Processes 20ms audio chunks instantly without buffering.
        """
        if self.asr_provider.__class__.__name__ != 'DeepgramProvider':
            logger.warning("[STREAMING] ASR provider is not Deepgram, streaming may not be optimal")
            return

        try:
            logger.info("[STREAMING] 🎤 Starting Deepgram streaming WebSocket...")

            # Get Deepgram WebSocket URL (already implemented in DeepgramProvider)
            import websockets
            from urllib.parse import urlencode

            # Build streaming parameters for ultra-low latency
            # IMPORTANT: Twilio sends μ-law 8kHz, Deepgram accepts it natively!
            # Get language from ASR provider (supports ANY language configured by user)
            asr_language = getattr(self.asr_provider, 'language', 'en')

            dg_params = {
                'model': 'nova-2',  # Fastest Deepgram model
                'language': asr_language,  # Use configured language from ASR provider
                'encoding': 'mulaw',  # μ-law for Twilio (native format - no conversion!)
                'sample_rate': 8000,  # Twilio's sample rate
                'channels': 1,
                'interim_results': 'true',  # Get partial transcripts
                'endpointing': '150',  # 150ms silence detection (faster response)
                'vad_events': 'true',  # Voice activity detection
                'utterance_end_ms': '400',  # Finalize after 400ms silence (faster than 800ms)
                'punctuate': 'true',
                'smart_format': 'true'
            }

            logger.info(f"[STREAMING] 🌍 Deepgram language: {asr_language}")

            deepgram_api_key = self.asr_provider.api_key
            websocket_url = f"wss://api.deepgram.com/v1/listen?{urlencode(dg_params)}"

            self.deepgram_ws = await websockets.connect(
                websocket_url,
                extra_headers={'Authorization': f'Token {deepgram_api_key}'}
            )

            logger.info("[STREAMING] ✅ Deepgram WebSocket connected")

            # Start background task to receive transcripts
            self.deepgram_task = asyncio.create_task(self._receive_deepgram_transcripts())

        except Exception as e:
            logger.error(f"[STREAMING] ❌ Failed to start Deepgram streaming: {e}", exc_info=True)

    async def _receive_deepgram_transcripts(self):
        """
        Background task to receive streaming transcripts from Deepgram.
        Processes partial and final results in real-time.
        """
        try:
            async for message in self.deepgram_ws:
                data = json.loads(message)

                if data.get('type') == 'Results':
                    channel = data.get('channel', {})
                    alternatives = channel.get('alternatives', [])

                    if alternatives:
                        transcript = alternatives[0].get('transcript', '')
                        is_final = channel.get('is_final', False)

                        if transcript:
                            if is_final:
                                # Final transcript - trigger LLM response
                                logger.info(f"[STREAMING] 🎤 Final transcript: \"{transcript}\"")
                                self.current_transcript = transcript

                                # Trigger streaming LLM response and track the task
                                self.current_response_task = asyncio.create_task(
                                    self._process_streaming_response(transcript)
                                )
                            else:
                                # Partial transcript - just log for monitoring
                                self.partial_transcript = transcript
                                logger.debug(f"[STREAMING] 🎤 Partial: \"{transcript}\"")

                elif data.get('type') == 'SpeechStarted':
                    logger.info("[STREAMING] 🎤 Speech detected - listening...")

                    # CRITICAL: Interrupt AI if it's speaking (user is talking over AI)
                    if self.is_ai_speaking:
                        logger.warning("[STREAMING] ⚠️ USER INTERRUPTED AI - Stopping response immediately!")
                        await self._stop_current_response()

                elif data.get('type') == 'UtteranceEnd':
                    logger.info("[STREAMING] 🎤 Utterance ended")

        except Exception as e:
            logger.error(f"[STREAMING] Error receiving Deepgram transcripts: {e}", exc_info=True)

    async def stream_audio_to_asr(self, audio_chunk: bytes):
        """
        Stream audio chunk to Deepgram WebSocket (no buffering).

        This is called for every 20ms audio chunk from Twilio/FreJun.
        No buffering = minimal latency!
        """
        if self.deepgram_ws and self.deepgram_ws.open:
            try:
                await self.deepgram_ws.send(audio_chunk)
            except Exception as e:
                logger.error(f"[STREAMING] Error sending audio to Deepgram: {e}")

    async def _process_streaming_response(self, user_message: str):
        """
        Process user message with streaming LLM and TTS.

        Flow:
        1. Send message to LLM with streaming enabled
        2. As LLM generates text, detect complete sentences
        3. Immediately synthesize and send each sentence
        4. Result: User hears first words in 200-400ms!
        """
        pipeline_start = time.time()

        try:
            # Mark AI as speaking - CRITICAL for interruption detection
            self.is_ai_speaking = True
            self.should_stop_response = False

            logger.info(f"[STREAMING] 🤖 Processing: \"{user_message}\"")

            # Track metrics
            llm_start = time.time()
            first_word_time = None
            sentences_sent = 0

            # Buffer for accumulating text until we have a complete sentence
            text_buffer = ""

            # Stream LLM response
            async for chunk in self._stream_llm_response(user_message):
                # Check for interruption BEFORE processing each chunk
                if self.should_stop_response:
                    logger.warning("[STREAMING] 🛑 Response interrupted - stopping immediately")
                    break

                if not first_word_time:
                    first_word_time = time.time()
                    llm_latency = (first_word_time - llm_start) * 1000
                    self.metrics['llm_latency'].append(llm_latency)
                    logger.info(f"[STREAMING] ⚡ First LLM token in {llm_latency:.0f}ms")

                text_buffer += chunk

                # Check if we have complete sentence(s)
                sentences = self._extract_complete_sentences(text_buffer)

                for sentence in sentences:
                    # Check for interruption before each sentence
                    if self.should_stop_response:
                        logger.warning("[STREAMING] 🛑 Sentence interrupted - stopping")
                        break

                    if sentence.strip():
                        # Synthesize and send this sentence immediately
                        tts_start = time.time()

                        audio = await self._synthesize_sentence(sentence)

                        if audio:
                            await self._send_audio(audio)
                            sentences_sent += 1

                            tts_latency = (time.time() - tts_start) * 1000
                            self.metrics['tts_latency'].append(tts_latency)

                            logger.info(f"[STREAMING] 🔊 Sentence {sentences_sent} sent in {tts_latency:.0f}ms: \"{sentence[:50]}...\"")

                        # Remove sent sentence from buffer
                        text_buffer = text_buffer.replace(sentence, "", 1)

            # Send any remaining text (only if not interrupted)
            if not self.should_stop_response and text_buffer.strip():
                logger.info(f"[STREAMING] 🔊 Sending final fragment: \"{text_buffer}\"")
                audio = await self._synthesize_sentence(text_buffer)
                if audio:
                    await self._send_audio(audio)

            # Calculate total pipeline latency
            total_latency = (time.time() - pipeline_start) * 1000
            self.metrics['total_latency'].append(total_latency)

            if self.should_stop_response:
                logger.info(f"[STREAMING] ⚠️ Response interrupted after {total_latency:.0f}ms ({sentences_sent} sentences sent)")
            else:
                logger.info(f"[STREAMING] ✅ Response complete - Total latency: {total_latency:.0f}ms, Sentences: {sentences_sent}")

            # Log performance metrics
            if self.metrics['llm_latency']:
                avg_llm = sum(self.metrics['llm_latency'][-10:]) / min(len(self.metrics['llm_latency']), 10)
                avg_tts = sum(self.metrics['tts_latency'][-10:]) / min(len(self.metrics['tts_latency']), 10) if self.metrics['tts_latency'] else 0
                logger.info(f"[STREAMING] 📊 Avg latencies (last 10): LLM={avg_llm:.0f}ms, TTS={avg_tts:.0f}ms")

        except asyncio.CancelledError:
            logger.warning("[STREAMING] ⚠️ Response task cancelled (interrupted)")
            raise
        except Exception as e:
            logger.error(f"[STREAMING] Error processing streaming response: {e}", exc_info=True)
        finally:
            # ALWAYS reset AI speaking state when done
            self.is_ai_speaking = False
            self.should_stop_response = False

    async def _stream_llm_response(self, user_message: str) -> AsyncIterator[str]:
        """
        Stream LLM response chunks in real-time.
        Yields text chunks as the LLM generates them.
        """
        try:
            # Check if LLM provider supports streaming
            if hasattr(self.llm_provider, 'stream_chat'):
                # Use provider's streaming method
                async for chunk in self.llm_provider.stream_chat(user_message):
                    yield chunk

            elif hasattr(self.llm_provider, 'client'):
                # Use OpenAI client directly with streaming
                from openai import AsyncOpenAI

                client = self.llm_provider.client
                if not isinstance(client, AsyncOpenAI):
                    client = AsyncOpenAI(api_key=self.llm_provider.api_key)

                stream = await client.chat.completions.create(
                    model=self.llm_provider.model or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": self.llm_provider.system_message or "You are a helpful assistant."},
                        {"role": "user", "content": user_message}
                    ],
                    stream=True,
                    max_tokens=150,
                    temperature=0.8
                )

                async for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

            else:
                # Fallback: get full response (not streaming)
                logger.warning("[STREAMING] LLM provider doesn't support streaming, using batch mode")
                response = await self.llm_provider.generate(user_message)
                yield response

        except Exception as e:
            logger.error(f"[STREAMING] Error streaming LLM response: {e}", exc_info=True)
            yield "I apologize, I'm having trouble processing your request right now."

    def _extract_complete_sentences(self, text: str) -> list:
        """
        Extract complete sentences from text buffer.
        Looks for sentence-ending punctuation: . ! ?

        Returns list of complete sentences.
        """
        # Match sentences ending with . ! ? followed by space or end of string
        pattern = r'([^.!?]+[.!?]+(?:\s|$))'
        matches = re.findall(pattern, text)
        return matches

    async def _synthesize_sentence(self, text: str) -> Optional[bytes]:
        """
        Synthesize a single sentence to audio.
        Returns raw audio bytes ready to send.
        """
        try:
            tts_start = time.time()

            # Use TTS provider to synthesize
            audio = await self.tts_provider.synthesize(text)

            if not audio:
                logger.warning(f"[STREAMING] TTS returned no audio for: \"{text[:50]}...\"")
                return None

            tts_time = (time.time() - tts_start) * 1000
            logger.debug(f"[STREAMING] 🔊 TTS synthesized {len(audio)} bytes in {tts_time:.0f}ms")

            # Convert audio format if needed
            audio = await self._convert_audio(audio)

            return audio

        except Exception as e:
            logger.error(f"[STREAMING] Error synthesizing sentence: {e}", exc_info=True)
            return None

    async def _convert_audio(self, audio: bytes) -> bytes:
        """
        Convert audio to platform-specific format.
        - FreJun: PCM 8kHz
        - Twilio: μ-law 8kHz
        """
        try:
            # Determine input format based on TTS provider
            tts_provider_name = self.tts_provider.__class__.__name__.lower()

            if 'elevenlabs' in tts_provider_name:
                input_rate = 16000
            elif 'openai' in tts_provider_name:
                input_rate = 24000
            elif 'sarvam' in tts_provider_name:
                # Sarvam returns WAV, extract PCM
                from app.voice_pipeline.helpers.utils import wav_bytes_to_pcm
                audio = wav_bytes_to_pcm(audio)
                input_rate = 8000
            else:  # Cartesia
                input_rate = 8000

            # Resample to 8kHz if needed
            if input_rate != 8000:
                audio, _ = audioop.ratecv(audio, 2, 1, input_rate, 8000, None)

            # Encode to μ-law for Twilio
            if self.platform == "twilio":
                audio = audioop.lin2ulaw(audio, 2)

            return audio

        except Exception as e:
            logger.error(f"[STREAMING] Error converting audio: {e}", exc_info=True)
            return audio  # Return original if conversion fails

    async def _send_audio(self, audio: bytes):
        """
        Send audio chunk to client.
        Platform-specific formatting.
        """
        try:
            if self.platform == "frejun":
                # FreJun format: base64 encoded
                audio_b64 = base64.b64encode(audio).decode('utf-8')
                await self.websocket.send_json({
                    "type": "audio",
                    "audio_b64": audio_b64
                })

            elif self.platform == "twilio":
                # Twilio format: media event with marks
                if self.mark_handler and self.stream_sid:
                    await self.mark_handler.send_audio_with_marks(
                        audio,
                        text="",  # Text already logged
                        is_final=False
                    )
                else:
                    logger.warning("[STREAMING] Cannot send audio: missing stream_sid or mark_handler")

        except Exception as e:
            logger.error(f"[STREAMING] Error sending audio: {e}", exc_info=True)

    async def _stop_current_response(self):
        """
        Stop the current AI response immediately (interruption handling).

        This is called when user starts speaking while AI is responding.
        CRITICAL for natural, human-like conversation flow.
        """
        try:
            logger.info("[STREAMING] 🛑 Stopping current response...")

            # Set the stop flag (checked in _process_streaming_response)
            self.should_stop_response = True

            # Cancel the response task if it's running
            if self.current_response_task and not self.current_response_task.done():
                self.current_response_task.cancel()
                try:
                    await self.current_response_task
                except asyncio.CancelledError:
                    pass  # Expected when cancelling

            # Reset AI speaking state
            self.is_ai_speaking = False

            logger.info("[STREAMING] ✅ Response stopped successfully")

        except Exception as e:
            logger.error(f"[STREAMING] Error stopping response: {e}", exc_info=True)

    async def close(self):
        """Clean up streaming connections"""
        try:
            if self.deepgram_task:
                self.deepgram_task.cancel()

            if self.deepgram_ws:
                await self.deepgram_ws.close()

            logger.info("[STREAMING] 🛑 Streaming pipeline closed")

        except Exception as e:
            logger.error(f"[STREAMING] Error closing pipeline: {e}")

    def get_performance_summary(self) -> Dict[str, float]:
        """Get average performance metrics"""
        return {
            'avg_llm_latency_ms': sum(self.metrics['llm_latency']) / len(self.metrics['llm_latency']) if self.metrics['llm_latency'] else 0,
            'avg_tts_latency_ms': sum(self.metrics['tts_latency']) / len(self.metrics['tts_latency']) if self.metrics['tts_latency'] else 0,
            'avg_total_latency_ms': sum(self.metrics['total_latency']) / len(self.metrics['total_latency']) if self.metrics['total_latency'] else 0,
            'responses_count': len(self.metrics['total_latency'])
        }
