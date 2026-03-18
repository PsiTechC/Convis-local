// Enhanced Provider Configuration with Complete Voice and Model Options
// All pricing data accurate as of January 2025

export const ENHANCED_TTS_VOICES = {
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
  ]
};

// Enhanced TTS Models with accurate per-character costs
export const ENHANCED_TTS_MODELS = {
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
    { value: 'llama3.2', label: 'Llama 3.2 (3B) - Fast & Lightweight', costInput: 0, costOutput: 0, latency: 300, cost: 'Free', speed: 'Fast' },
    { value: 'llama3.2:1b', label: 'Llama 3.2 (1B) - Ultra Fast', costInput: 0, costOutput: 0, latency: 200, cost: 'Free', speed: 'Ultra Fast' },
    { value: 'llama3.1', label: 'Llama 3.1 (8B) - Balanced', costInput: 0, costOutput: 0, latency: 500, cost: 'Free', speed: 'Moderate' },
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

// Function to fetch locally available Ollama models
export async function fetchOllamaModels(): Promise<typeof ENHANCED_LLM_MODELS.ollama> {
  try {
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/ollama/models`
    );

    if (!response.ok) {
      console.warn('Failed to fetch Ollama models, using defaults');
      return ENHANCED_LLM_MODELS.ollama;
    }

    const data = await response.json();

    if (data.success && data.models && data.models.length > 0) {
      return data.models.map((m: { value: string; label: string; size_gb: number }) => ({
        value: m.value,
        label: m.label,
        costInput: 0,
        costOutput: 0,
        latency: 300,
        cost: 'Free',
        speed: 'Local'
      }));
    }

    return ENHANCED_LLM_MODELS.ollama;
  } catch (error) {
    console.error('Error fetching Ollama models:', error);
    return ENHANCED_LLM_MODELS.ollama;
  }
}

// Function to get all available TTS voices.
export async function getTTSVoices(): Promise<typeof ENHANCED_TTS_VOICES> {
  return ENHANCED_TTS_VOICES;
}
