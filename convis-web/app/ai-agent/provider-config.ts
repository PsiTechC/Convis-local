// Enhanced Provider Configuration with Complete Voice and Model Options
// All pricing data accurate as of January 2025

export const ENHANCED_TTS_VOICES = {
  cartesia: [
    // Real Cartesia Voice IDs - For Voice Agents (Stable, Realistic)
    { value: 'f786b574-daa5-4673-aa0c-cbe3e8534c02', label: 'Katie - American Female (Voice Agent)', gender: 'female', accent: 'American' },
    { value: '228fca29-3a0a-435c-8728-5cb483251068', label: 'Kiefer - American Male (Voice Agent)', gender: 'male', accent: 'American' },
    // For Expressive Characters (Emotive)
    { value: '6ccbfb76-1fc6-48f7-b71d-91ac6298247b', label: 'Tessa - American Female (Emotive)', gender: 'female', accent: 'American' },
    { value: 'c961b81c-a935-4c17-bfb3-ba2239de8c2f', label: 'Kyle - American Male (Emotive)', gender: 'male', accent: 'American' },
    // Additional Voice IDs from Examples
    { value: 'a0e99841-438c-4a64-b679-ae501e7d6091', label: 'Default Voice (Recommended)', gender: 'neutral', accent: 'American' },
    { value: 'f9836c6e-a0bd-460e-9d3c-f7299fa60f94', label: 'Alternative Voice 1', gender: 'neutral', accent: 'American' },
    { value: 'a167e0f3-df7e-4d52-a9c3-f949145efdab', label: 'Customer Support Man', gender: 'male', accent: 'American' }
  ],
  elevenlabs: [
    // Female voices - American (using actual ElevenLabs voice_ids)
    { value: 'EXAVITQu4vr4xnSDxMaL', label: 'Sarah - American Female (Young)', gender: 'female', accent: 'American' },
    { value: 'FGY2WhTYpPnrIDTdsKH5', label: 'Laura - American Female (Young)', gender: 'female', accent: 'American' },
    { value: 'cgSgspJ2msm6clMCkdW9', label: 'Jessica - American Female (Young)', gender: 'female', accent: 'American' },
    { value: 'XrExE9yKIg1WjnnlVkGX', label: 'Matilda - American Female (Middle-aged)', gender: 'female', accent: 'American' },
    { value: 'pFZP5JQG7iQjIQuC4Bku', label: 'Lily - Female (Middle-aged)', gender: 'female', accent: 'American' },
    // Female voices - British
    { value: 'Xb7hH8MSUJpSbSDYk0k2', label: 'Alice - British Female (Middle-aged)', gender: 'female', accent: 'British' },
    { value: 'FrzKLwOr0y3qieiphjs2', label: 'Paula - British Female (Young)', gender: 'female', accent: 'British' },
    // Male voices - American
    { value: '2EiwWnXFnvU5JabPnv8n', label: 'Clyde - American Male (Middle-aged)', gender: 'male', accent: 'American' },
    { value: 'CwhRBWXzGAHq8TQ4Fs17', label: 'Roger - American Male (Middle-aged)', gender: 'male', accent: 'American' },
    { value: 'TX3LPaxmHKxFdv7VOQHJ', label: 'Liam - American Male (Young)', gender: 'male', accent: 'American' },
    { value: 'SOYHLrjzK2X1ezoPC6cr', label: 'Harry - American Male (Young)', gender: 'male', accent: 'American' },
    { value: 'bIHbv24MWmeRgasZH58o', label: 'Will - American Male (Young)', gender: 'male', accent: 'American' },
    { value: 'cjVigY5qzO86Huf0OWal', label: 'Eric - American Male (Middle-aged)', gender: 'male', accent: 'American' },
    { value: 'iP95p4xoKVk53GoZ742B', label: 'Chris - American Male (Middle-aged)', gender: 'male', accent: 'American' },
    { value: 'nPczCjzI2devNBz1zQrb', label: 'Brian - American Male (Middle-aged)', gender: 'male', accent: 'American' },
    { value: 'pqHfZKP75CvOlQylNhV4', label: 'Bill - American Male (Old)', gender: 'male', accent: 'American' },
    // Male voices - British
    { value: 'JBFqnCBsd6RMkjVDRZzb', label: 'George - British Male (Middle-aged)', gender: 'male', accent: 'British' },
    { value: 'onwK4e9ZLuTAKqWW03F9', label: 'Daniel - British Male (Middle-aged)', gender: 'male', accent: 'British' },
    { value: 'N2lVS1w4EtoT3dr4eOWO', label: 'Callum - Male (Middle-aged)', gender: 'male', accent: 'British' },
    // Male voices - Other
    { value: 'IKne3meq5aSn9XLyUdCD', label: 'Charlie - Australian Male (Young)', gender: 'male', accent: 'Australian' },
    // Neutral voices
    { value: 'SAz9YHcvj6GT2YYXdXww', label: 'River - American Neutral (Middle-aged)', gender: 'neutral', accent: 'American' },
    // Indian Hindi voices - Female
    { value: 'broqrJkktxd1CclKTudW', label: 'Anika - Hindi Customer Care Agent (Female)', gender: 'female', accent: 'Indian' },
    { value: 'ni6cdqyS9wBvic5LPA7M', label: 'Tara - Hindi Conversational (Female)', gender: 'female', accent: 'Indian' },
    { value: 'SZfY4K69FwXus87eayHK', label: 'Nikita - Hindi Youthful (Female)', gender: 'female', accent: 'Indian' },
    { value: '1qEiC6qsybMkmnNdVMbK', label: 'Monika - Hindi Modulated (Female)', gender: 'female', accent: 'Indian' },
    // Indian Hindi voices - Male
    { value: 'KSsyodh37PbfWy29kPtx', label: 'Kishan - Hindi Narrator (Male)', gender: 'male', accent: 'Indian' },
    { value: '6MoEUz34rbRrmmyxgRm4', label: 'Manav - Hindi Conversational (Male)', gender: 'male', accent: 'Indian' }
  ],
  openai: [
    { value: 'alloy', label: 'Alloy - Neutral, balanced', gender: 'neutral', accent: 'American' },
    { value: 'echo', label: 'Echo - Male voice', gender: 'male', accent: 'American' },
    { value: 'fable', label: 'Fable - British male', gender: 'male', accent: 'British' },
    { value: 'onyx', label: 'Onyx - Deep male', gender: 'male', accent: 'American' },
    { value: 'nova', label: 'Nova - Female voice', gender: 'female', accent: 'American' },
    { value: 'shimmer', label: 'Shimmer - Soft female', gender: 'female', accent: 'American' }
  ],
  sarvam: [
    // Female voices (lowercase required by Sarvam API)
    { value: 'manisha', label: 'Manisha - Female Hindi/English', gender: 'female', accent: 'Indian' },
    { value: 'anushka', label: 'Anushka - Female Hindi', gender: 'female', accent: 'Indian' },
    { value: 'vidya', label: 'Vidya - Female Hindi', gender: 'female', accent: 'Indian' },
    { value: 'arya', label: 'Arya - Female Hindi', gender: 'female', accent: 'Indian' },
    // Male voices (lowercase required by Sarvam API)
    { value: 'abhilash', label: 'Abhilash - Male Hindi', gender: 'male', accent: 'Indian' },
    { value: 'hitesh', label: 'Hitesh - Male Hindi/English', gender: 'male', accent: 'Indian' },
    { value: 'karun', label: 'Karun - Male Hindi', gender: 'male', accent: 'Indian' }
  ],
  piper: [
    { value: 'en_US-lessac-medium', label: 'Lessac - American Female', gender: 'female', accent: 'American' },
    { value: 'en_US-lessac-high', label: 'Lessac - American Female (HQ)', gender: 'female', accent: 'American' },
    { value: 'en_US-amy-medium', label: 'Amy - American Female', gender: 'female', accent: 'American' },
    { value: 'en_GB-alba-medium', label: 'Alba - British Female', gender: 'female', accent: 'British' },
    { value: 'hi_IN-priyamvada-medium', label: 'Priyamvada - Hindi Female', gender: 'female', accent: 'Indian' },
    { value: 'hi_IN-pratham-medium', label: 'Pratham - Hindi Male', gender: 'male', accent: 'Indian' },
  ],
};

// Enhanced ASR Models with all available options
export const ENHANCED_ASR_MODELS = {
  deepgram: [
    { value: 'nova-2', label: 'Nova-2 (Latest, Most Accurate)', cost: 0.0043, latency: 75, costPerMin: 0.0043 },
    { value: 'nova-3', label: 'Nova-3 (Beta, Improved)', cost: 0.0059, latency: 80, costPerMin: 0.0059 },
    { value: 'whisper', label: 'Whisper (Good Accuracy)', cost: 0.0048, latency: 100, costPerMin: 0.0048 },
    { value: 'base', label: 'Base (Standard)', cost: 0.0125, latency: 85, costPerMin: 0.0125 }
  ],
  openai: [
    { value: 'whisper-1', label: 'Whisper-1 (General Purpose)', cost: 0.006, latency: 250, costPerMin: 0.006 }
  ],
  sarvam: [
    { value: 'saarika:v1', label: 'Saarika V1 (Indian Languages)', cost: 0.004, latency: 120, costPerMin: 0.004 },
    { value: 'saarika:v2', label: 'Saarika V2 (Improved)', cost: 0.005, latency: 110, costPerMin: 0.005 }
  ],
  google: [
    { value: 'default', label: 'Google Speech-to-Text Standard', cost: 0.006, latency: 130, costPerMin: 0.006 },
    { value: 'latest_long', label: 'Latest Long (Better for Long Audio)', cost: 0.009, latency: 145, costPerMin: 0.009 }
  ],
  whisper: [
    { value: 'tiny', label: 'Whisper Tiny - Fastest (Free, Local)', cost: 0, latency: 150, costPerMin: 0 },
    { value: 'base', label: 'Whisper Base - Balanced (Free, Local)', cost: 0, latency: 300, costPerMin: 0 },
    { value: 'small', label: 'Whisper Small - Best Quality (Free, Local)', cost: 0, latency: 600, costPerMin: 0 },
    { value: 'medium', label: 'Whisper Medium - High Accuracy (Free, Local)', cost: 0, latency: 1000, costPerMin: 0 },
    { value: 'large-v3', label: 'Whisper Large-v3 - Best Accuracy (Free, Local)', cost: 0, latency: 2000, costPerMin: 0 },
  ]
};

// Enhanced TTS Models with accurate per-character costs
export const ENHANCED_TTS_MODELS = {
  cartesia: [
    { value: 'sonic-english', label: 'Sonic English (Ultra-Fast)', cost: 0.025, latency: 100, costPerChar: 0.000025 }
  ],
  elevenlabs: [
    // Flash Models - Ultra Low Latency (~75ms) - Best for Real-time/Voice Agents
    { value: 'eleven_flash_v2_5', label: 'Flash V2.5 - Ultra Fast (~75ms, 32 Languages)', cost: 0.09, latency: 75, costPerChar: 0.00009 },
    { value: 'eleven_flash_v2', label: 'Flash V2 - Ultra Fast (~75ms, English Only)', cost: 0.09, latency: 75, costPerChar: 0.00009 },
    // Turbo Models - Low Latency with Better Quality
    { value: 'eleven_turbo_v2_5', label: 'Turbo V2.5 - Fast & High Quality (32 Languages)', cost: 0.09, latency: 130, costPerChar: 0.00009 },
    { value: 'eleven_turbo_v2', label: 'Turbo V2 - Fast & High Quality (English Only)', cost: 0.09, latency: 150, costPerChar: 0.00009 },
    // Standard Models - Best Quality
    { value: 'eleven_multilingual_v2', label: 'Multilingual V2 - Best Quality (29 Languages)', cost: 0.18, latency: 180, costPerChar: 0.00018 },
    // Eleven V3 - Most Expressive (Higher Latency)
    { value: 'eleven_v3', label: 'Eleven V3 - Most Expressive (70+ Languages, Higher Latency)', cost: 0.18, latency: 300, costPerChar: 0.00018 }
  ],
  openai: [
    { value: 'tts-1', label: 'TTS-1 (Fast, Good Quality)', cost: 0.015, latency: 250, costPerChar: 0.000015 },
    { value: 'tts-1-hd', label: 'TTS-1-HD (High Quality)', cost: 0.030, latency: 300, costPerChar: 0.000030 }
  ],
  sarvam: [
    { value: 'bulbul:v2', label: 'Bulbul V2 (Hindi/Indian - Recommended)', cost: 0.006, latency: 130, costPerChar: 0.000006 },
    { value: 'bulbul:v3-beta', label: 'Bulbul V3 Beta (Latest, Experimental)', cost: 0.008, latency: 140, costPerChar: 0.000008 }
  ],
  piper: [
    { value: 'medium', label: 'Medium Quality (Free, Local)', cost: 0, latency: 50, costPerChar: 0 },
    { value: 'high', label: 'High Quality (Free, Local)', cost: 0, latency: 80, costPerChar: 0 },
  ]
};

// Enhanced LLM Models with accurate per-token costs (January 2025)
export const ENHANCED_LLM_MODELS = {
  openai: [
    // Sorted from cheapest/fastest to most expensive/capable
    { value: 'gpt-4o-mini', label: 'GPT-4O Mini - Cheapest & Fastest ($0.15 in / $0.60 out per 1M tokens)', costInput: 0.15, costOutput: 0.60, latency: 400, cost: '0.000375', speed: 'Fastest' },
    { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo - Very Fast ($0.50 in / $1.50 out per 1M tokens)', costInput: 0.50, costOutput: 1.50, latency: 300, cost: '0.001', speed: 'Very Fast' },
    { value: 'gpt-4o', label: 'GPT-4O - Balanced Performance ($5.00 in / $20.00 out per 1M tokens)', costInput: 5.00, costOutput: 20.00, latency: 800, cost: '0.0125', speed: 'Fast' },
    { value: 'gpt-4-turbo', label: 'GPT-4 Turbo - High Quality ($10.00 in / $30.00 out per 1M tokens)', costInput: 10.00, costOutput: 30.00, latency: 1000, cost: '0.02', speed: 'Moderate' },
    { value: 'o1-mini', label: 'O1 Mini - Advanced Reasoning ($3.00 in / $12.00 out per 1M tokens)', costInput: 3.00, costOutput: 12.00, latency: 1200, cost: '0.0075', speed: 'Advanced Reasoning' }
  ],
  ollama: [
    // Local LLM models via Ollama - Free, runs on your machine
    { value: 'llama3.2:3b', label: 'Llama 3.2 (3B) - Fast & Lightweight', costInput: 0, costOutput: 0, latency: 300, cost: 'Free', speed: 'Fast' },
    { value: 'llama3.2:1b', label: 'Llama 3.2 (1B) - Ultra Fast', costInput: 0, costOutput: 0, latency: 200, cost: 'Free', speed: 'Ultra Fast' },
    { value: 'llama3.1:8b', label: 'Llama 3.1 (8B) - Balanced', costInput: 0, costOutput: 0, latency: 500, cost: 'Free', speed: 'Moderate' },
    { value: 'mistral', label: 'Mistral (7B) - High Quality', costInput: 0, costOutput: 0, latency: 500, cost: 'Free', speed: 'Moderate' },
    { value: 'phi3', label: 'Phi-3 (3.8B) - Microsoft Small Model', costInput: 0, costOutput: 0, latency: 350, cost: 'Free', speed: 'Fast' },
    { value: 'gemma2', label: 'Gemma 2 (9B) - Google', costInput: 0, costOutput: 0, latency: 600, cost: 'Free', speed: 'Moderate' },
    { value: 'qwen2.5', label: 'Qwen 2.5 (7B) - Alibaba', costInput: 0, costOutput: 0, latency: 500, cost: 'Free', speed: 'Moderate' }
  ],
  'openai-realtime': [
    { value: 'gpt-4o-realtime-preview', label: 'GPT-4O Realtime Preview', cost: 0.30, latency: 320, costPerMin: 0.30, speed: 'Realtime' },
    { value: 'gpt-4o-realtime-preview-2024-10-01', label: 'GPT-4O Realtime 2024-10-01', cost: 0.30, latency: 320, costPerMin: 0.30, speed: 'Realtime' },
    { value: 'gpt-4o-realtime', label: 'GPT-4O Realtime (Stable)', cost: 0.30, latency: 280, costPerMin: 0.30, speed: 'Realtime' },
    { value: 'gpt-4o-mini-realtime-preview', label: 'GPT-4O Mini Realtime Preview', cost: 0.30, latency: 200, costPerMin: 0.30, speed: 'Ultra Fast' },
    { value: 'gpt-4o-mini-realtime', label: 'GPT-4O Mini Realtime (Stable)', cost: 0.30, latency: 200, costPerMin: 0.30, speed: 'Ultra Fast' }
  ]
};

// Twilio Cost
export const TWILIO_COST_PER_MIN = {
  usd: 0.014,
  inr: 5.5
};

// Function to fetch ElevenLabs voices dynamically from user's account
export async function fetchElevenLabsVoices(userId: string): Promise<Array<{value: string, label: string, gender: string, accent: string}>> {
  try {
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai'}/api/voices/elevenlabs/sync?user_id=${userId}`
    );

    if (!response.ok) {
      console.warn('Failed to fetch ElevenLabs voices, using defaults');
      return ENHANCED_TTS_VOICES.elevenlabs;
    }

    const data = await response.json();

    if (data.success && data.voices) {
      return data.voices.map((voice: { id: string; name: string; accent: string; gender: string; age_group?: string }) => ({
        value: voice.id,
        label: `${voice.name} - ${voice.accent} ${voice.gender.charAt(0).toUpperCase() + voice.gender.slice(1)}${voice.age_group ? ` (${voice.age_group})` : ''}`,
        gender: voice.gender,
        accent: voice.accent
      }));
    }

    return ENHANCED_TTS_VOICES.elevenlabs;
  } catch (error) {
    console.error('Error fetching ElevenLabs voices:', error);
    return ENHANCED_TTS_VOICES.elevenlabs;
  }
}

// Function to get all TTS voices with optional live ElevenLabs sync
export async function getTTSVoices(userId?: string, syncElevenLabs: boolean = false): Promise<typeof ENHANCED_TTS_VOICES> {
  if (!syncElevenLabs || !userId) {
    return ENHANCED_TTS_VOICES;
  }

  const liveElevenLabsVoices = await fetchElevenLabsVoices(userId);

  return {
    ...ENHANCED_TTS_VOICES,
    elevenlabs: liveElevenLabsVoices
  };
}
