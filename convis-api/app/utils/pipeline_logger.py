"""
Pipeline Debug Logger
Generates readable debug logs for each call showing latency of each component:
  ASR (Whisper) → LLM (Ollama) → TTS (Piper)
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Log directory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "pipeline")
os.makedirs(LOG_DIR, exist_ok=True)


def generate_pipeline_log(call_sid: str, execution_logs: dict, transcript: str = ""):
    """
    Generate a readable pipeline debug log file for a call.

    Args:
        call_sid: Twilio call SID
        execution_logs: The execution_logs dict from optimized_stream_handler
        transcript: Plain text transcript
    """
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"call_{call_sid}_{timestamp}.log"
        filepath = os.path.join(LOG_DIR, filename)

        providers = execution_logs.get("providers", {})
        models = execution_logs.get("models", {})
        perf = execution_logs.get("performance_metrics", {})
        stats = perf.get("stats", {})
        metrics = perf.get("metrics", [])

        lines = []
        lines.append("=" * 70)
        lines.append(f"  PIPELINE DEBUG LOG - Call: {call_sid}")
        lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
        lines.append("=" * 70)
        lines.append("")

        # Models used
        lines.append("--- MODELS USED ---")
        lines.append(f"  ASR (Speech-to-Text) : {providers.get('asr', 'N/A')} / {models.get('asr_model', 'N/A')}")
        lines.append(f"  LLM (AI Brain)       : {providers.get('llm', 'N/A')} / {models.get('llm_model', 'N/A')}")
        lines.append(f"  TTS (Text-to-Speech) : {providers.get('tts', 'N/A')} / {models.get('tts_voice', 'N/A')}")
        lines.append("")

        # Overall stats
        lines.append("--- OVERALL PERFORMANCE ---")
        lines.append(f"  Total turns          : {perf.get('total_turns', 'N/A')}")
        lines.append(f"  Session duration     : {perf.get('session_duration_ms', 0):.0f}ms")
        lines.append("")

        # Per-component stats
        if "asr" in stats:
            asr = stats["asr"]
            lines.append("--- ASR (Whisper) LATENCY ---")
            lines.append(f"  Average : {asr.get('avg_ms', 0):.0f}ms")
            lines.append(f"  Min     : {asr.get('min_ms', 0):.0f}ms")
            lines.append(f"  Max     : {asr.get('max_ms', 0):.0f}ms")
            lines.append(f"  Count   : {asr.get('count', 0)} transcriptions")
            lines.append("")

        if "llm" in stats:
            llm = stats["llm"]
            lines.append("--- LLM (Ollama) LATENCY ---")
            lines.append(f"  Average : {llm.get('avg_ms', 0):.0f}ms")
            lines.append(f"  Min     : {llm.get('min_ms', 0):.0f}ms")
            lines.append(f"  Max     : {llm.get('max_ms', 0):.0f}ms")
            lines.append(f"  Count   : {llm.get('count', 0)} responses")
            lines.append("")

        if "tts" in stats:
            tts = stats["tts"]
            lines.append("--- TTS (Piper) LATENCY ---")
            lines.append(f"  Average : {tts.get('avg_ms', 0):.0f}ms")
            lines.append(f"  Min     : {tts.get('min_ms', 0):.0f}ms")
            lines.append(f"  Max     : {tts.get('max_ms', 0):.0f}ms")
            lines.append(f"  Count   : {tts.get('count', 0)} syntheses")
            lines.append("")

        # Turn-by-turn breakdown
        lines.append("--- TURN-BY-TURN BREAKDOWN ---")
        current_turn = 0
        for m in metrics:
            turn = m.get("turn", 0)
            if turn != current_turn:
                current_turn = turn
                lines.append(f"")
                lines.append(f"  Turn {turn}:")
            op = m.get("operation", "")
            elapsed = m.get("elapsed_ms", 0)

            if op == "asr":
                lines.append(f"    [ASR]  Whisper transcription : {elapsed:.0f}ms")
            elif op == "llm":
                lines.append(f"    [LLM]  Ollama response       : {elapsed:.0f}ms")
            elif op == "tts":
                lines.append(f"    [TTS]  Piper synthesis        : {elapsed:.0f}ms")
        lines.append("")

        # Transcript
        if transcript:
            lines.append("--- TRANSCRIPT ---")
            for line in transcript.strip().split("\n"):
                lines.append(f"  {line}")
            lines.append("")

        lines.append("=" * 70)
        lines.append("  END OF LOG")
        lines.append("=" * 70)

        # Write to file
        log_content = "\n".join(lines)
        with open(filepath, "w") as f:
            f.write(log_content)

        # Also log to console
        logger.info(f"[PIPELINE_LOG] Debug log saved: {filepath}")
        logger.info(f"[PIPELINE_LOG] Summary - ASR: {stats.get('asr', {}).get('avg_ms', 'N/A')}ms avg | LLM: {stats.get('llm', {}).get('avg_ms', 'N/A')}ms avg | TTS: {stats.get('tts', {}).get('avg_ms', 'N/A')}ms avg")

        return filepath

    except Exception as e:
        logger.error(f"[PIPELINE_LOG] Failed to generate log: {e}")
        return None
