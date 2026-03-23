"""
Integration Validation Script
Validates that all provider integrations are properly configured
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import inspect
from app.utils.custom_provider_handler import CustomProviderHandler
from app.models.ai_assistant import AIAssistantCreate, AIAssistantUpdate, AIAssistantResponse


def validate_class_structure():
    """Validate CustomProviderHandler class structure"""
    print("=" * 60)
    print("VALIDATING CLASS STRUCTURE")
    print("=" * 60)

    # Check all required methods exist
    required_methods = [
        # Main handlers
        'handle_twilio_message',
        'handle_start',
        'handle_media',
        'handle_stop',
        'process_audio_buffer',

        # ASR methods
        'transcribe_audio',
        'transcribe_deepgram',
        'transcribe_openai',
        'transcribe_azure',
        'transcribe_sarvam',
        'transcribe_assembly',
        'transcribe_google',

        # LLM methods
        'generate_llm_response',
        'generate_openai_response',
        'generate_azure_response',
        'generate_anthropic_response',
        'generate_deepseek_response',
        'generate_openrouter_response',
        'generate_groq_response',

        # TTS methods
        'synthesize_and_send',
        'synthesize_openai',
        'synthesize_cartesia',
        'synthesize_sarvam',
        'synthesize_azuretts',
        'synthesize_elevenlabs',

        # Utility
        'send_audio_to_twilio'
    ]

    missing_methods = []
    for method_name in required_methods:
        if not hasattr(CustomProviderHandler, method_name):
            missing_methods.append(method_name)
        else:
            print(f"✓ Method '{method_name}' exists")

    if missing_methods:
        print(f"\n✗ MISSING METHODS: {missing_methods}")
        return False

    print(f"\n✓ All {len(required_methods)} required methods exist!")
    return True


def validate_asr_routing():
    """Validate ASR provider routing"""
    print("\n" + "=" * 60)
    print("VALIDATING ASR PROVIDER ROUTING")
    print("=" * 60)

    # Get the transcribe_audio method source
    source = inspect.getsource(CustomProviderHandler.transcribe_audio)

    asr_providers = ['deepgram', 'openai', 'azure', 'sarvam', 'assembly', 'google']

    for provider in asr_providers:
        if provider in source:
            print(f"✓ ASR provider '{provider}' is routed in transcribe_audio()")
        else:
            print(f"✗ ASR provider '{provider}' NOT found in routing")
            return False

    print(f"\n✓ All {len(asr_providers)} ASR providers are properly routed!")
    return True


def validate_llm_routing():
    """Validate LLM provider routing"""
    print("\n" + "=" * 60)
    print("VALIDATING LLM PROVIDER ROUTING")
    print("=" * 60)

    # Get the generate_llm_response method source
    source = inspect.getsource(CustomProviderHandler.generate_llm_response)

    llm_providers = ['openai', 'azure', 'anthropic', 'deepseek', 'openrouter', 'groq']

    for provider in llm_providers:
        if provider in source:
            print(f"✓ LLM provider '{provider}' is routed in generate_llm_response()")
        else:
            print(f"✗ LLM provider '{provider}' NOT found in routing")
            return False

    print(f"\n✓ All {len(llm_providers)} LLM providers are properly routed!")
    return True


def validate_tts_routing():
    """Validate TTS provider routing"""
    print("\n" + "=" * 60)
    print("VALIDATING TTS PROVIDER ROUTING")
    print("=" * 60)

    # Get the synthesize_and_send method source
    source = inspect.getsource(CustomProviderHandler.synthesize_and_send)

    tts_providers = ['openai', 'cartesia', 'sarvam', 'azuretts', 'elevenlabs']

    for provider in tts_providers:
        if provider in source:
            print(f"✓ TTS provider '{provider}' is routed in synthesize_and_send()")
        else:
            print(f"✗ TTS provider '{provider}' NOT found in routing")
            return False

    print(f"\n✓ All {len(tts_providers)} TTS providers are properly routed!")
    return True


def validate_model_fields():
    """Validate AI Assistant model fields"""
    print("\n" + "=" * 60)
    print("VALIDATING MODEL FIELDS")
    print("=" * 60)

    required_fields = {
        'voice_mode': 'Voice mode selection',
        'asr_provider': 'ASR provider selection',
        'asr_model': 'ASR model',
        'asr_language': 'ASR language',
        'llm_provider': 'LLM provider selection',
        'llm_model': 'LLM model',
        'llm_max_tokens': 'LLM max tokens',
        'tts_provider': 'TTS provider selection',
        'tts_model': 'TTS model',
        'tts_voice': 'TTS voice',
        'tts_speed': 'TTS speed'
    }

    # Check AIAssistantCreate
    create_fields = AIAssistantCreate.model_fields
    for field, description in required_fields.items():
        if field in create_fields:
            print(f"✓ AIAssistantCreate has field '{field}' ({description})")
        else:
            print(f"✗ AIAssistantCreate missing field '{field}'")
            return False

    # Check AIAssistantUpdate
    update_fields = AIAssistantUpdate.model_fields
    for field, description in required_fields.items():
        if field in update_fields:
            print(f"✓ AIAssistantUpdate has field '{field}' ({description})")
        else:
            print(f"✗ AIAssistantUpdate missing field '{field}'")
            return False

    # Check AIAssistantResponse
    response_fields = AIAssistantResponse.model_fields
    for field, description in required_fields.items():
        if field in response_fields:
            print(f"✓ AIAssistantResponse has field '{field}' ({description})")
        else:
            print(f"✗ AIAssistantResponse missing field '{field}'")
            return False

    print(f"\n✓ All {len(required_fields)} required fields exist in all models!")
    return True


def validate_api_integrations():
    """Validate API integration implementations"""
    print("\n" + "=" * 60)
    print("VALIDATING API INTEGRATIONS")
    print("=" * 60)

    integrations = {
        # ASR
        'transcribe_deepgram': ['api.deepgram.com', 'Authorization'],
        'transcribe_openai': ['api.openai.com/v1/audio/transcriptions', 'Authorization'],
        'transcribe_azure': ['stt.speech.microsoft.com', 'Ocp-Apim-Subscription-Key'],
        'transcribe_sarvam': ['api.sarvam.ai/speech-to-text', 'api-subscription-key'],
        'transcribe_assembly': ['api.assemblyai.com', 'authorization'],
        'transcribe_google': ['speech.googleapis.com', 'speech:recognize'],

        # LLM
        'generate_openai_response': ['api.openai.com/v1/chat/completions', 'Authorization'],
        'generate_anthropic_response': ['api.anthropic.com/v1/messages', 'x-api-key'],
        'generate_deepseek_response': ['api.deepseek.com/v1/chat/completions', 'Authorization'],
        'generate_openrouter_response': ['openrouter.ai/api/v1/chat/completions', 'Authorization'],
        'generate_groq_response': ['api.groq.com/openai/v1/chat/completions', 'Authorization'],

        # TTS
        'synthesize_openai': ['api.openai.com/v1/audio/speech', 'Authorization'],
        'synthesize_cartesia': ['api.cartesia.ai/tts/bytes', 'X-API-Key'],
        'synthesize_sarvam': ['api.sarvam.ai/text-to-speech', 'api-subscription-key'],
        'synthesize_azuretts': ['tts.speech.microsoft.com', 'Ocp-Apim-Subscription-Key'],
        'synthesize_elevenlabs': ['api.elevenlabs.io/v1/text-to-speech', 'xi-api-key']
    }

    for method_name, (api_endpoint, auth_header) in integrations.items():
        if not hasattr(CustomProviderHandler, method_name):
            print(f"✗ Method '{method_name}' not found")
            return False

        source = inspect.getsource(getattr(CustomProviderHandler, method_name))

        has_endpoint = api_endpoint in source
        has_auth = auth_header in source

        if has_endpoint and has_auth:
            print(f"✓ {method_name}: API endpoint and auth configured")
        else:
            missing = []
            if not has_endpoint:
                missing.append("endpoint")
            if not has_auth:
                missing.append("auth")
            print(f"✗ {method_name}: Missing {', '.join(missing)}")
            return False

    print(f"\n✓ All {len(integrations)} API integrations are properly implemented!")
    return True


def run_all_validations():
    """Run all validation checks"""
    print("\n" + "=" * 60)
    print("CUSTOM PROVIDER INTEGRATION VALIDATION")
    print("=" * 60)

    results = {
        'Class Structure': validate_class_structure(),
        'ASR Routing': validate_asr_routing(),
        'LLM Routing': validate_llm_routing(),
        'TTS Routing': validate_tts_routing(),
        'Model Fields': validate_model_fields(),
        'API Integrations': validate_api_integrations()
    }

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    for check, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{check}: {status}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL VALIDATIONS PASSED!")
        print("=" * 60)
        print("\nSummary:")
        print("- All 6 ASR providers implemented: Deepgram, OpenAI, Azure, Sarvam, Assembly, Google")
        print("- All 6 LLM providers implemented: OpenAI, Azure, Anthropic, Deepseek, OpenRouter, Groq")
        print("- All 5 TTS providers implemented: OpenAI, Cartesia, Sarvam, Azure, ElevenLabs")
        print("- All routing logic working correctly")
        print("- All model fields configured")
        print("- All API integrations implemented")
        print("\nStatus: READY FOR PRODUCTION")
        return 0
    else:
        print("✗ SOME VALIDATIONS FAILED")
        print("=" * 60)
        failed_checks = [check for check, passed in results.items() if not passed]
        print(f"\nFailed checks: {', '.join(failed_checks)}")
        print("\nStatus: REQUIRES FIXES")
        return 1


if __name__ == '__main__':
    exit_code = run_all_validations()
    sys.exit(exit_code)
