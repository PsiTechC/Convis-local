"""
Performance Monitor - Track millisecond-level timing for call workflows
Provides detailed visibility into ASR, LLM, TTS, and overall pipeline performance

Key Metrics (Vapi-aligned):
- TTFT (Time To First Token): Time from user speech end to first audio byte
- ASR Latency: Speech-to-text processing time
- LLM Latency: AI response generation time
- TTS Latency: Text-to-speech synthesis time
- Speculative Hit Rate: % of predict-and-scrap successes
"""

import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Tracks performance metrics for voice call pipeline with millisecond precision.

    Monitors:
    - Audio buffering time
    - ASR (Speech-to-Text) latency
    - LLM (AI Response) latency
    - TTS (Text-to-Speech) latency
    - Audio conversion time
    - Total end-to-end latency
    - Network/transport overhead
    """

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.metrics: List[Dict[str, Any]] = []
        self.current_turn = 0
        self.session_start = time.time()

        # Track cumulative stats
        self.total_turns = 0
        self.total_asr_time = 0
        self.total_llm_time = 0
        self.total_tts_time = 0

        # Vapi-style metrics
        self.ttft_times: List[float] = []  # Time To First Token (audio)
        self.speculative_attempts = 0
        self.speculative_hits = 0  # Used without re-processing

        logger.info(f"[PERF-MONITOR] 📊 Performance monitoring started for call {call_id}")

    def record_ttft(self, ttft_ms: float):
        """Record Time To First Token (first audio byte after user speech)"""
        self.ttft_times.append(ttft_ms)
        logger.info(f"[PERF] ⚡ TTFT (Time To First Token): {ttft_ms:.0f}ms")

    def record_speculative_attempt(self):
        """Record a speculative (predict-and-scrap) processing attempt"""
        self.speculative_attempts += 1

    def record_speculative_hit(self):
        """Record when speculative processing was used (not scrapped)"""
        self.speculative_hits += 1
        logger.info(f"[PERF] 🎯 Speculative hit! ({self.speculative_hits}/{self.speculative_attempts})")

    @contextmanager
    def track(self, operation: str, metadata: Optional[Dict] = None):
        """
        Context manager to track timing of any operation

        Usage:
            with perf_monitor.track('asr', {'audio_size': 1600}):
                result = await transcribe(audio)
        """
        start_time = time.time()
        start_timestamp = datetime.now().isoformat()

        try:
            yield
        finally:
            end_time = time.time()
            elapsed_ms = (end_time - start_time) * 1000

            metric = {
                'operation': operation,
                'start_timestamp': start_timestamp,
                'elapsed_ms': round(elapsed_ms, 2),
                'turn': self.current_turn,
                'metadata': metadata or {}
            }

            self.metrics.append(metric)
            self._log_metric(metric)

    def _log_metric(self, metric: Dict[str, Any]):
        """Log individual metric with emoji indicators"""
        emoji_map = {
            'audio_buffer': '🎙️',
            'asr': '🔊',
            'llm': '🤖',
            'tts': '🔉',
            'audio_convert': '🔄',
            'total_pipeline': '⚡',
            'greeting': '👋',
            'translation': '🌍',
            'network': '🌐'
        }

        emoji = emoji_map.get(metric['operation'], '📌')
        op_name = metric['operation'].replace('_', ' ').title()

        logger.info(
            f"[PERF] {emoji} {op_name}: {metric['elapsed_ms']:.0f}ms "
            f"(Turn {metric['turn']}) {self._format_metadata(metric['metadata'])}"
        )

    def _format_metadata(self, metadata: Dict) -> str:
        """Format metadata for logging"""
        if not metadata:
            return ""

        parts = []
        for key, value in metadata.items():
            if key == 'text_length':
                parts.append(f"{value} chars")
            elif key == 'audio_size':
                parts.append(f"{value} bytes")
            elif key == 'provider':
                parts.append(f"[{value}]")
            elif key == 'model':
                parts.append(f"model:{value}")

        return f"({', '.join(parts)})" if parts else ""

    def start_turn(self):
        """Mark the start of a new conversation turn"""
        self.current_turn += 1
        self.turn_start_time = time.time()
        logger.info(f"[PERF] 🔄 === TURN {self.current_turn} START ===")

    def end_turn(self):
        """Mark the end of a conversation turn and log summary"""
        if not hasattr(self, 'turn_start_time'):
            return

        turn_time = (time.time() - self.turn_start_time) * 1000

        # Get metrics for this turn
        turn_metrics = [m for m in self.metrics if m['turn'] == self.current_turn]

        # Calculate breakdown
        asr_time = sum(m['elapsed_ms'] for m in turn_metrics if m['operation'] == 'asr')
        llm_time = sum(m['elapsed_ms'] for m in turn_metrics if m['operation'] == 'llm')
        tts_time = sum(m['elapsed_ms'] for m in turn_metrics if m['operation'] == 'tts')

        logger.info(f"[PERF] ⚡ === TURN {self.current_turn} SUMMARY ===")
        logger.info(f"[PERF]   ASR:   {asr_time:.0f}ms")
        logger.info(f"[PERF]   LLM:   {llm_time:.0f}ms")
        logger.info(f"[PERF]   TTS:   {tts_time:.0f}ms")
        logger.info(f"[PERF]   TOTAL: {turn_time:.0f}ms")
        logger.info(f"[PERF] ⚡ === END TURN {self.current_turn} ===")

        # Update cumulative stats
        self.total_turns += 1
        self.total_asr_time += asr_time
        self.total_llm_time += llm_time
        self.total_tts_time += tts_time

    def log_session_summary(self):
        """Log summary of entire call session"""
        session_duration = (time.time() - self.session_start) * 1000

        logger.info(f"[PERF] 📊 === CALL SESSION SUMMARY ===")
        logger.info(f"[PERF] Call ID: {self.call_id}")
        logger.info(f"[PERF] Total Turns: {self.total_turns}")
        logger.info(f"[PERF] Session Duration: {session_duration:.0f}ms")

        if self.total_turns > 0:
            avg_asr = self.total_asr_time / self.total_turns
            avg_llm = self.total_llm_time / self.total_turns
            avg_tts = self.total_tts_time / self.total_turns

            logger.info(f"[PERF] Average ASR: {avg_asr:.0f}ms")
            logger.info(f"[PERF] Average LLM: {avg_llm:.0f}ms")
            logger.info(f"[PERF] Average TTS: {avg_tts:.0f}ms")
            logger.info(f"[PERF] Average Total: {(avg_asr + avg_llm + avg_tts):.0f}ms")

        # TTFT metrics (Vapi-style)
        if self.ttft_times:
            avg_ttft = sum(self.ttft_times) / len(self.ttft_times)
            min_ttft = min(self.ttft_times)
            max_ttft = max(self.ttft_times)
            logger.info(f"[PERF] ⚡ TTFT - Avg: {avg_ttft:.0f}ms, Min: {min_ttft:.0f}ms, Max: {max_ttft:.0f}ms")

        # Speculative processing metrics (predict-and-scrap)
        if self.speculative_attempts > 0:
            hit_rate = (self.speculative_hits / self.speculative_attempts) * 100
            logger.info(f"[PERF] 🔮 Speculative Processing: {self.speculative_hits}/{self.speculative_attempts} hits ({hit_rate:.1f}%)")

        logger.info(f"[PERF] 📊 === END SESSION SUMMARY ===")

    def get_metrics(self) -> List[Dict[str, Any]]:
        """Get all collected metrics"""
        return self.metrics

    def get_turn_metrics(self, turn: int) -> List[Dict[str, Any]]:
        """Get metrics for a specific turn"""
        return [m for m in self.metrics if m['turn'] == turn]

    def get_operation_stats(self, operation: str) -> Dict[str, float]:
        """Get statistics for a specific operation"""
        op_metrics = [m for m in self.metrics if m['operation'] == operation]

        if not op_metrics:
            return {}

        times = [m['elapsed_ms'] for m in op_metrics]

        return {
            'count': len(times),
            'total_ms': sum(times),
            'avg_ms': sum(times) / len(times),
            'min_ms': min(times),
            'max_ms': max(times)
        }

    def export_metrics(self) -> Dict[str, Any]:
        """Export all metrics as a structured dict for logging/storage"""
        return {
            'call_id': self.call_id,
            'total_turns': self.total_turns,
            'session_duration_ms': (time.time() - self.session_start) * 1000,
            'metrics': self.metrics,
            'stats': {
                'asr': self.get_operation_stats('asr'),
                'llm': self.get_operation_stats('llm'),
                'tts': self.get_operation_stats('tts'),
                'audio_convert': self.get_operation_stats('audio_convert')
            }
        }


class DetailedCallLogger:
    """
    Provides detailed, timestamped logging of entire call workflow
    Logs every step with millisecond precision for debugging and optimization
    """

    def __init__(self, call_id: str, platform: str = "frejun"):
        self.call_id = call_id
        self.platform = platform
        self.start_time = datetime.now()
        self.events: List[Dict[str, Any]] = []

        self._log_event('CALL_START', {
            'platform': platform,
            'timestamp': self.start_time.isoformat()
        })

    def _log_event(self, event_type: str, data: Dict[str, Any] = None):
        """Log an event with timestamp"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'elapsed_ms': (datetime.now() - self.start_time).total_seconds() * 1000,
            'event': event_type,
            'data': data or {}
        }

        self.events.append(event)

        # Format log message
        elapsed = event['elapsed_ms']
        logger.info(f"[CALL-FLOW] [{elapsed:>7.0f}ms] {event_type}: {self._format_data(data)}")

    def _format_data(self, data: Dict) -> str:
        """Format event data for logging"""
        if not data:
            return ""

        parts = []
        for key, value in data.items():
            if isinstance(value, str) and len(value) > 50:
                value = value[:50] + "..."
            parts.append(f"{key}={value}")

        return " | ".join(parts)

    # Event logging methods
    def log_websocket_connected(self):
        self._log_event('WEBSOCKET_CONNECTED')

    def log_providers_initialized(self, asr: str, tts: str, llm: str):
        self._log_event('PROVIDERS_INITIALIZED', {
            'asr': asr,
            'tts': tts,
            'llm': llm
        })

    def log_greeting_sent(self, text: str, audio_size: int):
        self._log_event('GREETING_SENT', {
            'text_preview': text[:50],
            'audio_bytes': audio_size
        })

    def log_audio_received(self, size: int, buffer_total: int):
        self._log_event('AUDIO_RECEIVED', {
            'chunk_bytes': size,
            'buffer_total': buffer_total
        })

    def log_asr_start(self, audio_size: int):
        self._log_event('ASR_START', {'audio_bytes': audio_size})

    def log_asr_complete(self, transcript: str, duration_ms: float):
        self._log_event('ASR_COMPLETE', {
            'transcript': transcript,
            'duration_ms': round(duration_ms, 1)
        })

    def log_llm_start(self, prompt_length: int):
        self._log_event('LLM_START', {'prompt_chars': prompt_length})

    def log_llm_streaming(self, tokens_received: int):
        self._log_event('LLM_STREAMING', {'tokens': tokens_received})

    def log_llm_complete(self, response: str, duration_ms: float):
        self._log_event('LLM_COMPLETE', {
            'response': response,
            'duration_ms': round(duration_ms, 1)
        })

    def log_tts_start(self, text_length: int, provider: str):
        self._log_event('TTS_START', {
            'text_chars': text_length,
            'provider': provider
        })

    def log_tts_complete(self, audio_size: int, duration_ms: float):
        self._log_event('TTS_COMPLETE', {
            'audio_bytes': audio_size,
            'duration_ms': round(duration_ms, 1)
        })

    def log_audio_sent(self, size: int):
        self._log_event('AUDIO_SENT', {'bytes': size})

    def log_error(self, error_type: str, message: str):
        self._log_event('ERROR', {
            'type': error_type,
            'message': message
        })

    def log_call_end(self, reason: str = "normal"):
        duration = (datetime.now() - self.start_time).total_seconds()
        self._log_event('CALL_END', {
            'reason': reason,
            'total_duration_sec': round(duration, 2)
        })

    def export_timeline(self) -> List[Dict[str, Any]]:
        """Export complete timeline of events"""
        return self.events
