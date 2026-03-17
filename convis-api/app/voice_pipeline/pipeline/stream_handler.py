"""
Advanced Stream Handler for Convis
Bridges Twilio WebSocket messages to Voice Pipeline with real-time streaming
"""
import json
import base64
from typing import Dict, Any
from app.voice_pipeline.helpers.logger_config import configure_logger
from .voice_pipeline import VoicePipeline

logger = configure_logger(__name__)


class StreamProviderHandler:
    """
    Handles Twilio WebSocket messages and routes them through voice pipeline
    Provides high-performance real-time voice processing with WebSocket streaming
    """

    def __init__(self, websocket, assistant: Dict[str, Any], api_keys: Dict[str, str], db=None):
        """
        Initialize stream handler

        Args:
            websocket: Twilio WebSocket connection
            assistant: Assistant configuration from database
            api_keys: API keys for Deepgram, OpenAI, ElevenLabs, etc.
            db: Database connection for saving transcripts
        """
        self.websocket = websocket
        self.assistant = assistant
        self.api_keys = api_keys
        self.db = db
        self.pipeline = None
        self.stream_sid = None
        self.call_sid = None
        self.conversation_history = []

        logger.info(f"[STREAM_HANDLER] Initialized for assistant: {assistant.get('name', 'Unknown')}")

    async def start_pipeline(self):
        """Create and start the voice pipeline"""
        try:
            # Prepare assistant config for voice pipeline
            # Map database field names to pipeline config format
            assistant_config = {
                'assistant_name': self.assistant.get('name', 'Convis Assistant'),
                'greeting_message': self.assistant.get('call_greeting') or self.assistant.get('greeting_message') or self.assistant.get('greeting'),
                'system_message': self.assistant.get('system_message', 'You are a helpful AI assistant.'),
                # Noise suppression settings
                'noise_suppression_level': self.assistant.get('noise_suppression_level', 'medium'),
                'vad_threshold': self.assistant.get('vad_threshold', 0.5),
                'transcriber': {
                    'provider': self.assistant.get('asr_provider', 'deepgram'),
                    'model': self.assistant.get('asr_model', 'nova-2'),
                    'language': self.assistant.get('asr_language', 'en')
                },
                'llm': {
                    'provider': self.assistant.get('llm_provider', 'openai'),
                    'model': self.assistant.get('llm_model', 'gpt-4'),
                    'temperature': self.assistant.get('temperature', 0.7),
                    'max_tokens': self.assistant.get('llm_max_tokens', 150),
                    'system_prompt': self.assistant.get('system_message', 'You are a helpful AI assistant.')
                },
                'synthesizer': {
                    'provider': self.assistant.get('tts_provider', 'elevenlabs'),
                    'voice': self.assistant.get('tts_voice', 'default'),
                    'voice_id': self.assistant.get('tts_voice', None),  # Use tts_voice as voice_id
                    'model': self.assistant.get('tts_model', 'eleven_turbo_v2_5')
                }
            }

            # Create and start pipeline
            self.pipeline = VoicePipeline(
                assistant_config=assistant_config,
                api_keys=self.api_keys,
                twilio_ws=self.websocket,
                call_sid=self.call_sid,
                stream_sid=self.stream_sid,
                db=self.db,
                conversation_history=self.conversation_history
            )

            await self.pipeline.start()
            logger.info(f"[STREAM_HANDLER] ✅ Pipeline started for call {self.call_sid}")

        except Exception as e:
            logger.error(f"[STREAM_HANDLER] Failed to start pipeline: {e}", exc_info=True)
            raise

    async def handle_twilio_message(self, message: Dict[str, Any]):
        """
        Handle incoming Twilio WebSocket messages

        Args:
            message: Parsed JSON message from Twilio WebSocket
        """
        event = message.get('event')

        try:
            if event == 'start':
                await self._handle_start(message)

            elif event == 'media':
                await self._handle_media(message)

            elif event == 'stop':
                await self._handle_stop(message)

            elif event == 'mark':
                # Mark events are acknowledgments of audio playback
                await self._handle_mark(message)

            else:
                logger.debug(f"[STREAM_HANDLER] Unhandled event type: {event}")

        except Exception as e:
            logger.error(f"[STREAM_HANDLER] Error handling message: {e}", exc_info=True)

    async def _handle_start(self, message: Dict[str, Any]):
        """Handle Twilio stream start event"""
        start_data = message.get('start', {})
        self.stream_sid = start_data.get('streamSid')
        self.call_sid = start_data.get('callSid')
        custom_parameters = start_data.get('customParameters', {})

        logger.info(f"[STREAM_HANDLER] 📞 Stream started")
        logger.info(f"[STREAM_HANDLER] Call SID: {self.call_sid}")
        logger.info(f"[STREAM_HANDLER] Stream SID: {self.stream_sid}")
        logger.info(f"[STREAM_HANDLER] Media format: {start_data.get('mediaFormat', {})}")

        # Start the voice pipeline
        # (Greeting will be sent automatically if configured in assistant)
        await self.start_pipeline()

    async def _handle_media(self, message: Dict[str, Any]):
        """Handle incoming audio from Twilio"""
        if not self.pipeline or not self.pipeline.running:
            logger.warning("[STREAM_HANDLER] Received media but pipeline not running")
            return

        media_data = message.get('media', {})
        payload = media_data.get('payload')  # Base64 encoded μ-law audio

        if payload:
            # Decode base64 audio
            audio_bytes = base64.b64decode(payload)

            # Feed to voice pipeline (transcriber will handle it)
            await self.pipeline.feed_audio(audio_bytes)
        else:
            logger.warning("[STREAM_HANDLER] Received media event with no payload")

    async def _handle_mark(self, message: Dict[str, Any]):
        """
        Handle mark event from Twilio
        Mark events confirm that audio has been played to the user
        """
        if not self.pipeline:
            logger.warning("[STREAM_HANDLER] Received mark but pipeline not initialized")
            return

        mark_data = message.get('mark', {})
        mark_id = mark_data.get('name')

        if mark_id:
            # Process mark event through pipeline
            self.pipeline.process_mark_event(mark_id)
            logger.debug(f"[STREAM_HANDLER] Mark event processed: {mark_id}")
        else:
            logger.warning("[STREAM_HANDLER] Received mark event with no name")

    async def _handle_stop(self, message: Dict[str, Any]):
        """Handle Twilio stream stop event"""
        logger.info(f"[STREAM_HANDLER] ❌ Stream stopped for call {self.call_sid}")

        # Stop the pipeline
        if self.pipeline:
            await self.pipeline.stop()

        # Close WebSocket
        await self.websocket.close()

    async def run(self):
        """
        Main message loop for handling Twilio WebSocket messages
        Bolna-style: internal loop instead of external iteration
        """
        logger.info(f"[STREAM_HANDLER] Starting message loop")

        try:
            while True:
                try:
                    # Receive message from Twilio WebSocket
                    message_text = await self.websocket.receive_text()
                    message = json.loads(message_text)

                    # Handle the message
                    await self.handle_twilio_message(message)

                    # Check for stop event
                    if message.get('event') == 'stop':
                        break

                except Exception as e:
                    logger.error(f"[STREAM_HANDLER] Error in message loop: {e}", exc_info=True)
                    break

        except Exception as e:
            logger.error(f"[STREAM_HANDLER] Fatal error in run loop: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources"""
        logger.info(f"[STREAM_HANDLER] Cleaning up handler for call {self.call_sid}")

        if self.pipeline:
            await self.pipeline.stop()

        self.pipeline = None
