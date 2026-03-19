"""
Shared utilities for OpenAI Realtime API session management.
Used by both inbound and outbound call handlers.
"""
import json
import logging
import re
from typing import Optional

from app.constants import DEFAULT_CALL_GREETING

logger = logging.getLogger(__name__)

# Event types to log for debugging
LOG_EVENT_TYPES = [
    'response.content.done',
    'rate_limits.updated',
    'response.done',
    'response.created',
    'response.output_item.added',
    'response.output_item.done',
    'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started',
    'session.created',
    'session.updated',
    'response.audio.delta',
    'response.audio.done',
    'response.audio_transcript.delta',
    'response.audio_transcript.done',
    'response.output_audio.delta',
    'response.output_audio.done',
    'response.output_text.delta',
    'response.output_text.done',
    'conversation.item.created',
    'error'
]

async def send_session_update(
    openai_ws,
    system_message: str,
    voice: str,
    temperature: float = 0.8,
    enable_interruptions: bool = True,
    greeting_text: Optional[str] = None,
    max_response_output_tokens: Optional[int] = None,
    vad_threshold: float = 0.5,
    vad_prefix_padding_ms: int = 300,
    vad_silence_duration_ms: int = 500
):
    """
    Send session update to OpenAI WebSocket with dynamic configuration.
    CRITICAL: This matches the original pattern where send_initial_conversation_item
    is called INSIDE send_session_update for proper timing.

    Args:
        openai_ws: OpenAI WebSocket connection
        system_message: System instructions for the AI
        voice: Voice to use for output (e.g., 'alloy', 'echo', 'shimmer')
        temperature: Temperature for response generation (0.0-1.0)
        enable_interruptions: Whether to enable interruption handling
        greeting_text: Optional custom greeting text (passed to send_initial_conversation_item)
        max_response_output_tokens: Optional max tokens for AI responses (e.g., 'inf', 50-4096)
        vad_threshold: Voice Activity Detection threshold (0.0-1.0) - lower=more sensitive to background noise
        vad_prefix_padding_ms: Padding before speech starts (ms) - helps capture beginning of speech
        vad_silence_duration_ms: Silence duration to detect end of speech (ms) - longer=less affected by noise
    """
    session_config = {
        "turn_detection": {
            "type": "server_vad",
            "threshold": vad_threshold,  # Configurable VAD threshold for noise sensitivity
            "prefix_padding_ms": vad_prefix_padding_ms,  # Configurable padding before speech
            "silence_duration_ms": vad_silence_duration_ms  # Configurable silence detection - helps with noise handling
        },
        "input_audio_format": "g711_ulaw",
        "output_audio_format": "g711_ulaw",
        "voice": voice,
        "instructions": system_message,
        "modalities": ["audio", "text"],
        "temperature": temperature,
        "input_audio_transcription": {
            "model": "whisper-1"
        }
    }

    # Add max_response_output_tokens if specified
    if max_response_output_tokens is not None:
        session_config["max_response_output_tokens"] = max_response_output_tokens

    session_update = {
        "type": "session.update",
        "session": session_config
    }

    logger.info(f'Sending session update with voice={voice}, temperature={temperature}, max_tokens={max_response_output_tokens}')
    logger.info('Session modalities: ["audio", "text"], formats: g711_ulaw')
    await openai_ws.send(json.dumps(session_update))

    # CRITICAL: Call send_initial_conversation_item HERE, matching original pattern (line 223)
    # This ensures proper timing for OpenAI to start generating audio
    await send_initial_conversation_item(openai_ws, greeting_text)

async def send_initial_conversation_item(openai_ws, greeting_text: Optional[str] = None):
    """
    Send initial conversation item so AI speaks first.

    Args:
        openai_ws: OpenAI WebSocket connection
        greeting_text: Optional custom greeting text
    """
    if greeting_text is None or not greeting_text.strip():
        greeting_text = DEFAULT_CALL_GREETING
    else:
        greeting_text = greeting_text.strip()

    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": greeting_text
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    logger.info("Sent initial greeting to AI")

async def send_mark(websocket, stream_sid: str, mark_queue: list):
    """
    Send a mark event to track audio playback position.
    Used for precise interruption handling.

    Args:
        websocket: Twilio WebSocket connection
        stream_sid: Twilio stream SID
        mark_queue: Queue to track marks
    """
    if stream_sid:
        mark_event = {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": "responsePart"}
        }
        await websocket.send_json(mark_event)
        mark_queue.append('responsePart')

async def handle_interruption(
    openai_ws,
    twilio_ws,
    stream_sid: str,
    last_assistant_item: Optional[str],
    response_start_timestamp: Optional[int],
    latest_media_timestamp: int,
    mark_queue: list,
    show_timing_math: bool = False
):
    """
    Handle interruption when the caller's speech starts.
    Truncates the current AI response and clears the audio buffer.

    Args:
        openai_ws: OpenAI WebSocket connection
        twilio_ws: Twilio WebSocket connection
        stream_sid: Twilio stream SID
        last_assistant_item: ID of the last assistant message
        response_start_timestamp: Timestamp when response started
        latest_media_timestamp: Current media timestamp
        mark_queue: Queue of marks
        show_timing_math: Whether to log timing calculations

    Returns:
        Tuple of (last_assistant_item, response_start_timestamp) after reset
    """
    logger.info("Handling interruption - truncating AI response")

    if mark_queue and response_start_timestamp is not None:
        elapsed_time = latest_media_timestamp - response_start_timestamp

        if show_timing_math:
            logger.info(
                f"Calculating elapsed time for truncation: "
                f"{latest_media_timestamp} - {response_start_timestamp} = {elapsed_time}ms"
            )

        if last_assistant_item:
            if show_timing_math:
                logger.info(f"Truncating item with ID: {last_assistant_item}, at: {elapsed_time}ms")

            truncate_event = {
                "type": "conversation.item.truncate",
                "item_id": last_assistant_item,
                "content_index": 0,
                "audio_end_ms": elapsed_time
            }
            await openai_ws.send(json.dumps(truncate_event))

        # Clear Twilio's audio buffer
        await twilio_ws.send_json({
            "event": "clear",
            "streamSid": stream_sid
        })

        mark_queue.clear()
    logger.info("Cleared audio buffers and mark queue")

    return None, None  # Reset last_assistant_item and response_start_timestamp

async def inject_knowledge_base_context(openai_ws, context: str):
    """
    Inject knowledge base context as a system message into the conversation.

    Args:
        openai_ws: OpenAI WebSocket connection
        context: Knowledge base context to inject
    """
    context_message = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": context
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(context_message))
    logger.info("Injected knowledge base context")


HANGUP_INTENT_PATTERNS = [
    r"\bbye\b",
    r"\bgood\s*bye\b",
    r"\bsee\s+(you|ya|ya\s+later|you\s+later)\b",
    r"\bend\s+(the\s+)?call\b",
    r"\bhang\s*(up)?\b",
    r"\bthat'?s\s+all\b",
    r"\bstop\s+(the\s+)?call\b",
]

HANGUP_CONFIRMATION_PATTERNS = [
    r"\byes\b",
    r"\byeah\b",
    r"\byep\b",
    r"\bsure\b",
    r"\bplease\s+end\b",
    r"\bgo\s+ahead\b",
    r"\bconfirm\b",
    r"\bend\s+(it|the\s+call)\b",
    r"\bhang\s*(up)?\b",
]

HANGUP_DECLINE_PATTERNS = [
    r"\bno\b",
    r"\bnot\s+yet\b",
    r"\bwait\b",
    r"\bkeep\s+going\b",
    r"\bcontinue\b",
    r"\bdon't\s+hang\b",
    r"\bdo\s+not\s+end\b",
]


def _matches_any_pattern(text: str, patterns: list[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def transcript_has_hangup_intent(transcript: str) -> bool:
    """Return True if transcript suggests the caller wants to end the call."""
    return _matches_any_pattern(transcript, HANGUP_INTENT_PATTERNS)


def transcript_confirms_hangup(transcript: str) -> bool:
    """Return True if transcript confirms ending the call."""
    return _matches_any_pattern(transcript, HANGUP_CONFIRMATION_PATTERNS)


def transcript_denies_hangup(transcript: str) -> bool:
    """Return True if transcript declines ending the call."""
    return _matches_any_pattern(transcript, HANGUP_DECLINE_PATTERNS)


async def request_call_end_confirmation(openai_ws):
    """
    Instruct the assistant to confirm whether the caller truly wants to end the call.
    """
    confirmation_prompt = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "The caller just indicated they may want to end the call. "
                        "Politely ask them to confirm whether they would like you to hang up now. "
                        "Do not end the call until they explicitly confirm."
                    )
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(confirmation_prompt))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    logger.info("Requested hangup confirmation from assistant")


async def send_call_end_acknowledgement(openai_ws):
    """
    Instruct the assistant to acknowledge the confirmation and say goodbye.
    """
    acknowledgement_prompt = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "The caller confirmed they want to end the call. "
                        "Please provide a brief, polite goodbye and let them know the call is ending now."
                    )
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(acknowledgement_prompt))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    logger.info("Sent acknowledgement prompt for confirmed hangup")


async def send_call_continue_acknowledgement(openai_ws):
    """
    Instruct the assistant to acknowledge that the caller wants to keep talking.
    """
    continue_prompt = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "The caller does not want to end the call anymore. "
                        "Reassure them that the conversation will continue and ask how you can assist further."
                    )
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(continue_prompt))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    logger.info("Sent acknowledgement prompt to continue the call")
