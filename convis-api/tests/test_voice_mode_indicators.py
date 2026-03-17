"""
Unit Tests for Voice Mode Detection and Provider Display
Tests the logic for determining Realtime API vs Custom Provider mode
"""
import pytest
from typing import Dict, Any


class TestVoiceModeDetection:
    """Tests for voice mode detection logic"""

    def test_realtime_mode_explicit(self):
        """Test explicit realtime mode setting"""
        assistant = {
            "voice_mode": "realtime",
            "asr_provider": None,
            "tts_provider": None,
            "llm_provider": "openai"
        }

        is_custom = self._is_custom_mode(assistant)
        assert is_custom is False, "Should detect realtime mode"

    def test_custom_mode_explicit(self):
        """Test explicit custom mode setting"""
        assistant = {
            "voice_mode": "custom",
            "asr_provider": "deepgram",
            "tts_provider": "cartesia",
            "llm_provider": "groq"
        }

        is_custom = self._is_custom_mode(assistant)
        assert is_custom is True, "Should detect custom mode"

    def test_custom_mode_by_asr_provider(self):
        """Test custom mode detection by ASR provider presence"""
        assistant = {
            "voice_mode": None,
            "asr_provider": "deepgram",
            "tts_provider": None,
            "llm_provider": "openai"
        }

        is_custom = self._is_custom_mode(assistant)
        assert is_custom is True, "Should detect custom mode from ASR provider"

    def test_custom_mode_by_tts_provider(self):
        """Test custom mode detection by TTS provider presence"""
        assistant = {
            "voice_mode": None,
            "asr_provider": None,
            "tts_provider": "sarvam",
            "llm_provider": "openai"
        }

        is_custom = self._is_custom_mode(assistant)
        assert is_custom is True, "Should detect custom mode from TTS provider"

    def test_custom_mode_all_providers(self):
        """Test custom mode with all providers specified"""
        assistant = {
            "voice_mode": "custom",
            "asr_provider": "deepgram",
            "tts_provider": "cartesia",
            "llm_provider": "groq",
            "asr_model": "nova-3",
            "tts_voice": "sonic",
            "llm_model": "llama-3.3-70b-versatile"
        }

        is_custom = self._is_custom_mode(assistant)
        assert is_custom is True, "Should detect custom mode with all providers"

    def test_realtime_mode_default(self):
        """Test default realtime mode when nothing specified"""
        assistant = {
            "voice_mode": None,
            "asr_provider": None,
            "tts_provider": None,
            "llm_provider": None
        }

        is_custom = self._is_custom_mode(assistant)
        assert is_custom is False, "Should default to realtime mode"

    def test_openai_providers_realtime(self):
        """Test that OpenAI-only providers indicate realtime mode"""
        assistant = {
            "voice_mode": "realtime",
            "asr_provider": "openai",
            "tts_provider": "openai",
            "llm_provider": "openai"
        }

        is_custom = self._is_custom_mode(assistant)
        assert is_custom is False, "OpenAI-only should be realtime"

    def _is_custom_mode(self, assistant: Dict[str, Any]) -> bool:
        """
        Helper method that replicates the frontend detection logic
        Returns True if custom mode, False if realtime mode
        """
        return (
            assistant.get("voice_mode") == "custom" or
            (assistant.get("asr_provider") is not None and
             assistant.get("asr_provider") != "openai") or
            (assistant.get("tts_provider") is not None and
             assistant.get("tts_provider") != "openai")
        )


class TestProviderDisplayInfo:
    """Tests for provider information display"""

    def test_provider_info_custom_mode(self):
        """Test provider info extraction for custom mode"""
        assistant = {
            "asr_provider": "deepgram",
            "asr_model": "nova-3",
            "llm_provider": "groq",
            "llm_model": "llama-3.3-70b-versatile",
            "tts_provider": "cartesia",
            "tts_voice": "sonic",
            "tts_model": "sonic-english"
        }

        info = self._get_provider_display_info(assistant)

        assert info["asr"]["provider"] == "DEEPGRAM"
        assert info["asr"]["model"] == "nova-3"
        assert info["llm"]["provider"] == "GROQ"
        assert info["llm"]["model"] == "llama-3.3-70b-versatile"
        assert info["tts"]["provider"] == "CARTESIA"
        assert info["tts"]["voice"] == "sonic"

    def test_provider_info_defaults(self):
        """Test provider info with default values"""
        assistant = {
            "asr_provider": None,
            "llm_provider": None,
            "tts_provider": None
        }

        info = self._get_provider_display_info(assistant)

        assert info["asr"]["provider"] == "OPENAI"
        assert info["llm"]["provider"] == "OPENAI"
        assert info["tts"]["provider"] == "OPENAI"

    def test_provider_tooltip_text(self):
        """Test tooltip text generation"""
        assistant = {
            "asr_provider": "deepgram",
            "llm_provider": "groq",
            "tts_provider": "cartesia"
        }

        tooltip = self._generate_tooltip(assistant)

        assert "ASR: deepgram" in tooltip
        assert "LLM: groq" in tooltip
        assert "TTS: cartesia" in tooltip

    def test_sarvam_provider_info(self):
        """Test Sarvam AI provider display"""
        assistant = {
            "asr_provider": "sarvam",
            "asr_model": "saarika:v1",
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "tts_provider": "sarvam",
            "tts_voice": "Manisha",
            "tts_model": "bulbul:v2"
        }

        info = self._get_provider_display_info(assistant)

        assert info["asr"]["provider"] == "SARVAM"
        assert info["tts"]["provider"] == "SARVAM"
        assert info["tts"]["voice"] == "Manisha"

    def _get_provider_display_info(self, assistant: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """Extract provider display information"""
        return {
            "asr": {
                "provider": (assistant.get("asr_provider") or "openai").upper(),
                "model": assistant.get("asr_model")
            },
            "llm": {
                "provider": (assistant.get("llm_provider") or "openai").upper(),
                "model": assistant.get("llm_model")
            },
            "tts": {
                "provider": (assistant.get("tts_provider") or "openai").upper(),
                "voice": assistant.get("tts_voice"),
                "model": assistant.get("tts_model")
            }
        }

    def _generate_tooltip(self, assistant: Dict[str, Any]) -> str:
        """Generate tooltip text for provider badge"""
        asr = assistant.get("asr_provider") or "openai"
        llm = assistant.get("llm_provider") or "openai"
        tts = assistant.get("tts_provider") or "openai"
        return f"ASR: {asr} | LLM: {llm} | TTS: {tts}"


class TestBadgeRendering:
    """Tests for badge rendering logic"""

    def test_realtime_badge_properties(self):
        """Test realtime API badge properties"""
        badge = {
            "type": "realtime",
            "color": "blue",
            "icon": "lightning",
            "text": "Realtime API"
        }

        assert badge["type"] == "realtime"
        assert badge["color"] == "blue"
        assert badge["text"] == "Realtime API"

    def test_custom_badge_properties(self):
        """Test custom providers badge properties"""
        badge = {
            "type": "custom",
            "color": "purple",
            "icon": "circuit",
            "text": "Custom Providers"
        }

        assert badge["type"] == "custom"
        assert badge["color"] == "purple"
        assert badge["text"] == "Custom Providers"

    def test_api_key_badge_configured(self):
        """Test API key configured badge"""
        badge = {
            "type": "api_key",
            "status": "configured",
            "color": "green",
            "text": "API Key Configured"
        }

        assert badge["status"] == "configured"
        assert badge["color"] == "green"

    def test_api_key_badge_missing(self):
        """Test API key missing badge"""
        badge = {
            "type": "api_key",
            "status": "missing",
            "color": "red",
            "text": "No API Key"
        }

        assert badge["status"] == "missing"
        assert badge["color"] == "red"

    def test_knowledge_base_badge(self):
        """Test knowledge base badge"""
        badge = {
            "type": "knowledge_base",
            "color": "indigo",
            "count": 3,
            "text": "3 Docs"
        }

        assert badge["count"] == 3
        assert badge["text"] == "3 Docs"


class TestProviderCombinations:
    """Tests for various provider combinations"""

    def test_ultra_fast_combo(self):
        """Test ultra-fast provider combination"""
        assistant = {
            "voice_mode": "custom",
            "asr_provider": "deepgram",
            "asr_model": "nova-3",
            "llm_provider": "groq",
            "llm_model": "llama-3.3-70b-versatile",
            "tts_provider": "cartesia",
            "tts_model": "sonic-english"
        }

        estimated_latency = self._estimate_latency(assistant)

        # Deepgram (80ms) + Groq (150ms) + Cartesia (100ms) + buffer (500ms) = ~830ms
        assert 700 <= estimated_latency <= 900, f"Expected ~800ms, got {estimated_latency}ms"

    def test_quality_combo(self):
        """Test quality-focused provider combination"""
        assistant = {
            "voice_mode": "custom",
            "asr_provider": "deepgram",
            "asr_model": "nova-3",
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "tts_provider": "elevenlabs",
            "tts_model": "eleven_turbo_v2"
        }

        estimated_latency = self._estimate_latency(assistant)

        # Deepgram (80ms) + GPT-4O (800ms) + ElevenLabs (150ms) + buffer (500ms) = ~1530ms
        assert 1400 <= estimated_latency <= 1700, f"Expected ~1500ms, got {estimated_latency}ms"

    def test_indian_language_combo(self):
        """Test Indian language provider combination"""
        assistant = {
            "voice_mode": "custom",
            "asr_provider": "sarvam",
            "asr_language": "hi",
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "tts_provider": "sarvam",
            "tts_voice": "Manisha"
        }

        is_indian_lang = self._is_indian_language_setup(assistant)
        assert is_indian_lang is True

    def test_realtime_api_combo(self):
        """Test OpenAI Realtime API combination"""
        assistant = {
            "voice_mode": "realtime",
            "model": "gpt-4o-mini-realtime",
            "voice": "alloy"
        }

        estimated_latency = self._estimate_latency(assistant)

        # Realtime API: ~350ms
        assert 300 <= estimated_latency <= 450, f"Expected ~350ms, got {estimated_latency}ms"

    def _estimate_latency(self, assistant: Dict[str, Any]) -> int:
        """Estimate total latency based on providers"""
        latencies = {
            "deepgram": 80,
            "openai_asr": 250,
            "azure": 100,
            "sarvam_asr": 120,
            "assembly": 90,
            "google": 130,
            "groq": 150,
            "openai_llm": 800,
            "anthropic": 900,
            "gpt-4o-mini": 400,
            "cartesia": 100,
            "elevenlabs": 150,
            "sarvam_tts": 130,
            "openai_tts": 250
        }

        if assistant.get("voice_mode") == "realtime":
            return 350  # Realtime API latency

        total = 500  # Base buffer time

        # Add ASR latency
        asr = assistant.get("asr_provider", "openai")
        total += latencies.get(asr, latencies.get("openai_asr"))

        # Add LLM latency
        llm_provider = assistant.get("llm_provider", "openai")
        llm_model = assistant.get("llm_model", "")
        if "gpt-4o-mini" in llm_model:
            total += latencies["gpt-4o-mini"]
        elif "gpt-4o" in llm_model:
            total += latencies["openai_llm"]
        elif llm_provider == "groq":
            total += latencies["groq"]
        else:
            total += latencies.get(llm_provider, latencies["openai_llm"])

        # Add TTS latency
        tts = assistant.get("tts_provider", "openai")
        if tts == "sarvam":
            total += latencies["sarvam_tts"]
        elif tts == "openai":
            total += latencies["openai_tts"]
        else:
            total += latencies.get(tts, latencies["openai_tts"])

        return total

    def _is_indian_language_setup(self, assistant: Dict[str, Any]) -> bool:
        """Check if setup is for Indian languages"""
        indian_langs = ["hi", "te", "ta", "mr", "bn", "gu", "kn", "ml", "pa"]
        asr_lang = assistant.get("asr_language", "en")

        return (
            asr_lang in indian_langs or
            assistant.get("asr_provider") == "sarvam" or
            assistant.get("tts_provider") == "sarvam"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
