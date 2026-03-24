"""
Pipeline Debug Logger
Generates readable debug logs for each call showing:
  - Models used
  - Overall performance
  - Turn-by-turn breakdown with sentences and timing
  - Full transcript
  - Conclusion with issue detection
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Log directory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "pipeline")
os.makedirs(LOG_DIR, exist_ok=True)

# Thresholds for issue detection
ASR_SLOW_MS = 1500       # Whisper taking more than 1.5s is slow
LLM_SLOW_MS = 3000       # LLM taking more than 3s is slow
TTS_SLOW_MS = 800        # TTS taking more than 0.8s is slow
HALLUCINATION_PHRASES = [
    "thank you", "thanks", "bye", "goodbye", "i love", "hip-hop",
    "subscribe", "like and subscribe", "see you next time",
    "the end", "music", "applause"
]


def _detect_hallucination(text: str) -> bool:
    """Check if text looks like a Whisper hallucination."""
    if not text:
        return False
    text_lower = text.strip().lower()
    # Very short generic phrases on their own are likely hallucinations
    for phrase in HALLUCINATION_PHRASES:
        if text_lower == phrase or text_lower == phrase + ".":
            return True
    return False


def _ms_to_seconds(ms: float) -> str:
    """Convert milliseconds to readable seconds string."""
    return f"{ms / 1000:.1f}s"


def generate_pipeline_log(call_sid: str, execution_logs: dict, transcript: str = ""):
    """
    Generate a readable pipeline debug log file for a call.
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
        session_ms = perf.get("session_duration_ms", 0)

        # Parse transcript into turn pairs
        transcript_lines = []
        if transcript:
            for line in transcript.strip().split("\n"):
                line = line.strip()
                if line:
                    transcript_lines.append(line)

        # Build user/assistant pairs
        turns = []
        i = 0
        while i < len(transcript_lines):
            user_text = ""
            assistant_text = ""
            if transcript_lines[i].startswith("USER:"):
                user_text = transcript_lines[i].replace("USER:", "").strip()
                if i + 1 < len(transcript_lines) and transcript_lines[i + 1].startswith("ASSISTANT:"):
                    assistant_text = transcript_lines[i + 1].replace("ASSISTANT:", "").strip()
                    i += 2
                else:
                    i += 1
            elif transcript_lines[i].startswith("ASSISTANT:"):
                assistant_text = transcript_lines[i].replace("ASSISTANT:", "").strip()
                i += 1
            else:
                i += 1
                continue
            turns.append({"user": user_text, "assistant": assistant_text})

        # Collect timing per turn from metrics
        turn_timings = {}
        for m in metrics:
            turn_num = m.get("turn", 0)
            if turn_num not in turn_timings:
                turn_timings[turn_num] = {}
            op = m.get("operation", "")
            elapsed = m.get("elapsed_ms", 0)
            turn_timings[turn_num][op] = elapsed

        # Issue tracking
        issues = []
        hallucination_count = 0
        slow_llm_count = 0
        slow_asr_count = 0
        slow_tts_count = 0

        lines = []
        lines.append("=" * 70)
        lines.append(f"  PIPELINE DEBUG LOG")
        lines.append(f"  Call ID  : {call_sid}")
        lines.append(f"  Date     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("=" * 70)
        lines.append("")

        # ── MODELS USED ──
        lines.append("--- MODELS USED ---")
        lines.append(f"  Whisper (ASR)  : {providers.get('asr', 'N/A')} / {models.get('asr_model', 'N/A')}")
        lines.append(f"  Ollama (LLM)   : {providers.get('llm', 'N/A')} / {models.get('llm_model', 'N/A')}")
        lines.append(f"  Piper (TTS)    : {providers.get('tts', 'N/A')} / {models.get('tts_voice', 'N/A')}")
        lines.append("")

        # ── OVERALL PERFORMANCE ──
        lines.append("--- OVERALL PERFORMANCE ---")
        lines.append(f"  Total turns       : {perf.get('total_turns', 0)}")
        lines.append(f"  Session duration  : {session_ms:.0f}ms ({_ms_to_seconds(session_ms)})")
        lines.append("")

        # ── TURN-BY-TURN BREAKDOWN ──
        lines.append("--- TURN-BY-TURN BREAKDOWN ---")
        lines.append("  (Each turn = User speaks → Whisper listens → Ollama thinks → Piper speaks)")
        lines.append("")

        for idx, turn in enumerate(turns):
            turn_num = idx + 1
            timing = turn_timings.get(turn_num, {})
            asr_ms = timing.get("asr", 0)
            llm_ms = timing.get("llm", 0)
            tts_ms = timing.get("tts", 0)
            total_turn_ms = asr_ms + llm_ms + tts_ms

            # Check for issues
            is_hallucination = _detect_hallucination(turn["user"])
            if is_hallucination:
                hallucination_count += 1
            if asr_ms > ASR_SLOW_MS:
                slow_asr_count += 1
            if llm_ms > LLM_SLOW_MS:
                slow_llm_count += 1
            if tts_ms > TTS_SLOW_MS:
                slow_tts_count += 1

            lines.append(f"  Turn {turn_num}:")
            if turn["user"]:
                halluc_tag = " [HALLUCINATION?]" if is_hallucination else ""
                lines.append(f"    User said    : \"{turn['user']}\"{halluc_tag}")
            if turn["assistant"]:
                lines.append(f"    Bot replied  : \"{turn['assistant'][:80]}{'...' if len(turn['assistant']) > 80 else ''}\"")

            # Timing breakdown
            if asr_ms > 0 or llm_ms > 0 or tts_ms > 0:
                lines.append(f"    Timing:")
                if asr_ms > 0:
                    slow_tag = " (SLOW!)" if asr_ms > ASR_SLOW_MS else ""
                    lines.append(f"      Whisper (listening)  : {asr_ms:.0f}ms ({_ms_to_seconds(asr_ms)}){slow_tag}")
                if llm_ms > 0:
                    slow_tag = " (SLOW!)" if llm_ms > LLM_SLOW_MS else ""
                    lines.append(f"      Ollama (thinking)    : {llm_ms:.0f}ms ({_ms_to_seconds(llm_ms)}){slow_tag}")
                if tts_ms > 0:
                    slow_tag = " (SLOW!)" if tts_ms > TTS_SLOW_MS else ""
                    lines.append(f"      Piper (speaking)     : {tts_ms:.0f}ms ({_ms_to_seconds(tts_ms)}){slow_tag}")
                if total_turn_ms > 0:
                    lines.append(f"      Total for this turn  : {total_turn_ms:.0f}ms ({_ms_to_seconds(total_turn_ms)})")
            else:
                lines.append(f"    Timing: Not recorded for this turn")

            lines.append("")

        # ── FULL TRANSCRIPT ──
        lines.append("--- FULL TRANSCRIPT ---")
        if transcript:
            for line in transcript.strip().split("\n"):
                line = line.strip()
                if line.startswith("USER:"):
                    lines.append(f"  [YOU]  {line.replace('USER:', '').strip()}")
                elif line.startswith("ASSISTANT:"):
                    lines.append(f"  [BOT]  {line.replace('ASSISTANT:', '').strip()}")
                elif line:
                    lines.append(f"         {line}")
        else:
            lines.append("  No transcript available")
        lines.append("")

        # ── CONCLUSION ──
        lines.append("--- CONCLUSION ---")

        # Detect issues
        if hallucination_count > 0:
            issues.append(f"WHISPER ISSUE: {hallucination_count} possible hallucination(s) detected. "
                         f"Whisper misheard silence/noise as words. "
                         f"Fix: Use a larger Whisper model (medium/large-v3) or reduce background noise.")

        if slow_llm_count > 0:
            issues.append(f"OLLAMA ISSUE: {slow_llm_count} slow response(s) detected (>{LLM_SLOW_MS}ms). "
                         f"Fix: Reduce max tokens, use a smaller model, or warm up Ollama before calls.")

        if slow_asr_count > 0:
            issues.append(f"WHISPER ISSUE: {slow_asr_count} slow transcription(s) detected (>{ASR_SLOW_MS}ms). "
                         f"Fix: Use a smaller Whisper model or check GPU load.")

        if slow_tts_count > 0:
            issues.append(f"PIPER ISSUE: {slow_tts_count} slow synthesis(es) detected (>{TTS_SLOW_MS}ms). "
                         f"Fix: Use shorter bot responses (reduce max tokens).")

        if len(turns) <= 1:
            issues.append("CALL ISSUE: Only 1 turn or less. The call ended too quickly. "
                         "Possible causes: VAD not detecting speech, Twilio webhook failure, or call disconnected.")

        # Check if bot repeated itself
        bot_responses = [t["assistant"] for t in turns if t["assistant"]]
        if len(bot_responses) > 2:
            repeated = len(bot_responses) - len(set(bot_responses))
            if repeated > 0:
                issues.append(f"LLM ISSUE: Bot repeated the same response {repeated} time(s). "
                             f"Fix: Use a larger LLM model (8B+) that remembers context better.")

        if issues:
            for issue in issues:
                lines.append(f"  ! {issue}")
        else:
            lines.append("  No issues detected. Call completed successfully.")

        lines.append("")
        lines.append("=" * 70)
        lines.append("  END OF LOG")
        lines.append("=" * 70)

        # Write to file
        log_content = "\n".join(lines)
        with open(filepath, "w") as f:
            f.write(log_content)

        # Console summary
        logger.info(f"[PIPELINE_LOG] Debug log saved: {filepath}")
        if issues:
            for issue in issues:
                logger.warning(f"[PIPELINE_LOG] {issue}")
        else:
            logger.info(f"[PIPELINE_LOG] No issues detected")

        return filepath

    except Exception as e:
        logger.error(f"[PIPELINE_LOG] Failed to generate log: {e}")
        return None
