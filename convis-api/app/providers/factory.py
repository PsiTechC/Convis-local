"""
Provider Factory - Dynamically create ASR/TTS providers based on configuration
"""

import logging
from typing import Optional
from .asr import ASRProvider, DeepgramASR, OpenAIASR, SarvamASR, GoogleASR
from .tts import TTSProvider, CartesiaTTS, ElevenLabsTTS, OpenAITTS, SarvamTTS, PiperTTS

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating ASR and TTS providers dynamically"""

    # Provider registry - All supported ASR providers
    ASR_PROVIDERS = {
        'deepgram': DeepgramASR,
        'openai': OpenAIASR,
        'sarvam': SarvamASR,
        'google': GoogleASR,
    }

    TTS_PROVIDERS = {
        'cartesia': CartesiaTTS,
        'elevenlabs': ElevenLabsTTS,
        'openai': OpenAITTS,
        'sarvam': SarvamTTS,
        'piper': PiperTTS,
    }

    @classmethod
    def create_asr_provider(
        cls,
        provider_name: str,
        api_key: Optional[str] = None,
        model: str = "default",
        language: str = "en",
        keywords: Optional[str] = None
    ) -> ASRProvider:
        """
        Create ASR provider instance

        Args:
            provider_name: Name of provider ('deepgram', 'openai', etc.)
            api_key: API key (optional, will use env var if not provided)
            model: Model name
            language: Language code
            keywords: Comma-separated keywords for boosting (Deepgram only)

        Returns:
            ASRProvider instance

        Raises:
            ValueError: If provider not found
        """
        provider_name = provider_name.lower()

        if provider_name not in cls.ASR_PROVIDERS:
            available = ', '.join(cls.ASR_PROVIDERS.keys())
            raise ValueError(
                f"Unknown ASR provider: {provider_name}. "
                f"Available providers: {available}"
            )

        provider_class = cls.ASR_PROVIDERS[provider_name]
        logger.info(f"Creating ASR provider: {provider_name} with model: {model}")

        # Pass keywords only to Deepgram (other providers don't support it)
        if provider_name == 'deepgram' and keywords:
            logger.info(f"Deepgram ASR with keyword boosting enabled")
            return provider_class(
                api_key=api_key,
                model=model,
                language=language,
                keywords=keywords
            )

        return provider_class(
            api_key=api_key,
            model=model,
            language=language
        )

    @classmethod
    def create_tts_provider(
        cls,
        provider_name: str,
        api_key: Optional[str] = None,
        voice: str = "default",
        **kwargs
    ) -> TTSProvider:
        """
        Create TTS provider instance

        Args:
            provider_name: Name of provider ('cartesia', 'elevenlabs', 'openai', 'sarvam')
            api_key: API key (optional, will use env var if not provided)
            voice: Voice name
            **kwargs: Additional provider-specific parameters (e.g., language for Sarvam)

        Returns:
            TTSProvider instance

        Raises:
            ValueError: If provider not found
        """
        provider_name = provider_name.lower()

        if provider_name not in cls.TTS_PROVIDERS:
            available = ', '.join(cls.TTS_PROVIDERS.keys())
            raise ValueError(
                f"Unknown TTS provider: {provider_name}. "
                f"Available providers: {available}"
            )

        provider_class = cls.TTS_PROVIDERS[provider_name]
        logger.info(f"Creating TTS provider: {provider_name} with voice: {voice}")

        # Pass additional kwargs for provider-specific parameters
        return provider_class(
            api_key=api_key,
            voice=voice,
            **kwargs
        )

    @classmethod
    def get_provider_info(cls, provider_type: str) -> dict:
        """
        Get information about available providers

        Args:
            provider_type: 'asr' or 'tts'

        Returns:
            Dictionary with provider information
        """
        if provider_type == 'asr':
            providers = {}
            for name, provider_class in cls.ASR_PROVIDERS.items():
                # Create temporary instance to get info
                try:
                    instance = provider_class(api_key="temp")
                    providers[name] = {
                        'latency_ms': instance.get_latency_ms(),
                        'cost_per_minute': instance.get_cost_per_minute(),
                        'description': instance.__class__.__doc__
                    }
                except:
                    providers[name] = {'error': 'Could not instantiate'}

            return providers

        elif provider_type == 'tts':
            providers = {}
            for name, provider_class in cls.TTS_PROVIDERS.items():
                try:
                    instance = provider_class(api_key="temp")
                    providers[name] = {
                        'latency_ms': instance.get_latency_ms(),
                        'cost_per_minute': instance.get_cost_per_minute(),
                        'voices': instance.get_available_voices(),
                        'description': instance.__class__.__doc__
                    }
                except:
                    providers[name] = {'error': 'Could not instantiate'}

            return providers

        else:
            raise ValueError("provider_type must be 'asr' or 'tts'")

    @classmethod
    def calculate_cost(
        cls,
        asr_provider: str,
        tts_provider: str,
        duration_minutes: float
    ) -> dict:
        """
        Calculate total cost for a call

        Args:
            asr_provider: ASR provider name
            tts_provider: TTS provider name
            duration_minutes: Call duration in minutes

        Returns:
            Cost breakdown dictionary
        """
        try:
            asr = cls.create_asr_provider(asr_provider)
            tts = cls.create_tts_provider(tts_provider)

            asr_cost = asr.get_cost_per_minute() * duration_minutes
            tts_cost = tts.get_cost_per_minute() * duration_minutes
            # LLM cost (approximate for GPT-4 Turbo)
            llm_cost = 0.10 * duration_minutes

            total_cost = asr_cost + tts_cost + llm_cost

            return {
                'asr_cost': round(asr_cost, 4),
                'tts_cost': round(tts_cost, 4),
                'llm_cost': round(llm_cost, 4),
                'total_cost': round(total_cost, 4),
                'cost_per_minute': round(total_cost / duration_minutes, 4),
                'duration_minutes': duration_minutes
            }

        except Exception as e:
            logger.error(f"Error calculating cost: {e}")
            return {'error': str(e)}

    @classmethod
    def get_recommended_combination(cls, priority: str = 'balanced') -> dict:
        """
        Get recommended provider combination based on priority

        Args:
            priority: 'speed', 'cost', 'quality', or 'balanced'

        Returns:
            Recommended configuration
        """
        recommendations = {
            'speed': {
                'asr_provider': 'deepgram',
                'asr_model': 'nova-2',
                'tts_provider': 'cartesia',
                'tts_voice': 'sonic',
                'description': 'Fastest configuration (180-320ms latency)',
                'estimated_latency_ms': 250,
                'estimated_cost_per_min': 0.11
            },
            'cost': {
                'asr_provider': 'deepgram',
                'asr_model': 'nova-2',
                'tts_provider': 'cartesia',
                'tts_voice': 'sonic',
                'description': 'Most economical (64% cheaper than OpenAI Realtime)',
                'estimated_latency_ms': 250,
                'estimated_cost_per_min': 0.11
            },
            'quality': {
                'asr_provider': 'deepgram',
                'asr_model': 'nova-2',
                'tts_provider': 'elevenlabs',
                'tts_voice': 'rachel',
                'description': 'Best voice quality',
                'estimated_latency_ms': 300,
                'estimated_cost_per_min': 0.12
            },
            'balanced': {
                'asr_provider': 'deepgram',
                'asr_model': 'nova-2',
                'tts_provider': 'cartesia',
                'tts_voice': 'sonic',
                'description': 'Best balance of speed, cost, and quality',
                'estimated_latency_ms': 250,
                'estimated_cost_per_min': 0.11
            }
        }

        return recommendations.get(priority, recommendations['balanced'])
