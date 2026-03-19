# Call Handlers Package
# Provides legacy, optimized, and ultra-low-latency streaming handlers

from .custom_provider_stream import CustomProviderStreamHandler
from .optimized_stream_handler import OptimizedStreamHandler, handle_optimized_stream
from .streaming_asr_handler import StreamingDeepgramASR
from .streaming_llm_handler import StreamingLLMHandler, ConversationManager
from .streaming_tts_handler import StreamingElevenLabsTTS, StreamingOpenAITTS
from .offline_asr_handler import OfflineWhisperASR
from .offline_tts_handler import OfflinePiperTTS

# Ultra-low-latency streaming (word-by-word for ElevenLabs, chunked for Sarvam)
from .elevenlabs_websocket_tts import ElevenLabsWebSocketTTS
from .sarvam_streaming_tts import SarvamStreamingTTS
from .ultra_low_latency_handler import UltraLowLatencyHandler, handle_ultra_low_latency_stream

__all__ = [
    # Legacy handler (sentence-by-sentence, ~1500-3000ms)
    "CustomProviderStreamHandler",

    # Optimized handlers (sentence-by-sentence streaming, ~300-600ms)
    "OptimizedStreamHandler",
    "handle_optimized_stream",
    "StreamingDeepgramASR",
    "StreamingLLMHandler",
    "ConversationManager",
    "StreamingElevenLabsTTS",
    "StreamingOpenAITTS",
    "OfflineWhisperASR",
    "OfflinePiperTTS",

    # Ultra-low-latency handlers
    # ElevenLabs: word-by-word streaming (~100-200ms)
    # Sarvam: chunked streaming (~200-400ms, best Hindi quality)
    "ElevenLabsWebSocketTTS",
    "SarvamStreamingTTS",
    "UltraLowLatencyHandler",
    "handle_ultra_low_latency_stream",
]









