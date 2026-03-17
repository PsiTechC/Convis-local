"""
Shared constants for the Convis API.
"""

DEFAULT_CALL_GREETING = (
    "Hello! Thanks for calling. How can I help you today?"
)

# Email collection best practices for AI assistants
# This can be appended to system prompts for better email capture accuracy
EMAIL_COLLECTION_GUIDANCE = """
## Email Collection Best Practices

When collecting email addresses from callers:

1. **Request Character-by-Character Spelling**
   - Ask the caller to spell out their email slowly
   - Example: "Could you please spell out your email address for me, one letter at a time?"

2. **Use Phonetic Alphabet for Confirmation**
   - When repeating back, use the NATO phonetic alphabet for clarity
   - Example: "Let me confirm: S as in Sierra, dot, B as in Bravo, G as in Golf..."

3. **Confirm @ Symbol and Domain Separately**
   - "What comes before the @ sign?"
   - "And after the @ sign, is that gmail.com, yahoo.com, or another domain?"

4. **Read Back Complete Email**
   - Always read the complete email back before proceeding
   - "Just to confirm, your email is s.bgadhave611 at gmail dot com. Is that correct?"

5. **Handle Common Mistakes**
   - If they say "at the rate" or "at sign", understand it as @
   - If they say "dot", understand it as a period (.)
   - Common domains: gmail.com, yahoo.com, outlook.com, hotmail.com

6. **Ask for Correction Politely**
   - "I want to make sure I have this right. Could you repeat just the part before the @ sign?"
   - "Let me try again. Is it G as in Golf, M as in Mike, A as in Alpha, I as in India, L as in Lima?"
"""

# Recommended VAD and interruption settings for different use cases
RECOMMENDED_SETTINGS = {
    "fast_response": {
        "description": "Best for quick, natural conversations with minimal latency",
        "vad_threshold": 0.35,
        "vad_min_speech_ms": 100,
        "vad_min_silence_ms": 150,
        "interruption_probability_threshold": 0.5,
        "interruption_min_chunks": 2,
        "use_streaming_mode": True,
    },
    "balanced": {
        "description": "Good balance between responsiveness and accuracy",
        "vad_threshold": 0.4,
        "vad_min_speech_ms": 150,
        "vad_min_silence_ms": 200,
        "interruption_probability_threshold": 0.6,
        "interruption_min_chunks": 2,
        "use_streaming_mode": True,
    },
    "accurate": {
        "description": "Best for complex information gathering (email, phone, address)",
        "vad_threshold": 0.45,
        "vad_min_speech_ms": 200,
        "vad_min_silence_ms": 300,
        "interruption_probability_threshold": 0.7,
        "interruption_min_chunks": 3,
        "use_streaming_mode": False,
    },
    "noisy_environment": {
        "description": "For calls with background noise",
        "vad_threshold": 0.5,
        "vad_min_speech_ms": 200,
        "vad_min_silence_ms": 250,
        "interruption_probability_threshold": 0.7,
        "interruption_min_chunks": 3,
        "use_streaming_mode": True,
    },
}

