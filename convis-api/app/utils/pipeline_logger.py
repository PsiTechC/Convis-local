"""
Pipeline Debug Logger
Generates readable debug logs for each call showing:
  - Models used
  - Overall performance
  - Turn-by-turn breakdown with sentences and timing
  - Full transcript
  - Smart conclusion with automatic issue detection
"""

import os
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Log directory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "pipeline")
os.makedirs(LOG_DIR, exist_ok=True)

# Thresholds for issue detection
ASR_SLOW_MS = 1500
LLM_SLOW_MS = 3000
TTS_SLOW_MS = 800
LONG_RESPONSE_CHARS = 150  # Bot response too long for phone call
MAX_GOOD_TURN_MS = 2500    # Total turn time should be under 2.5s

HALLUCINATION_PHRASES = [
    "thank you", "thanks", "bye", "goodbye", "i love", "hip-hop",
    "subscribe", "like and subscribe", "see you next time",
    "the end", "music", "applause", "bye-bye, everyone",
    "bye, snowball", "i love that", "and then"
]

GOODBYE_PHRASES = [
    "bye", "goodbye", "bye-bye", "okay bye", "thank you bye",
    "that's all", "nothing else", "no thanks bye"
]


def _detect_hallucination(text: str) -> bool:
    """Check if text looks like a Whisper hallucination."""
    if not text:
        return False
    text_lower = text.strip().lower().rstrip(".")
    for phrase in HALLUCINATION_PHRASES:
        if text_lower == phrase or text_lower == phrase + ".":
            return True
    return False


def _detect_goodbye(text: str) -> bool:
    """Check if user is saying goodbye."""
    if not text:
        return False
    text_lower = text.strip().lower().rstrip(".")
    for phrase in GOODBYE_PHRASES:
        if phrase in text_lower:
            return True
    return False


def _has_numbered_list(text: str) -> bool:
    """Check if bot response contains numbered lists."""
    return bool(re.search(r'\d+[\.\)]\s', text))


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

        # Collect timing per turn
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
        warnings = []
        hallucination_count = 0
        slow_llm_count = 0
        slow_asr_count = 0
        slow_tts_count = 0
        verbose_count = 0
        list_count = 0
        ignored_answer_count = 0
        goodbye_ignored = False

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
        lines.append(f"    (This is total pipeline processing time, not call length)")
        lines.append("")

        # ── TURN-BY-TURN BREAKDOWN ──
        lines.append("--- TURN-BY-TURN BREAKDOWN ---")
        lines.append("  (Each turn = User speaks -> Whisper listens -> Ollama thinks -> Piper speaks)")
        lines.append("")

        for idx, turn in enumerate(turns):
            turn_num = idx + 1
            timing = turn_timings.get(turn_num, {})
            asr_ms = timing.get("asr", 0)
            llm_ms = timing.get("llm", 0)
            tts_ms = timing.get("tts", 0)
            total_turn_ms = asr_ms + llm_ms + tts_ms

            # ── Issue detection per turn ──
            is_hallucination = _detect_hallucination(turn["user"])
            if is_hallucination:
                hallucination_count += 1

            is_verbose = len(turn["assistant"]) > LONG_RESPONSE_CHARS if turn["assistant"] else False
            if is_verbose:
                verbose_count += 1

            has_list = _has_numbered_list(turn["assistant"]) if turn["assistant"] else False
            if has_list:
                list_count += 1

            is_goodbye = _detect_goodbye(turn["user"])
            if is_goodbye and turn["assistant"] and not any(g in turn["assistant"].lower() for g in ["bye", "great day", "goodbye"]):
                goodbye_ignored = True

            if asr_ms > ASR_SLOW_MS:
                slow_asr_count += 1
            if llm_ms > LLM_SLOW_MS:
                slow_llm_count += 1
            if tts_ms > TTS_SLOW_MS:
                slow_tts_count += 1

            # Check if bot asked same question as previous turn
            if idx > 0 and turn["assistant"] and turns[idx-1]["assistant"]:
                if turn["assistant"][:50] == turns[idx-1]["assistant"][:50]:
                    ignored_answer_count += 1

            # ── Write turn ──
            turn_issues = []
            lines.append(f"  Turn {turn_num}:")

            if turn["user"]:
                halluc_tag = ""
                if is_hallucination:
                    halluc_tag = " [!!! LIKELY HALLUCINATION - Whisper misheard noise as speech]"
                lines.append(f"    You said      : \"{turn['user']}\"{halluc_tag}")

            if turn["assistant"]:
                resp_preview = turn['assistant'][:100]
                if len(turn['assistant']) > 100:
                    resp_preview += "..."
                lines.append(f"    Bot replied   : \"{resp_preview}\"")

                if is_verbose:
                    turn_issues.append("BOT TOO VERBOSE - Response too long for phone call")
                if has_list:
                    turn_issues.append("BOT USED NUMBERED LIST - Bad for voice calls")

            # Timing
            if asr_ms > 0 or llm_ms > 0 or tts_ms > 0:
                lines.append(f"    Timing:")
                if asr_ms > 0:
                    tag = " [SLOW!]" if asr_ms > ASR_SLOW_MS else ""
                    lines.append(f"      Whisper (listening)  : {asr_ms:.0f}ms ({_ms_to_seconds(asr_ms)}){tag}")
                if llm_ms > 0:
                    tag = " [SLOW!]" if llm_ms > LLM_SLOW_MS else ""
                    lines.append(f"      Ollama (thinking)    : {llm_ms:.0f}ms ({_ms_to_seconds(llm_ms)}){tag}")
                if tts_ms > 0:
                    tag = " [SLOW!]" if tts_ms > TTS_SLOW_MS else ""
                    lines.append(f"      Piper (speaking)     : {tts_ms:.0f}ms ({_ms_to_seconds(tts_ms)}){tag}")
                if total_turn_ms > 0:
                    tag = " [SLOW TURN!]" if total_turn_ms > MAX_GOOD_TURN_MS else ""
                    lines.append(f"      Total for this turn  : {total_turn_ms:.0f}ms ({_ms_to_seconds(total_turn_ms)}){tag}")
            else:
                lines.append(f"    Timing: Not recorded")

            if turn_issues:
                for ti in turn_issues:
                    lines.append(f"    >>> ISSUE: {ti}")

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
        lines.append("=" * 70)
        lines.append("  CONCLUSION - AUTOMATIC ISSUE DETECTION")
        lines.append("=" * 70)
        lines.append("")

        # Detect all issues
        if hallucination_count > 0:
            issues.append(
                f"WHISPER PROBLEM: {hallucination_count} hallucination(s) detected.\n"
                f"    What happened : Whisper heard noise/silence and invented words like 'Thank you'\n"
                f"    Why           : Whisper model too small or background noise too high\n"
                f"    Fix           : Use Whisper Medium or Large-v3 model, or use earphones when testing"
            )

        if slow_llm_count > 0:
            issues.append(
                f"OLLAMA PROBLEM: {slow_llm_count} slow response(s) over {LLM_SLOW_MS}ms.\n"
                f"    What happened : Bot took too long to think of a reply\n"
                f"    Why           : First call after restart (cold start) or max tokens too high\n"
                f"    Fix           : Warm up Ollama before calls, reduce max tokens to 50-75"
            )

        if slow_asr_count > 0:
            issues.append(
                f"WHISPER PROBLEM: {slow_asr_count} slow transcription(s) over {ASR_SLOW_MS}ms.\n"
                f"    What happened : Whisper took too long to convert your speech to text\n"
                f"    Why           : Large Whisper model or GPU overloaded\n"
                f"    Fix           : Use a smaller Whisper model or check GPU usage with nvidia-smi"
            )

        if slow_tts_count > 0:
            issues.append(
                f"PIPER PROBLEM: {slow_tts_count} slow synthesis over {TTS_SLOW_MS}ms.\n"
                f"    What happened : Piper took too long to convert text to speech\n"
                f"    Why           : Bot response was too long (many words to speak)\n"
                f"    Fix           : Reduce max tokens so bot gives shorter replies"
            )

        if verbose_count > 0:
            issues.append(
                f"BOT TOO VERBOSE: {verbose_count} response(s) were too long for a phone call.\n"
                f"    What happened : Bot gave long paragraph replies instead of short sentences\n"
                f"    Why           : Max tokens too high or system prompt not strict enough\n"
                f"    Fix           : Set max tokens to 50, add 'ONE short sentence per reply' to prompt"
            )

        if list_count > 0:
            issues.append(
                f"BOT USED LISTS: {list_count} response(s) contained numbered lists.\n"
                f"    What happened : Bot said '1. ... 2. ... 3. ...' which is bad for voice\n"
                f"    Why           : System prompt allows listing or max tokens too high\n"
                f"    Fix           : Add 'Never use numbered lists' to system prompt"
            )

        if ignored_answer_count > 0:
            issues.append(
                f"BOT MEMORY PROBLEM: Bot repeated the same question {ignored_answer_count} time(s).\n"
                f"    What happened : User already answered but bot asked the same thing again\n"
                f"    Why           : LLM model too small (can't remember context) or Whisper misheard\n"
                f"    Fix           : Use Llama 3.1 8B instead of 3B, or check if Whisper heard correctly"
            )

        if goodbye_ignored:
            issues.append(
                f"BOT IGNORED GOODBYE: User said bye but bot kept talking.\n"
                f"    What happened : User wanted to end the call but bot continued with more questions\n"
                f"    Why           : Bot interpreted goodbye as something else\n"
                f"    Fix           : Add 'When user says bye, say goodbye and stop' to system prompt"
            )

        if len(turns) <= 1:
            issues.append(
                f"CALL FAILED: Only {len(turns)} turn(s). Call ended too quickly.\n"
                f"    What happened : Bot greeted but no conversation happened\n"
                f"    Why           : VAD not detecting speech, webhook failure, or call disconnected\n"
                f"    Fix           : Check if VAD is working, check Twilio webhook URLs, check server logs"
            )

        # Check bot repeated itself
        bot_responses = [t["assistant"] for t in turns if t["assistant"]]
        if len(bot_responses) > 2:
            repeated = len(bot_responses) - len(set(bot_responses))
            if repeated > 0:
                issues.append(
                    f"BOT LOOPING: Bot gave the exact same response {repeated} time(s).\n"
                    f"    What happened : Bot got stuck in a loop repeating itself\n"
                    f"    Why           : LLM too small or system prompt too complex\n"
                    f"    Fix           : Use Llama 3.1 8B, simplify system prompt, reduce max tokens"
                )

        # Write conclusion
        if issues:
            lines.append(f"  ISSUES FOUND: {len(issues)}")
            lines.append("")
            for i, issue in enumerate(issues):
                lines.append(f"  Issue {i+1}:")
                for issue_line in issue.split("\n"):
                    lines.append(f"    {issue_line}")
                lines.append("")
        else:
            lines.append("  NO ISSUES DETECTED")
            lines.append("")
            lines.append("  Call completed successfully. All models performed within normal range.")
            lines.append(f"  Average response time: {session_ms / max(len(turns), 1):.0f}ms per turn")

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
            logger.warning(f"[PIPELINE_LOG] {len(issues)} issue(s) detected in call {call_sid}")
        else:
            logger.info(f"[PIPELINE_LOG] No issues detected in call {call_sid}")

        return filepath

    except Exception as e:
        logger.error(f"[PIPELINE_LOG] Failed to generate log: {e}")
        return None
