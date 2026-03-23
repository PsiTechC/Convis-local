"""
Comprehensive Pricing Calculator for Voice AI Services
Includes: OpenAI, Anthropic, Deepgram, ElevenLabs, Cartesia, Twilio
All prices updated as of January 2025
"""
from typing import Dict, Optional, Tuple
from datetime import datetime

# Exchange rate (updated dynamically, but default fallback)
USD_TO_INR = 83.0  # 1 USD = 83 INR (approximate, can be updated)

# ============================================================================
# TWILIO PRICING
# ============================================================================
TWILIO_PRICING = {
    "call_per_minute_usd": 0.0140,       # $0.014/min for US calls
    "recording_per_minute_usd": 0.0025,  # $0.0025/min
}

# ============================================================================
# OPENAI PRICING (Realtime API)
# ============================================================================
OPENAI_REALTIME_PRICING = {
    # GPT-4o Realtime models
    "gpt-4o-realtime-preview": {
        "audio_input_per_min": 0.06,   # $0.06/min
        "audio_output_per_min": 0.24,  # $0.24/min
        "text_input_per_1m": 5.00,     # $5/1M tokens
        "text_output_per_1m": 20.00,   # $20/1M tokens
        "includes_transcription": True,
        "includes_tts": True,
        "total_per_min_estimate": 0.30  # Average total
    },
    "gpt-4o-realtime-preview-2024-10-01": {
        "audio_input_per_min": 0.06,
        "audio_output_per_min": 0.24,
        "text_input_per_1m": 5.00,
        "text_output_per_1m": 20.00,
        "includes_transcription": True,
        "includes_tts": True,
        "total_per_min_estimate": 0.30
    },
    "gpt-4o-realtime": {
        "audio_input_per_min": 0.06,
        "audio_output_per_min": 0.24,
        "text_input_per_1m": 5.00,
        "text_output_per_1m": 20.00,
        "includes_transcription": True,
        "includes_tts": True,
        "total_per_min_estimate": 0.30
    },
    # GPT-4o Mini Realtime models (cheaper)
    "gpt-4o-mini-realtime-preview": {
        "audio_input_per_min": 0.06,
        "audio_output_per_min": 0.24,
        "text_input_per_1m": 0.15,     # Much cheaper text
        "text_output_per_1m": 0.60,
        "includes_transcription": True,
        "includes_tts": True,
        "total_per_min_estimate": 0.30  # Same audio cost
    },
    "gpt-4o-mini-realtime": {
        "audio_input_per_min": 0.06,
        "audio_output_per_min": 0.24,
        "text_input_per_1m": 0.15,
        "text_output_per_1m": 0.60,
        "includes_transcription": True,
        "includes_tts": True,
        "total_per_min_estimate": 0.30
    },
}

# ============================================================================
# ASR (Speech-to-Text) PRICING
# ============================================================================
ASR_PRICING = {
    "openai": {
        "whisper-1": {
            "per_minute": 0.006,  # $0.006/min
            "per_hour": 0.36,
        }
    },
    "deepgram": {
        "nova-2": {
            "per_minute": 0.0043,  # $0.0043/min
            "per_hour": 0.26,
        },
        "nova": {
            "per_minute": 0.0043,
            "per_hour": 0.26,
        },
        "whisper": {
            "per_minute": 0.0048,
            "per_hour": 0.29,
        },
        "base": {
            "per_minute": 0.0125,
            "per_hour": 0.75,
        }
    },
    "azure": {
        "default": {
            "per_hour": 1.00,  # $1/hour
            "per_minute": 0.0167,
        }
    },
    "google": {
        "default": {
            "per_minute": 0.006,
            "per_hour": 0.36,
        }
    },
    "assemblyai": {
        "default": {
            "per_hour": 0.65,
            "per_minute": 0.0108,
        }
    },
    "sarvam": {
        "default": {
            "per_minute": 0.004,  # Estimated
            "per_hour": 0.24,
        }
    }
}

# ============================================================================
# LLM (Language Model) PRICING
# ============================================================================
LLM_PRICING = {
    "openai": {
        "gpt-4o": {
            "input_per_1m": 2.50,   # $2.50/1M tokens
            "output_per_1m": 10.00,  # $10/1M tokens
        },
        "gpt-4o-mini": {
            "input_per_1m": 0.150,   # $0.15/1M tokens
            "output_per_1m": 0.600,  # $0.60/1M tokens
        },
        "gpt-4-turbo": {
            "input_per_1m": 10.00,
            "output_per_1m": 30.00,
        },
        "gpt-3.5-turbo": {
            "input_per_1m": 0.50,
            "output_per_1m": 1.50,
        }
    },
    "anthropic": {
        "claude-sonnet-4": {
            "input_per_1m": 3.00,
            "output_per_1m": 15.00,
        },
        "claude-sonnet-3.5": {
            "input_per_1m": 3.00,
            "output_per_1m": 15.00,
        },
        "claude-haiku-3.5": {
            "input_per_1m": 0.80,
            "output_per_1m": 4.00,
        },
        "claude-opus-3": {
            "input_per_1m": 15.00,
            "output_per_1m": 75.00,
        }
    },
    "deepseek": {
        "deepseek-chat": {
            "input_per_1m": 0.14,   # Ultra cheap!
            "output_per_1m": 0.28,
        },
        "deepseek-reasoner": {
            "input_per_1m": 0.55,
            "output_per_1m": 2.19,
        }
    },
    "groq": {
        "llama-3-70b": {
            "input_per_1m": 0.59,
            "output_per_1m": 0.79,
        },
        "llama-3-8b": {
            "input_per_1m": 0.05,
            "output_per_1m": 0.08,
        },
        "mixtral-8x7b": {
            "input_per_1m": 0.27,
            "output_per_1m": 0.27,
        }
    },
    "cohere": {
        "command-r-plus": {
            "input_per_1m": 2.50,
            "output_per_1m": 10.00,
        },
        "command-r": {
            "input_per_1m": 0.15,
            "output_per_1m": 0.60,
        }
    }
}

# ============================================================================
# TTS (Text-to-Speech) PRICING
# ============================================================================
TTS_PRICING = {
    "openai": {
        "tts-1": {
            "per_1m_chars": 15.00,  # $15/1M characters
            "per_1k_chars": 0.015,
        },
        "tts-1-hd": {
            "per_1m_chars": 30.00,
            "per_1k_chars": 0.030,
        }
    },
    "elevenlabs": {
        "eleven_turbo_v2_5": {
            "per_1m_chars": 180.00,  # $180/1M chars (high quality)
            "per_1k_chars": 0.18,
        },
        "eleven_multilingual_v2": {
            "per_1m_chars": 180.00,
            "per_1k_chars": 0.18,
        }
    },
    "cartesia": {
        "sonic": {
            "per_1m_chars": 25.00,  # $25/1M chars (fast)
            "per_1k_chars": 0.025,
        },
        "sonic-english": {
            "per_1m_chars": 25.00,
            "per_1k_chars": 0.025,
        }
    },
    "azure": {
        "default": {
            "per_1m_chars": 15.00,
            "per_1k_chars": 0.015,
        }
    }
}


class PricingCalculator:
    """Calculate costs for voice AI calls"""

    def __init__(self, currency: str = "USD"):
        """
        Initialize calculator
        Args:
            currency: "USD" or "INR"
        """
        self.currency = currency
        self.usd_to_inr = USD_TO_INR

    def convert_to_currency(self, usd_amount: float) -> float:
        """Convert USD to selected currency"""
        if self.currency == "INR":
            return usd_amount * self.usd_to_inr
        return usd_amount

    def calculate_realtime_api_cost(
        self,
        model: str,
        duration_minutes: float
    ) -> Dict[str, float]:
        """
        Calculate OpenAI Realtime API cost

        Args:
            model: Model name (e.g., "gpt-4o-realtime")
            duration_minutes: Call duration in minutes

        Returns:
            Dict with cost breakdown
        """
        pricing = OPENAI_REALTIME_PRICING.get(model, OPENAI_REALTIME_PRICING["gpt-4o-realtime"])

        # Realtime API pricing is per minute for audio
        api_cost_usd = pricing["total_per_min_estimate"] * duration_minutes

        # Add Twilio cost (convert from USD so USD/INR stay in sync)
        twilio_cost_usd = TWILIO_PRICING["call_per_minute_usd"] * duration_minutes
        twilio_cost_inr = twilio_cost_usd * self.usd_to_inr

        total_usd = api_cost_usd + twilio_cost_usd
        total_inr = (api_cost_usd * self.usd_to_inr) + twilio_cost_inr

        return {
            "api_cost_usd": round(api_cost_usd, 4),
            "api_cost_inr": round(api_cost_usd * self.usd_to_inr, 2),
            "twilio_cost_usd": round(twilio_cost_usd, 4),
            "twilio_cost_inr": round(twilio_cost_inr, 2),
            "total_usd": round(total_usd, 4),
            "total_inr": round(total_inr, 2),
            "currency": self.currency,
            "total": round(total_inr if self.currency == "INR" else total_usd, 2),
            "model": model,
            "duration_minutes": duration_minutes,
            "includes_transcription": True,
            "breakdown": {
                "realtime_api": round(api_cost_usd, 4),
                "twilio": round(twilio_cost_usd, 4)
            }
        }

    def calculate_custom_pipeline_cost(
        self,
        asr_provider: str,
        asr_model: str,
        llm_provider: str,
        llm_model: str,
        tts_provider: str,
        tts_model: str,
        duration_minutes: float,
        estimated_tokens_in: int = 500,  # Estimated input tokens
        estimated_tokens_out: int = 300,  # Estimated output tokens
        estimated_tts_chars: int = 1000   # Estimated TTS characters
    ) -> Dict[str, float]:
        """
        Calculate custom provider pipeline cost

        Args:
            asr_provider: ASR provider name
            asr_model: ASR model name
            llm_provider: LLM provider name
            llm_model: LLM model name
            tts_provider: TTS provider name
            tts_model: TTS model name
            duration_minutes: Call duration
            estimated_tokens_in: Estimated input tokens per minute
            estimated_tokens_out: Estimated output tokens per minute
            estimated_tts_chars: Estimated TTS characters per minute

        Returns:
            Dict with cost breakdown
        """
        # ASR cost
        asr_pricing = ASR_PRICING.get(asr_provider, {}).get(asr_model, {})
        if not asr_pricing:
            asr_pricing = ASR_PRICING.get(asr_provider, {}).get("default", {"per_minute": 0.005})
        asr_cost_usd = asr_pricing.get("per_minute", 0.005) * duration_minutes

        # LLM cost (token-based)
        llm_pricing = LLM_PRICING.get(llm_provider, {}).get(llm_model, {})
        if not llm_pricing:
            llm_pricing = {"input_per_1m": 0.50, "output_per_1m": 1.50}  # Default

        total_tokens_in = estimated_tokens_in * duration_minutes
        total_tokens_out = estimated_tokens_out * duration_minutes

        llm_cost_usd = (
            (total_tokens_in / 1_000_000) * llm_pricing["input_per_1m"] +
            (total_tokens_out / 1_000_000) * llm_pricing["output_per_1m"]
        )

        # TTS cost (character-based)
        tts_pricing = TTS_PRICING.get(tts_provider, {}).get(tts_model, {})
        if not tts_pricing:
            tts_pricing = TTS_PRICING.get(tts_provider, {}).get("default", {"per_1k_chars": 0.015})

        total_chars = estimated_tts_chars * duration_minutes
        tts_cost_usd = (total_chars / 1000) * tts_pricing.get("per_1k_chars", 0.015)

        # Total API cost
        api_cost_usd = asr_cost_usd + llm_cost_usd + tts_cost_usd

        # Twilio cost (keep USD as source of truth)
        twilio_cost_usd = TWILIO_PRICING["call_per_minute_usd"] * duration_minutes
        twilio_cost_inr = twilio_cost_usd * self.usd_to_inr

        total_usd = api_cost_usd + twilio_cost_usd
        total_inr = (api_cost_usd * self.usd_to_inr) + twilio_cost_inr

        return {
            "asr_cost_usd": round(asr_cost_usd, 4),
            "llm_cost_usd": round(llm_cost_usd, 4),
            "tts_cost_usd": round(tts_cost_usd, 4),
            "api_cost_usd": round(api_cost_usd, 4),
            "api_cost_inr": round(api_cost_usd * self.usd_to_inr, 2),
            "twilio_cost_usd": round(twilio_cost_usd, 4),
            "twilio_cost_inr": round(twilio_cost_inr, 2),
            "total_usd": round(total_usd, 4),
            "total_inr": round(total_inr, 2),
            "currency": self.currency,
            "total": round(total_inr if self.currency == "INR" else total_usd, 2),
            "duration_minutes": duration_minutes,
            "breakdown": {
                "asr": round(asr_cost_usd, 4),
                "llm": round(llm_cost_usd, 4),
                "tts": round(tts_cost_usd, 4),
                "twilio": round(twilio_cost_usd, 4)
            },
            "providers": {
                "asr": f"{asr_provider}/{asr_model}",
                "llm": f"{llm_provider}/{llm_model}",
                "tts": f"{tts_provider}/{tts_model}"
            }
        }

    def get_per_minute_estimate(
        self,
        is_realtime: bool,
        model: Optional[str] = None,
        asr_provider: Optional[str] = None,
        asr_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        tts_provider: Optional[str] = None,
        tts_model: Optional[str] = None
    ) -> Dict[str, float]:
        """Get estimated cost per minute for configuration"""
        if is_realtime:
            model = model or "gpt-4o-realtime"
            return self.calculate_realtime_api_cost(model, 1.0)
        else:
            return self.calculate_custom_pipeline_cost(
                asr_provider or "deepgram",
                asr_model or "nova-2",
                llm_provider or "openai",
                llm_model or "gpt-4o-mini",
                tts_provider or "openai",
                tts_model or "tts-1",
                1.0
            )


def get_currency_symbol(currency: str) -> str:
    """Get currency symbol"""
    return "₹" if currency == "INR" else "$"


def format_cost(amount: float, currency: str) -> str:
    """Format cost with currency symbol"""
    symbol = get_currency_symbol(currency)
    return f"{symbol}{amount:.2f}"
