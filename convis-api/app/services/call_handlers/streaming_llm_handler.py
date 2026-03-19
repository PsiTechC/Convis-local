"""
Streaming LLM Handler for VAPI-like Low Latency
Streams LLM response and processes sentence-by-sentence for early TTS
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict, Any, Callable, Awaitable, AsyncIterator

logger = logging.getLogger(__name__)


class StreamingLLMHandler:
    """
    Streams LLM responses and yields complete sentences for immediate TTS.
    
    Key optimization: Instead of waiting for complete response (1-3 seconds),
    we start TTS on the first sentence (~200ms), drastically reducing perceived latency.
    """
    
    def __init__(
        self,
        openai_client,
        model: str = "gpt-4o-mini",
        temperature: float = 0.8,
        max_tokens: int = 150
    ):
        self.client = openai_client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Sentence boundary patterns
        self.sentence_endings = re.compile(r'[.!?]+[\s\n]+|[.!?]+$')
        
    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        on_sentence: Optional[Callable[[str], Awaitable[None]]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> str:
        """
        Stream LLM response and call on_sentence for each complete sentence.

        This is the key to low latency:
        - User hears first sentence in ~300ms instead of waiting 1500ms for full response
        - TTS runs in parallel with LLM generation

        Args:
            is_cancelled: Optional callback that returns True to abort the stream
                          early (e.g. on user barge-in).

        Returns:
            Complete response text
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True  # KEY: Enable streaming!
            )

            buffer = ""
            full_response = ""
            sentence_count = 0

            async for chunk in response:
                # Abort early if caller signals cancellation (barge-in)
                if is_cancelled and is_cancelled():
                    logger.info(f"[STREAMING_LLM] Cancelled after {sentence_count} sentences")
                    break

                delta = chunk.choices[0].delta

                if delta.content:
                    token = delta.content
                    buffer += token
                    full_response += token

                    # Check for complete sentences
                    while True:
                        match = self.sentence_endings.search(buffer)
                        if not match:
                            break

                        # Extract complete sentence
                        end_pos = match.end()
                        sentence = buffer[:end_pos].strip()
                        buffer = buffer[end_pos:]

                        if sentence and on_sentence:
                            sentence_count += 1
                            logger.info(f"[STREAMING_LLM] Sentence {sentence_count}: {sentence[:50]}...")
                            await on_sentence(sentence)

            # Handle any remaining text (incomplete sentence at end)
            if buffer.strip() and on_sentence and not (is_cancelled and is_cancelled()):
                sentence_count += 1
                logger.info(f"[STREAMING_LLM] Final fragment: {buffer.strip()[:50]}...")
                await on_sentence(buffer.strip())

            logger.info(f"[STREAMING_LLM] ✅ Complete: {sentence_count} sentences, {len(full_response)} chars")
            return full_response

        except Exception as e:
            logger.error(f"[STREAMING_LLM] Error: {e}")
            raise
    
    async def generate_sentences(
        self,
        messages: List[Dict[str, str]]
    ) -> AsyncIterator[str]:
        """
        Generator version - yields sentences as they're ready.
        Useful for pipeline architectures.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True
            )
            
            buffer = ""
            
            async for chunk in response:
                delta = chunk.choices[0].delta
                
                if delta.content:
                    buffer += delta.content
                    
                    # Yield complete sentences
                    while True:
                        match = self.sentence_endings.search(buffer)
                        if not match:
                            break
                        
                        end_pos = match.end()
                        sentence = buffer[:end_pos].strip()
                        buffer = buffer[end_pos:]
                        
                        if sentence:
                            yield sentence
            
            # Yield remaining text
            if buffer.strip():
                yield buffer.strip()
                
        except Exception as e:
            logger.error(f"[STREAMING_LLM] Generator error: {e}")
            raise


class ConversationManager:
    """
    Manages conversation history with optimizations for voice calls.
    """
    
    def __init__(self, system_message: str, max_history: int = 10):
        self.system_message = system_message
        self.max_history = max_history
        self.history: List[Dict[str, str]] = [
            {"role": "system", "content": system_message}
        ]
    
    def add_user_message(self, text: str):
        """Add user message to history"""
        self.history.append({"role": "user", "content": text})
        self._trim_history()
    
    def add_assistant_message(self, text: str):
        """Add assistant message to history"""
        self.history.append({"role": "assistant", "content": text})
        self._trim_history()
    
    def _trim_history(self):
        """Keep history under max size while preserving system message"""
        if len(self.history) > self.max_history + 1:
            # Keep system message + last N messages
            self.history = [self.history[0]] + self.history[-(self.max_history):]
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Get messages for LLM call"""
        return self.history.copy()
    
    def clear(self):
        """Clear history but keep system message"""
        self.history = [{"role": "system", "content": self.system_message}]









