from typing import Tuple, Optional, Dict, Union
from bson import ObjectId
from fastapi import HTTPException, status
from app.utils.encryption import encryption_service
import os
import logging

logger = logging.getLogger(__name__)

# NOTE: Deployments now supply provider API keys via environment variables.
# The new helper resolve_env_provider_keys below lets callers enforce env-only
# resolution (no DB lookups) to keep the voice pipelines deterministic.


def resolve_assistant_api_key(db, assistant: dict, required_provider: Optional[str] = "openai") -> Tuple[str, str]:
    """
    Retrieve API key from environment variables (system-wide configuration).
    Database API keys are no longer used - all keys come from .env

    Args:
        db: Database connection (not used, kept for backwards compatibility)
        assistant: Assistant document (not used, kept for backwards compatibility)
        required_provider: Provider name (e.g. 'openai')

    Returns:
        Tuple[str, str]: API key from environment and provider name

    Raises:
        HTTPException: when environment key is not configured
    """
    provider = required_provider or 'openai'

    # Local providers that do not require API keys
    local_providers = {'piper', 'ollama', 'whisper'}
    if provider.lower() in local_providers:
        logger.info(f"✓ Provider '{provider}' does not require an API key")
        return "", provider

    # Map provider to environment variable
    env_var_map = {
        'openai': 'OPENAI_API_KEY',
        'deepgram': 'DEEPGRAM_API_KEY',
        'sarvam': 'SARVAM_API_KEY',
        'google': 'GOOGLE_API_KEY',
        'cartesia': 'CARTESIA_API_KEY',
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'groq': 'GROQ_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY'
    }

    env_var = env_var_map.get(provider.lower())
    if not env_var:
        logger.error(f"Unknown provider: {provider}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider}' is not supported."
        )

    api_key = os.getenv(env_var)
    if not api_key:
        logger.error(f"Environment variable {env_var} not configured for provider {provider}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API key not configured for {provider}. Please contact administrator."
        )

    logger.info(f"✓ Using system API key from environment variable {env_var}")
    return api_key.strip(), provider


def resolve_provider_keys(db, assistant: dict, user_id: ObjectId) -> Dict[str, str]:
    """
    Resolve API keys for all providers from environment variables only.
    Database keys are no longer used - system uses .env configuration.

    Args:
        db: Database connection (not used, kept for backwards compatibility)
        assistant: Assistant document
        user_id: User ID (not used, kept for backwards compatibility)

    Returns:
        Dict[str, str]: Dictionary mapping provider names to API keys from environment
        Example: {
            'openai': 'sk-...',
            'deepgram': '...',
            'cartesia': 'sk_car_...',
            'elevenlabs': 'sk_...',
            'groq': 'gsk_...',
            'anthropic': 'sk-ant-...'
        }
    """
    provider_keys = {}

    # Get ASR, TTS, and LLM providers from assistant config
    asr_provider = assistant.get('asr_provider', 'openai').lower()
    tts_provider = assistant.get('tts_provider', 'openai').lower()
    llm_provider = assistant.get('llm_provider', 'openai').lower()

    # Collect unique providers needed
    needed_providers = set([asr_provider, tts_provider, llm_provider])

    logger.info(f"Resolving system API keys for providers: {needed_providers}")

    # Providers that do not require API keys
    local_providers = {'piper', 'ollama', 'whisper'}

    # Get keys from environment variables only
    env_var_map = {
        'openai': 'OPENAI_API_KEY',
        'deepgram': 'DEEPGRAM_API_KEY',
        'sarvam': 'SARVAM_API_KEY',
        'google': 'GOOGLE_API_KEY',
        'cartesia': 'CARTESIA_API_KEY',
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'groq': 'GROQ_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'azure': 'AZURE_API_KEY',
        'assembly': 'ASSEMBLYAI_API_KEY'
    }

    for provider in needed_providers:
        if provider in local_providers:
            logger.info(f"✓ Provider {provider} is local/offline and needs no API key")
            continue

        env_var = env_var_map.get(provider)
        if env_var:
            env_value = os.getenv(env_var)
            if env_value:
                provider_keys[provider] = env_value.strip()
                logger.info(f"✓ Resolved {provider} key from environment variable {env_var}")
            else:
                logger.warning(f"⚠ No {provider} API key found in environment variable {env_var}")
        else:
            logger.warning(f"⚠ Unknown provider: {provider}, no env var mapping")

    return provider_keys


def resolve_user_provider_key(
    db,
    user_id: Union[str, ObjectId],
    provider: str,
    allow_env_fallback: bool = True
) -> Optional[str]:
    """
    Retrieve API key from environment variables (system-wide configuration).
    Database keys are no longer used - always returns from .env

    Args:
        db: Database connection (not used, kept for backwards compatibility)
        user_id: User's ObjectId (not used, kept for backwards compatibility)
        provider: Provider name (e.g., 'openai')
        allow_env_fallback: Not used (always uses env)

    Returns:
        API key from environment or None if not configured
    """
    env_var_map = {
        'openai': 'OPENAI_API_KEY',
        'deepgram': 'DEEPGRAM_API_KEY',
        'sarvam': 'SARVAM_API_KEY',
        'google': 'GOOGLE_API_KEY',
        'cartesia': 'CARTESIA_API_KEY',
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'groq': 'GROQ_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'azure': 'AZURE_API_KEY',
        'assembly': 'ASSEMBLYAI_API_KEY'
    }

    if provider.lower() in {'piper', 'ollama', 'whisper'}:
        logger.info(f"✓ Provider {provider} is local/offline and needs no API key")
        return ""

    env_var = env_var_map.get(provider.lower())
    if env_var:
        env_value = os.getenv(env_var)
        if env_value:
            logger.info(f"✓ Using system API key from environment variable {env_var} for provider {provider}")
            return env_value.strip()
        logger.warning(f"⚠ No environment variable configured for provider {provider} ({env_var})")
    else:
        logger.warning(f"⚠ No environment mapping defined for provider {provider}")

    return None


def resolve_env_provider_keys(
    asr_provider: str,
    tts_provider: str,
    llm_provider: str
) -> Dict[str, str]:
    """
    Resolve required provider keys strictly from environment variables.
    This bypasses any database lookup to align with deployments where
    keys are injected via container envs only.
    """
    provider_env_map = {
        'openai': 'OPENAI_API_KEY',
        'openai-realtime': 'OPENAI_API_KEY',
        'deepgram': 'DEEPGRAM_API_KEY',
        'sarvam': 'SARVAM_API_KEY',
        'google': 'GOOGLE_API_KEY',
        'cartesia': 'CARTESIA_API_KEY',
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'groq': 'GROQ_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY'
    }

    local_providers = {'piper', 'ollama', 'whisper'}
    needed = {asr_provider.lower(), tts_provider.lower(), llm_provider.lower()}
    keys: Dict[str, str] = {}
    missing = []

    for provider in needed:
        if provider in local_providers:
            continue

        env_var = provider_env_map.get(provider)
        if not env_var:
            missing.append(provider)
            continue
        value = os.getenv(env_var)
        if value:
            keys[provider] = value.strip()
        else:
            missing.append(provider)

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing API keys for providers: {', '.join(sorted(missing))}. "
                   "Ensure they are set via environment variables."
        )

    return keys
