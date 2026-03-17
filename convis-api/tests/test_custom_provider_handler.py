"""
Unit tests for Custom Provider Handler
Tests all ASR, LLM, and TTS provider integrations
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json
import base64

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.custom_provider_handler import CustomProviderHandler


def create_mock_httpx_client(response_data, status_code=200, content=None):
    """Helper to create properly mocked httpx.AsyncClient"""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json = MagicMock(return_value=response_data)
    if content:
        mock_response.content = content

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

    return mock_client


class TestCustomProviderHandler:
    """Test suite for CustomProviderHandler"""

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket"""
        ws = AsyncMock()
        ws.send = AsyncMock()
        return ws

    @pytest.fixture
    def assistant_config(self):
        """Base assistant configuration"""
        return {
            'system_message': 'You are a helpful assistant',
            'call_greeting': 'Hello!',
            'temperature': 0.8,
            'asr_provider': 'deepgram',
            'asr_model': 'nova-3',
            'asr_language': 'en',
            'llm_provider': 'openai',
            'llm_model': 'gpt-4o-mini',
            'llm_max_tokens': 150,
            'tts_provider': 'sarvam',
            'tts_model': 'bulbul:v2',
            'tts_voice': 'Manisha',
            'tts_speed': 1.0
        }

    @pytest.fixture
    def api_keys(self):
        """Mock API keys"""
        return {
            'openai': 'test-openai-key',
            'deepgram': 'test-deepgram-key',
            'sarvam': 'test-sarvam-key',
            'azure': 'test-azure-key',
            'assembly': 'test-assembly-key',
            'google': 'test-google-key',
            'cartesia': 'test-cartesia-key',
            'elevenlabs': 'test-elevenlabs-key',
            'anthropic': 'test-anthropic-key',
            'deepseek': 'test-deepseek-key',
            'openrouter': 'test-openrouter-key',
            'groq': 'test-groq-key'
        }

    @pytest.fixture
    def handler(self, mock_websocket, assistant_config, api_keys):
        """Create handler instance"""
        return CustomProviderHandler(mock_websocket, assistant_config, api_keys)

    # ==================== ASR Provider Tests ====================

    def test_asr_provider_routing(self, handler):
        """Test ASR provider routing logic"""
        # Test that handler initializes with correct provider
        assert handler.asr_provider == 'deepgram'
        assert handler.asr_model == 'nova-3'
        assert handler.asr_language == 'en'

    @pytest.mark.asyncio
    async def test_transcribe_deepgram_success(self, handler):
        """Test Deepgram transcription success"""
        mock_response = {
            'results': {
                'channels': [{
                    'alternatives': [{
                        'transcript': 'Hello world'
                    }]
                }]
            }
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.transcribe_deepgram(b'test_audio_data')
            assert result == 'Hello world'

    @pytest.mark.asyncio
    async def test_transcribe_openai_whisper_success(self, handler):
        """Test OpenAI Whisper transcription success"""
        mock_response = {
            'text': 'Hello from whisper'
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.transcribe_openai(b'test_audio_data')
            assert result == 'Hello from whisper'

    @pytest.mark.asyncio
    async def test_transcribe_azure_success(self, handler):
        """Test Azure Speech Services transcription success"""
        mock_response = {
            'DisplayText': 'Azure transcription'
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.transcribe_azure(b'test_audio_data')
            assert result == 'Azure transcription'

    @pytest.mark.asyncio
    async def test_transcribe_sarvam_success(self, handler):
        """Test Sarvam AI transcription success"""
        mock_response = {
            'transcript': 'Sarvam transcription'
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.transcribe_sarvam(b'test_audio_data')
            assert result == 'Sarvam transcription'

    @pytest.mark.asyncio
    async def test_transcribe_google_success(self, handler):
        """Test Google Speech-to-Text success"""
        mock_response = {
            'results': [{
                'alternatives': [{
                    'transcript': 'Google transcription'
                }]
            }]
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.transcribe_google(b'test_audio_data')
            assert result == 'Google transcription'

    @pytest.mark.asyncio
    async def test_transcribe_no_api_key(self, mock_websocket, assistant_config):
        """Test ASR without API key"""
        handler = CustomProviderHandler(mock_websocket, assistant_config, {})
        result = await handler.transcribe_deepgram(b'test_audio_data')
        assert result is None

    # ==================== LLM Provider Tests ====================

    def test_llm_provider_routing(self, handler):
        """Test LLM provider routing logic"""
        assert handler.llm_provider == 'openai'
        assert handler.llm_model == 'gpt-4o-mini'
        assert handler.llm_max_tokens == 150

    @pytest.mark.asyncio
    async def test_generate_openai_response_success(self, handler):
        """Test OpenAI LLM response generation"""
        mock_response = {
            'choices': [{
                'message': {
                    'content': 'OpenAI response'
                }
            }]
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.generate_openai_response()
            assert result == 'OpenAI response'

    @pytest.mark.asyncio
    async def test_generate_anthropic_response_success(self, handler):
        """Test Anthropic Claude response generation"""
        handler.llm_provider = 'anthropic'
        mock_response = {
            'content': [{
                'text': 'Claude response'
            }]
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.generate_anthropic_response()
            assert result == 'Claude response'

    @pytest.mark.asyncio
    async def test_generate_deepseek_response_success(self, handler):
        """Test Deepseek response generation"""
        mock_response = {
            'choices': [{
                'message': {
                    'content': 'Deepseek response'
                }
            }]
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.generate_deepseek_response()
            assert result == 'Deepseek response'

    @pytest.mark.asyncio
    async def test_generate_groq_response_success(self, handler):
        """Test Groq response generation"""
        mock_response = {
            'choices': [{
                'message': {
                    'content': 'Groq response'
                }
            }]
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.generate_groq_response()
            assert result == 'Groq response'

    # ==================== TTS Provider Tests ====================

    def test_tts_provider_routing(self, handler):
        """Test TTS provider routing logic"""
        assert handler.tts_provider == 'sarvam'
        assert handler.tts_model == 'bulbul:v2'
        assert handler.tts_voice == 'Manisha'

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires real audio data for resampling - manual test needed")
    async def test_synthesize_openai_success(self, handler):
        """Test OpenAI TTS synthesis"""
        mock_audio = b'openai_audio_data'

        mock_client = create_mock_httpx_client({}, content=mock_audio)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.synthesize_openai('Test text')
            assert result == mock_audio

    @pytest.mark.asyncio
    async def test_synthesize_cartesia_success(self, handler):
        """Test Cartesia TTS synthesis"""
        mock_audio = b'cartesia_audio_data'

        mock_client = create_mock_httpx_client({}, content=mock_audio)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.synthesize_cartesia('Test text')
            assert result == mock_audio

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires real audio data for mu-law encoding - manual test needed")
    async def test_synthesize_sarvam_success(self, handler):
        """Test Sarvam TTS synthesis"""
        mock_audio_base64 = base64.b64encode(b'sarvam_audio').decode('utf-8')
        mock_response = {
            'audios': [mock_audio_base64]
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.synthesize_sarvam('Test text')
            assert result == b'sarvam_audio'

    @pytest.mark.asyncio
    async def test_synthesize_azuretts_success(self, handler):
        """Test Azure TTS synthesis"""
        mock_audio = b'azure_audio_data'

        mock_client = create_mock_httpx_client({}, content=mock_audio)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.synthesize_azuretts('Test text')
            assert result == mock_audio

    @pytest.mark.asyncio
    async def test_synthesize_elevenlabs_success(self, handler):
        """Test ElevenLabs TTS synthesis"""
        mock_audio = b'elevenlabs_audio_data'

        mock_client = create_mock_httpx_client({}, content=mock_audio)
        with patch('httpx.AsyncClient', mock_client):
            result = await handler.synthesize_elevenlabs('Test text')
            assert result == mock_audio

    # ==================== Integration Tests ====================

    @pytest.mark.asyncio
    async def test_handle_start_event(self, handler):
        """Test handling call start event"""
        start_message = {
            'event': 'start',
            'start': {
                'streamSid': 'test-stream-sid',
                'callSid': 'test-call-sid'
            }
        }

        with patch.object(handler, 'synthesize_and_send', new_callable=AsyncMock) as mock_synth:
            await handler.handle_start(start_message)

            assert handler.stream_sid == 'test-stream-sid'
            assert handler.call_sid == 'test-call-sid'
            mock_synth.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_media_event(self, handler):
        """Test handling media event"""
        audio_payload = base64.b64encode(b'test_audio').decode('utf-8')
        media_message = {
            'event': 'media',
            'media': {
                'payload': audio_payload
            }
        }

        await handler.handle_media(media_message)

        # Check that audio buffer was populated
        assert len(handler.audio_buffer) > 0

    @pytest.mark.asyncio
    async def test_process_audio_buffer_pipeline(self, handler):
        """Test complete pipeline: ASR -> LLM -> TTS"""
        handler.stream_sid = 'test-stream-sid'
        handler.audio_buffer = b'test_audio_data'

        # Mock all pipeline steps
        with patch.object(handler, 'transcribe_audio', new_callable=AsyncMock) as mock_asr, \
             patch.object(handler, 'generate_llm_response', new_callable=AsyncMock) as mock_llm, \
             patch.object(handler, 'synthesize_and_send', new_callable=AsyncMock) as mock_tts:

            mock_asr.return_value = 'Hello'
            mock_llm.return_value = 'Hi there!'

            await handler.process_audio_buffer()

            mock_asr.assert_called_once()
            mock_llm.assert_called_once_with('Hello')
            mock_tts.assert_called_once_with('Hi there!')

    @pytest.mark.asyncio
    async def test_conversation_history_tracking(self, handler):
        """Test that conversation history is maintained"""
        initial_length = len(handler.conversation_history)

        mock_response = {
            'choices': [{
                'message': {
                    'content': 'Response'
                }
            }]
        }

        mock_client = create_mock_httpx_client(mock_response)
        with patch('httpx.AsyncClient', mock_client):
            await handler.generate_llm_response('User message')

        # Should have user message + assistant response
        assert len(handler.conversation_history) == initial_length + 2
        assert handler.conversation_history[-2]['role'] == 'user'
        assert handler.conversation_history[-1]['role'] == 'assistant'

    @pytest.mark.asyncio
    async def test_send_audio_to_twilio(self, handler):
        """Test sending audio to Twilio"""
        handler.stream_sid = 'test-stream-sid'
        test_audio = b'test_audio_data'

        await handler.send_audio_to_twilio(test_audio)

        # Verify WebSocket send was called
        assert handler.twilio_ws.send.called

    # ==================== Error Handling Tests ====================

    @pytest.mark.asyncio
    async def test_transcribe_with_error(self, handler):
        """Test ASR error handling"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_post = AsyncMock()
            mock_post.return_value.status_code = 500
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await handler.transcribe_deepgram(b'test_audio')
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_with_error(self, handler):
        """Test LLM error handling"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_post = AsyncMock()
            mock_post.return_value.status_code = 500
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await handler.generate_openai_response()
            assert result is None

    @pytest.mark.asyncio
    async def test_tts_with_error(self, handler):
        """Test TTS error handling"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_post = AsyncMock()
            mock_post.return_value.status_code = 500
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await handler.synthesize_openai('Test')
            assert result is None

    @pytest.mark.asyncio
    async def test_unsupported_asr_provider(self, mock_websocket, assistant_config, api_keys):
        """Test unsupported ASR provider"""
        assistant_config['asr_provider'] = 'unsupported_provider'
        handler = CustomProviderHandler(mock_websocket, assistant_config, api_keys)

        result = await handler.transcribe_audio(b'test_audio')
        assert result is None

    @pytest.mark.asyncio
    async def test_unsupported_tts_provider(self, mock_websocket, assistant_config, api_keys):
        """Test unsupported TTS provider"""
        assistant_config['tts_provider'] = 'unsupported_provider'
        handler = CustomProviderHandler(mock_websocket, assistant_config, api_keys)

        with patch.object(handler, 'send_audio_to_twilio', new_callable=AsyncMock):
            await handler.synthesize_and_send('Test')
            # Should not crash, just log error


class TestVADIntegration:
    """Test VAD integration with CustomProviderHandler"""

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket"""
        ws = AsyncMock()
        ws.send = AsyncMock()
        return ws

    @pytest.fixture
    def assistant_config_with_vad(self):
        """Assistant configuration with VAD enabled"""
        return {
            'system_message': 'You are a helpful assistant',
            'call_greeting': 'Hello!',
            'temperature': 0.8,
            'asr_provider': 'deepgram',
            'asr_model': 'nova-3',
            'asr_language': 'en',
            'llm_provider': 'openai',
            'llm_model': 'gpt-4o-mini',
            'llm_max_tokens': 150,
            'tts_provider': 'openai',
            'tts_model': 'tts-1',
            'tts_voice': 'alloy',
            'use_vad': True,
            'vad_threshold': 0.5,
            'vad_min_speech_ms': 250,
            'vad_min_silence_ms': 300
        }

    @pytest.fixture
    def assistant_config_without_vad(self):
        """Assistant configuration with VAD disabled"""
        return {
            'system_message': 'You are a helpful assistant',
            'call_greeting': 'Hello!',
            'temperature': 0.8,
            'asr_provider': 'deepgram',
            'asr_model': 'nova-3',
            'asr_language': 'en',
            'llm_provider': 'openai',
            'llm_model': 'gpt-4o-mini',
            'llm_max_tokens': 150,
            'tts_provider': 'openai',
            'tts_model': 'tts-1',
            'tts_voice': 'alloy',
            'use_vad': False
        }

    @pytest.fixture
    def api_keys(self):
        """Mock API keys"""
        return {
            'openai': 'test-openai-key',
            'deepgram': 'test-deepgram-key'
        }

    def test_vad_enabled_when_configured(self, mock_websocket, assistant_config_with_vad, api_keys):
        """Test VAD is enabled when configured"""
        with patch('app.utils.custom_provider_handler.SILERO_VAD_AVAILABLE', True), \
             patch('app.utils.custom_provider_handler.SileroVADProcessor') as MockVAD:
            mock_vad_instance = MagicMock()
            MockVAD.return_value = mock_vad_instance

            handler = CustomProviderHandler(mock_websocket, assistant_config_with_vad, api_keys)

            assert handler.use_vad == True
            assert handler.vad_processor == mock_vad_instance
            MockVAD.assert_called_once_with(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=300
            )

    def test_vad_disabled_when_not_configured(self, mock_websocket, assistant_config_without_vad, api_keys):
        """Test VAD is disabled when not configured"""
        handler = CustomProviderHandler(mock_websocket, assistant_config_without_vad, api_keys)

        assert handler.use_vad == False
        assert handler.vad_processor is None

    def test_vad_disabled_when_not_available(self, mock_websocket, assistant_config_with_vad, api_keys):
        """Test VAD is disabled when library not available"""
        with patch('app.utils.custom_provider_handler.SILERO_VAD_AVAILABLE', False):
            handler = CustomProviderHandler(mock_websocket, assistant_config_with_vad, api_keys)

            assert handler.use_vad == False
            assert handler.vad_processor is None

    @pytest.mark.asyncio
    async def test_handle_media_uses_vad(self, mock_websocket, assistant_config_with_vad, api_keys):
        """Test that handle_media uses VAD when enabled"""
        with patch('app.utils.custom_provider_handler.SILERO_VAD_AVAILABLE', True), \
             patch('app.utils.custom_provider_handler.SileroVADProcessor') as MockVAD:
            mock_vad_instance = MagicMock()
            mock_vad_instance.process_chunk.return_value = (True, 0.7)
            mock_vad_instance.is_speech_ended.return_value = False
            MockVAD.return_value = mock_vad_instance

            handler = CustomProviderHandler(mock_websocket, assistant_config_with_vad, api_keys)

            # Process media
            audio_payload = base64.b64encode(b'test_audio').decode('utf-8')
            media_message = {
                'event': 'media',
                'media': {'payload': audio_payload}
            }

            await handler.handle_media(media_message)

            # VAD should have been called
            mock_vad_instance.process_chunk.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_media_uses_time_based_when_vad_disabled(
        self, mock_websocket, assistant_config_without_vad, api_keys
    ):
        """Test that handle_media uses time-based buffering when VAD disabled"""
        handler = CustomProviderHandler(mock_websocket, assistant_config_without_vad, api_keys)

        with patch.object(handler, '_handle_media_time_based', new_callable=AsyncMock) as mock_time_based, \
             patch.object(handler, '_handle_media_with_vad', new_callable=AsyncMock) as mock_vad:
            # Process media
            audio_payload = base64.b64encode(b'test_audio').decode('utf-8')
            media_message = {
                'event': 'media',
                'media': {'payload': audio_payload}
            }

            await handler.handle_media(media_message)

            # Time-based should be called, not VAD
            mock_time_based.assert_called_once()
            mock_vad.assert_not_called()

    @pytest.mark.asyncio
    async def test_vad_triggers_processing_on_speech_end(
        self, mock_websocket, assistant_config_with_vad, api_keys
    ):
        """Test that processing is triggered when VAD detects speech end"""
        with patch('app.utils.custom_provider_handler.SILERO_VAD_AVAILABLE', True), \
             patch('app.utils.custom_provider_handler.SileroVADProcessor') as MockVAD:
            mock_vad_instance = MagicMock()
            mock_vad_instance.process_chunk.return_value = (False, 0.1)
            mock_vad_instance.is_speech_ended.return_value = True
            mock_vad_instance.get_speech_duration_ms.return_value = 500
            MockVAD.return_value = mock_vad_instance

            handler = CustomProviderHandler(mock_websocket, assistant_config_with_vad, api_keys)
            handler.audio_buffer = b'x' * 5000  # Enough audio

            with patch.object(handler, 'process_audio_buffer', new_callable=AsyncMock) as mock_process:
                await handler._handle_media_with_vad(b'audio_chunk')

                # Processing should be triggered
                mock_process.assert_called_once()
                # VAD should be reset
                mock_vad_instance.reset.assert_called()

    @pytest.mark.asyncio
    async def test_vad_emergency_flush(self, mock_websocket, assistant_config_with_vad, api_keys):
        """Test emergency buffer flush at 32KB limit"""
        with patch('app.utils.custom_provider_handler.SILERO_VAD_AVAILABLE', True), \
             patch('app.utils.custom_provider_handler.SileroVADProcessor') as MockVAD:
            mock_vad_instance = MagicMock()
            mock_vad_instance.process_chunk.return_value = (True, 0.8)  # Still speaking
            mock_vad_instance.is_speech_ended.return_value = False
            MockVAD.return_value = mock_vad_instance

            handler = CustomProviderHandler(mock_websocket, assistant_config_with_vad, api_keys)
            handler.audio_buffer = b'x' * 33000  # Over 32KB limit

            with patch.object(handler, 'process_audio_buffer', new_callable=AsyncMock) as mock_process:
                await handler._handle_media_with_vad(b'audio_chunk')

                # Emergency flush should be triggered
                mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_vad_reset_on_call_start(self, mock_websocket, assistant_config_with_vad, api_keys):
        """Test VAD state is reset on call start"""
        with patch('app.utils.custom_provider_handler.SILERO_VAD_AVAILABLE', True), \
             patch('app.utils.custom_provider_handler.SileroVADProcessor') as MockVAD:
            mock_vad_instance = MagicMock()
            MockVAD.return_value = mock_vad_instance

            handler = CustomProviderHandler(mock_websocket, assistant_config_with_vad, api_keys)

            with patch.object(handler, 'synthesize_and_send', new_callable=AsyncMock):
                start_message = {
                    'event': 'start',
                    'start': {
                        'streamSid': 'test-stream-sid',
                        'callSid': 'test-call-sid'
                    }
                }

                await handler.handle_start(start_message)

                # VAD should be reset for new call
                mock_vad_instance.reset.assert_called_once()

    def test_vad_configuration_parameters(self, mock_websocket, api_keys):
        """Test custom VAD configuration parameters"""
        config = {
            'system_message': 'Test',
            'use_vad': True,
            'vad_threshold': 0.7,
            'vad_min_speech_ms': 400,
            'vad_min_silence_ms': 500
        }

        with patch('app.utils.custom_provider_handler.SILERO_VAD_AVAILABLE', True), \
             patch('app.utils.custom_provider_handler.SileroVADProcessor') as MockVAD:
            mock_vad_instance = MagicMock()
            MockVAD.return_value = mock_vad_instance

            handler = CustomProviderHandler(mock_websocket, config, api_keys)

            MockVAD.assert_called_once_with(
                threshold=0.7,
                min_speech_duration_ms=400,
                min_silence_duration_ms=500
            )


class TestDeepgramKeywordBoosting:
    """Test suite for Deepgram ASR keyword boosting"""

    def test_deepgram_asr_default_keywords(self):
        """Test Deepgram ASR has default email keywords"""
        from app.providers.asr import DeepgramASR

        # DeepgramASR should have default keywords
        assert hasattr(DeepgramASR, 'DEFAULT_KEYWORDS')
        default_kw = DeepgramASR.DEFAULT_KEYWORDS

        # Verify essential email keywords are present
        assert any('gmail' in kw.lower() for kw in default_kw)
        assert any('yahoo' in kw.lower() for kw in default_kw)
        assert any('outlook' in kw.lower() for kw in default_kw)
        assert any('@' in kw for kw in default_kw)
        assert any('dot com' in kw.lower() for kw in default_kw)
        assert any('at the rate' in kw.lower() for kw in default_kw)
        print("✅ Test Passed: Deepgram ASR has default email keywords")

    def test_deepgram_asr_keyword_format(self):
        """Test Deepgram keywords have boost weights"""
        from app.providers.asr import DeepgramASR

        for kw in DeepgramASR.DEFAULT_KEYWORDS:
            assert ':' in kw, f"Keyword '{kw}' should have boost weight"
            parts = kw.split(':')
            assert len(parts) == 2, f"Keyword '{kw}' should have exactly one colon"
            assert parts[1].isdigit(), f"Boost weight for '{kw}' should be numeric"
        print("✅ Test Passed: Deepgram keywords have correct format with boost weights")

    def test_provider_factory_passes_keywords(self):
        """Test ProviderFactory passes keywords to Deepgram"""
        from app.providers.factory import ProviderFactory

        # Test with custom keywords - patch at factory level to avoid SDK import
        with patch.object(ProviderFactory, 'ASR_PROVIDERS') as mock_providers:
            mock_deepgram_class = Mock()
            mock_instance = Mock()
            mock_deepgram_class.return_value = mock_instance
            mock_providers.__getitem__ = Mock(return_value=mock_deepgram_class)
            mock_providers.__contains__ = Mock(return_value=True)
            mock_providers.keys = Mock(return_value=['deepgram', 'openai'])

            ProviderFactory.create_asr_provider(
                provider_name='deepgram',
                api_key='test_key',
                model='nova-2',
                language='en',
                keywords='custom:100,email:80'
            )

            # Verify the class was called with keywords
            mock_deepgram_class.assert_called_once()
            call_kwargs = mock_deepgram_class.call_args.kwargs
            assert 'keywords' in call_kwargs
            assert call_kwargs['keywords'] == 'custom:100,email:80'
        print("✅ Test Passed: ProviderFactory passes keywords to Deepgram")

    def test_handler_builds_keywords_for_deepgram(self):
        """Test CustomProviderStreamHandler builds keywords for Deepgram"""
        from app.services.call_handlers.custom_provider_stream import CustomProviderStreamHandler

        config = {
            'user_id': 'test_user',
            'assistant_id': 'test_assistant',
            'system_message': 'Test',
            'asr_provider': 'deepgram',
            'asr_keywords': ['Bruce:100', 'CompanyName:80']
        }

        handler = CustomProviderStreamHandler(
            websocket=Mock(),
            assistant_config=config,
            openai_api_key='test_key',
            call_id='test_call'
        )

        assert handler.asr_provider_name == 'deepgram'
        assert handler.asr_keywords == ['Bruce:100', 'CompanyName:80']
        print("✅ Test Passed: Handler stores ASR keywords for Deepgram")

    def test_handler_uses_elevenlabs_tts(self):
        """Test handler correctly configures ElevenLabs TTS"""
        from app.services.call_handlers.custom_provider_stream import CustomProviderStreamHandler

        config = {
            'user_id': 'test_user',
            'assistant_id': 'test_assistant',
            'system_message': 'Test',
            'tts_provider': 'elevenlabs',
            'voice': 'rachel'
        }

        handler = CustomProviderStreamHandler(
            websocket=Mock(),
            assistant_config=config,
            openai_api_key='test_key',
            call_id='test_call'
        )

        assert handler.tts_provider_name == 'elevenlabs'
        assert handler.voice == 'rachel'
        print("✅ Test Passed: Handler uses ElevenLabs TTS with correct voice")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
