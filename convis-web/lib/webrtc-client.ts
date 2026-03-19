/**
 * WebRTC Voice Client SDK for Convis
 *
 * Browser-based voice calling to Convis AI assistants.
 * Uses WebSocket for signaling + audio transport (mic: PCM 16-bit 16kHz, playback: PCM 16-bit 24kHz).
 * Audio passes through server for ASR → LLM → TTS pipeline.
 *
 * Usage:
 * ```typescript
 * import { useWebRTCCall } from '@/lib/webrtc-client';
 *
 * const { state, transcripts, duration, isMuted, start, stop, toggleMute, setVolume } =
 *   useWebRTCCall({ apiBaseUrl: 'https://api.convis.ai', assistantId: 'abc123' });
 * ```
 */

import { useState, useRef, useCallback, useEffect } from 'react';

// ─── Types ───────────────────────────────────────────────────────────────────

export type CallState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'ai-speaking'
  | 'disconnected'
  | 'error';

export interface Transcript {
  speaker: 'user' | 'assistant';
  text: string;
  isFinal: boolean;
  timestamp: number;
}

export interface WebRTCClientConfig {
  apiBaseUrl: string;
  assistantId: string;
  userId?: string;
  onTranscript?: (text: string, isFinal: boolean, speaker: string) => void;
  onStateChange?: (state: CallState) => void;
  onError?: (error: Error) => void;
  onAudioStart?: () => void;
  onAudioEnd?: () => void;
}

interface SignalingMessage {
  type: string;
  sessionId?: string;
  mode?: string;
  audioConstraints?: Record<string, unknown>;
  data?: string;
  format?: string;
  text?: string;
  isFinal?: boolean;
  speaker?: string;
  state?: string;
}

// ─── Core Client Class ───────────────────────────────────────────────────────

export class ConvisWebRTCClient {
  private config: WebRTCClientConfig;
  private ws: WebSocket | null = null;
  private localStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private sessionId: string | null = null;
  private state: CallState = 'idle';

  // Audio capture
  private scriptProcessor: ScriptProcessorNode | null = null;

  // Client-side barge-in detection
  private bargeInCount = 0;

  // Tracks when server is done sending audio but client is still playing.
  // Keeps barge-in detection active until playback actually finishes.
  private serverDoneSending = false;

  // Audio playback
  private gainNode: GainNode | null = null;
  private nextPlayTime = 0;

  // Jitter buffer: accumulate small chunks, play in larger batches
  private pendingSamples: Int16Array[] = [];
  private pendingSampleCount = 0;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private static readonly BUFFER_FLUSH_MS = 80;           // flush after 80ms if threshold not reached
  private static readonly BUFFER_MIN_SAMPLES = 1920;       // ~80ms at 24kHz — flush when this much accumulates

  // Keepalive
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  constructor(config: WebRTCClientConfig) {
    this.config = config;
  }

  getState(): CallState {
    return this.state;
  }

  getSessionId(): string | null {
    return this.sessionId;
  }

  // ── Lifecycle ────────────────────────────────────────────────────────────

  async start(): Promise<void> {
    if (this.state !== 'idle' && this.state !== 'disconnected' && this.state !== 'error') {
      throw new Error(`Cannot start call in state: ${this.state}`);
    }

    // Close any leftover AudioContext from a previous call (Chrome limits ~6 concurrent contexts)
    if (this.audioContext) {
      try { await this.audioContext.close(); } catch { /* already closed */ }
      this.audioContext = null;
      this.gainNode = null;
    }

    this.setState('connecting');

    try {
      // 1. Create AudioContext NOW (during user gesture) so browser allows audio playback.
      //    Use browser's default sample rate (usually 48kHz) — specifying 16kHz causes
      //    "closed" state on some Chrome/macOS configurations. We downsample in capture
      //    and let createBuffer() handle resampling for playback.
      this.audioContext = new AudioContext();

      // Some browsers start the context suspended; resume during user gesture
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      console.log('[WebRTC] AudioContext created, state:', this.audioContext.state, 'sampleRate:', this.audioContext.sampleRate);

      if (this.audioContext.state !== 'running') {
        console.warn('[WebRTC] AudioContext not running, closing and retrying...');
        try { this.audioContext.close(); } catch { /* ignore */ }
        // Wait a tick for the closed context to release
        await new Promise(r => setTimeout(r, 100));
        this.audioContext = new AudioContext();
        await this.audioContext.resume();
        console.log('[WebRTC] AudioContext retry, state:', this.audioContext.state, 'sampleRate:', this.audioContext.sampleRate);

        if (this.audioContext.state !== 'running') {
          throw new Error('AudioContext failed to start. Please close other tabs and refresh this page.');
        }
      }

      // Set up gain node for playback volume control
      this.gainNode = this.audioContext.createGain();
      this.gainNode.connect(this.audioContext.destination);

      // 2. Get microphone access
      await this.setupLocalAudio();

      // Abort if stop() was called while waiting for mic permission (React StrictMode)
      if (!this.audioContext) {
        console.log('[WebRTC] Start aborted (stopped during mic access)');
        return;
      }

      // 3. Connect WebSocket to signaling server
      await this.connectSignaling();

      // Abort if stop() was called during WebSocket connection
      if (!this.audioContext) {
        console.log('[WebRTC] Start aborted (stopped during signaling)');
        return;
      }

      // Server will send "config" message → we reply "ready" → pipeline starts
    } catch (error) {
      // Don't report error if we were deliberately stopped (audioContext nulled by cleanup)
      if (!this.audioContext) return;
      this.setState('error');
      this.config.onError?.(error as Error);
      throw error;
    }
  }

  async stop(): Promise<void> {
    try {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'hangup' }));
      }
      await this.cleanup();
      this.setState('disconnected');
    } catch (error) {
      console.error('[WebRTC] Error stopping call:', error);
      await this.cleanup();
      this.setState('disconnected');
    }
  }

  setMuted(muted: boolean): void {
    if (this.localStream) {
      this.localStream.getAudioTracks().forEach((track) => {
        track.enabled = !muted;
      });
    }
  }

  setVolume(volume: number): void {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, volume));
    }
  }

  // ── Internal: State ──────────────────────────────────────────────────────

  private setState(newState: CallState): void {
    this.state = newState;
    this.config.onStateChange?.(newState);
  }

  // ── Internal: Microphone ─────────────────────────────────────────────────

  private async setupLocalAudio(): Promise<void> {
    try {
      this.localStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
          channelCount: 1,
        },
        video: false,
      });
      console.log('[WebRTC] Microphone access granted');
    } catch (error) {
      console.error('[WebRTC] Microphone access denied:', error);
      throw new Error('Microphone access is required for voice calls');
    }
  }

  // ── Internal: WebSocket Signaling ────────────────────────────────────────

  private connectSignaling(): Promise<void> {
    const baseUrl = this.config.apiBaseUrl.replace(/^http/, 'ws');
    let wsUrl = `${baseUrl}/api/webrtc/call/${this.config.assistantId}`;
    if (this.config.userId) {
      wsUrl += `?user_id=${encodeURIComponent(this.config.userId)}`;
    }

    console.log('[WebRTC] Connecting to:', wsUrl);

    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl);
      this.ws = ws;

      let settled = false;
      const settleError = (message: string) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        reject(new Error(message));
      };

      const settleSuccess = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        resolve();
      };

      const timeout = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          ws.close();
          settleError('Connection timeout');
        }
      }, 15000);

      ws.onopen = () => {
        console.log('[WebRTC] WebSocket connected');
        this.startPingInterval();
        settleSuccess();
      };

      ws.onmessage = (event) => {
        this.handleMessage(event.data);
      };

      ws.onclose = (event) => {
        console.log('[WebRTC] WebSocket closed:', event.code, event.reason);
        this.stopPingInterval();

        if (!settled) {
          const closeReason = event.reason
            ? `Signaling server closed connection (${event.code}): ${event.reason}`
            : `Signaling server closed connection (${event.code})`;
          settleError(closeReason);
          return;
        }

        if (this.state === 'connected' || this.state === 'listening' || this.state === 'ai-speaking') {
          this.setState('disconnected');
          this.cleanup();
        }
      };

      ws.onerror = () => {
        settleError('Failed to connect to signaling server');
      };
    });
  }

  // ── Internal: Message Handling ───────────────────────────────────────────

  private async handleMessage(data: string): Promise<void> {
    try {
      const msg: SignalingMessage = JSON.parse(data);

      switch (msg.type) {
        case 'config':
          this.handleConfig(msg);
          break;

        case 'audio':
          this.handleIncomingAudio(msg);
          break;

        case 'transcript':
          this.config.onTranscript?.(msg.text || '', msg.isFinal ?? false, msg.speaker || 'user');
          break;

        case 'call-state':
          this.handleCallState(msg);
          break;

        case 'speech-end':
          // If audio is still playing, defer state transition until playback finishes.
          if (this.state === 'ai-speaking' && this.isAudioStillPlaying()) {
            this.serverDoneSending = true;
            console.log('[WebRTC] Speech-end received, audio still playing — deferring');
          } else {
            this.serverDoneSending = false;
            this.config.onAudioEnd?.();
            this.setState('listening');
          }
          break;

        case 'interrupt':
          console.log('[WebRTC] INTERRUPT received — stopping audio playback');
          this.stopAudioPlayback();
          this.setState('listening');
          break;

        case 'pong':
          break;

        case 'error':
          console.error('[WebRTC] Server error:', msg);
          this.config.onError?.(new Error('Server error'));
          break;

        default:
          console.log('[WebRTC] Unknown message type:', msg.type);
      }
    } catch (error) {
      console.error('[WebRTC] Error handling message:', error);
    }
  }

  private handleConfig(msg: SignalingMessage): void {
    // Abort if stop() was called (client is being torn down)
    if (!this.audioContext) return;

    this.sessionId = msg.sessionId || null;
    console.log('[WebRTC] Received config, session:', this.sessionId, 'mode:', msg.mode);

    // Start audio capture and tell server we're ready
    this.startAudioCapture();

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ready' }));
    }

    this.setState('connected');
  }

  private handleCallState(msg: SignalingMessage): void {
    const serverState = msg.state;
    if (serverState === 'listening') {
      // If we're still playing buffered audio, defer the transition.
      // Stay in ai-speaking so barge-in detection remains active.
      if (this.state === 'ai-speaking' && this.isAudioStillPlaying()) {
        this.serverDoneSending = true;
        console.log('[WebRTC] Server done sending, audio still playing — staying in ai-speaking');
      } else {
        this.serverDoneSending = false;
        this.setState('listening');
      }
    } else if (serverState === 'ai-speaking') {
      this.serverDoneSending = false;
      this.config.onAudioStart?.();
      this.setState('ai-speaking');
    } else if (serverState === 'connecting') {
      this.setState('connecting');
    }
  }

  private isAudioStillPlaying(): boolean {
    if (!this.audioContext) return false;
    return this.nextPlayTime > this.audioContext.currentTime + 0.05;
  }

  // ── Internal: Audio Capture (Mic → Server) ──────────────────────────────

  private startAudioCapture(): void {
    if (!this.localStream || !this.audioContext) return;

    // Ensure AudioContext is running (may have been suspended)
    if (this.audioContext.state === 'suspended') {
      this.audioContext.resume();
    }

    const source = this.audioContext.createMediaStreamSource(this.localStream);
    const contextRate = this.audioContext.sampleRate;

    // Use ScriptProcessorNode to capture PCM chunks
    this.scriptProcessor = this.audioContext.createScriptProcessor(4096, 1, 1);

    this.scriptProcessor.onaudioprocess = (event) => {
      if (this.ws?.readyState !== WebSocket.OPEN) return;

      const inputData = event.inputBuffer.getChannelData(0);

      // ── Client-side barge-in detection ──
      // Compute RMS energy of the mic input. Even after echo cancellation,
      // real user speech has noticeably higher energy than silence/residual echo.
      if (this.state === 'ai-speaking') {
        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sum / inputData.length);

        if (rms > 0.01) {
          this.bargeInCount++;
          if (this.bargeInCount >= 2) {
            console.log(`[WebRTC] CLIENT BARGE-IN! RMS=${rms.toFixed(4)}`);
            this.stopAudioPlayback();
            this.setState('listening');
            this.ws.send(JSON.stringify({ type: 'barge-in' }));
            this.bargeInCount = 0;
            return;
          }
        } else {
          this.bargeInCount = 0;
        }
      } else {
        this.bargeInCount = 0;
      }

      // Check if deferred playback has finished — transition to listening
      // and tell server it's safe to resume ASR.
      if (this.serverDoneSending && !this.isAudioStillPlaying()) {
        console.log('[WebRTC] Buffered audio playback complete — transitioning to listening');
        this.serverDoneSending = false;
        this.config.onAudioEnd?.();
        this.setState('listening');
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: 'playback-complete' }));
        }
      }

      // Downsample from AudioContext rate (e.g. 48kHz) to 16kHz for the server
      let audioToSend: Float32Array;
      if (contextRate !== 16000) {
        const ratio = contextRate / 16000;
        const outputLength = Math.floor(inputData.length / ratio);
        audioToSend = new Float32Array(outputLength);
        for (let i = 0; i < outputLength; i++) {
          audioToSend[i] = inputData[Math.floor(i * ratio)];
        }
      } else {
        audioToSend = inputData;
      }

      const pcmData = this.float32ToPcm16(audioToSend);

      this.ws.send(
        JSON.stringify({
          type: 'audio',
          data: this.arrayBufferToBase64(pcmData),
        })
      );
    };

    source.connect(this.scriptProcessor);
    // Connect to a silent destination to keep the processor alive (required by spec).
    // Using a zero-gain node prevents mic audio from playing through speakers.
    const silentGain = this.audioContext.createGain();
    silentGain.gain.value = 0;
    silentGain.connect(this.audioContext.destination);
    this.scriptProcessor.connect(silentGain);

    console.log(`[WebRTC] Audio capture started (context=${contextRate}Hz, sending=16000Hz)`);
  }

  // ── Internal: Audio Playback (Server → Speaker) ─────────────────────────

  private audioChunkCount = 0;

  private handleIncomingAudio(msg: SignalingMessage): void {
    if (!msg.data || !this.audioContext) return;

    // Only play audio when we're in ai-speaking state.
    // After barge-in (state=listening), ignore residual audio from the server
    // until the next call-state:ai-speaking message arrives.
    if (this.state !== 'ai-speaking' && this.state !== 'connected') return;

    // Decode base64 → raw PCM bytes
    const pcmBytes = this.base64ToArrayBuffer(msg.data);
    if (pcmBytes.byteLength < 2) return;

    // Ensure byte length is even (Int16Array requires 2-byte alignment)
    let buffer = pcmBytes;
    if (buffer.byteLength % 2 !== 0) {
      buffer = buffer.slice(0, buffer.byteLength - 1);
    }

    const samples = new Int16Array(buffer);
    this.pendingSamples.push(samples);
    this.pendingSampleCount += samples.length;

    // Flush immediately if we've accumulated enough, otherwise set a timer
    if (this.pendingSampleCount >= ConvisWebRTCClient.BUFFER_MIN_SAMPLES) {
      this.flushAudioBuffer();
    } else if (!this.flushTimer) {
      this.flushTimer = setTimeout(() => this.flushAudioBuffer(), ConvisWebRTCClient.BUFFER_FLUSH_MS);
    }
  }

  private flushAudioBuffer(): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }

    if (this.pendingSamples.length === 0 || !this.audioContext || !this.gainNode) return;

    // Concatenate all pending chunks into one buffer
    const combined = new Int16Array(this.pendingSampleCount);
    let offset = 0;
    for (const chunk of this.pendingSamples) {
      combined.set(chunk, offset);
      offset += chunk.length;
    }
    this.pendingSamples = [];
    this.pendingSampleCount = 0;

    // Resume AudioContext if it got suspended (e.g. tab backgrounded)
    if (this.audioContext.state === 'suspended') {
      this.audioContext.resume();
    }

    // Convert Int16 PCM → Float32 for Web Audio API
    const float32 = new Float32Array(combined.length);
    for (let i = 0; i < combined.length; i++) {
      float32[i] = combined[i] / 32768;
    }

    // Create AudioBuffer (1 channel, 24kHz)
    const audioBuffer = this.audioContext.createBuffer(1, float32.length, 24000);
    audioBuffer.getChannelData(0).set(float32);

    // Schedule sequentially to prevent gaps/overlaps
    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.gainNode);

    const now = this.audioContext.currentTime;

    // On first chunk or after a gap (>100ms silence), add 60ms lead time to absorb jitter
    if (this.nextPlayTime === 0 || now > this.nextPlayTime + 0.1) {
      this.nextPlayTime = now + 0.06;
    }

    const startTime = Math.max(now, this.nextPlayTime);
    source.start(startTime);
    this.nextPlayTime = startTime + audioBuffer.duration;

    this.audioChunkCount++;
    if (this.audioChunkCount <= 3) {
      console.log(`[WebRTC] Playing audio chunk #${this.audioChunkCount}: ${combined.length * 2} bytes (${combined.length} samples), duration=${audioBuffer.duration.toFixed(3)}s`);
    }
  }

  private stopAudioPlayback(): void {
    // Clear pending buffer and reset play queue (for barge-in)
    this.pendingSamples = [];
    this.pendingSampleCount = 0;
    this.serverDoneSending = false;
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    this.nextPlayTime = 0;

    // Immediately silence already-scheduled AudioBufferSourceNodes by
    // disconnecting the old gainNode (all sources are connected to it)
    // and creating a fresh one.
    if (this.gainNode && this.audioContext) {
      this.gainNode.disconnect();
      this.gainNode = this.audioContext.createGain();
      this.gainNode.connect(this.audioContext.destination);
    }
  }

  // ── Internal: Keepalive ──────────────────────────────────────────────────

  private startPingInterval(): void {
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 15000);
  }

  private stopPingInterval(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  // ── Internal: Cleanup ────────────────────────────────────────────────────

  private async cleanup(): Promise<void> {
    this.stopPingInterval();

    // Clear audio buffer
    this.pendingSamples = [];
    this.pendingSampleCount = 0;
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }

    if (this.scriptProcessor) {
      this.scriptProcessor.disconnect();
      this.scriptProcessor = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    if (this.localStream) {
      this.localStream.getTracks().forEach((track) => track.stop());
      this.localStream = null;
    }

    if (this.audioContext) {
      try {
        await this.audioContext.close();
      } catch {
        // Already closed
      }
      this.audioContext = null;
    }

    this.sessionId = null;
    this.gainNode = null;
    this.nextPlayTime = 0;
    this.audioChunkCount = 0;
    this.bargeInCount = 0;
    this.serverDoneSending = false;
  }

  // ── Utility ──────────────────────────────────────────────────────────────

  private float32ToPcm16(float32Array: Float32Array): ArrayBuffer {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buffer;
  }

  private base64ToArrayBuffer(base64: string): ArrayBuffer {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
}

// ─── React Hook ──────────────────────────────────────────────────────────────

export interface UseWebRTCCallReturn {
  state: CallState;
  transcripts: Transcript[];
  duration: number;
  isMuted: boolean;
  volume: number;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  toggleMute: () => void;
  setVolume: (v: number) => void;
}

export function useWebRTCCall(config: {
  apiBaseUrl: string;
  assistantId: string;
  userId?: string;
}): UseWebRTCCallReturn {
  const [state, setState] = useState<CallState>('idle');
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolumeState] = useState(1);

  const clientRef = useRef<ConvisWebRTCClient | null>(null);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const connectedAtRef = useRef<number | null>(null);

  // Store config in a ref so the start callback is stable (doesn't change every render)
  const configRef = useRef(config);
  configRef.current = config;

  // Duration timer
  useEffect(() => {
    if (state === 'connected' || state === 'listening' || state === 'ai-speaking') {
      if (!connectedAtRef.current) {
        connectedAtRef.current = Date.now();
      }
      durationTimerRef.current = setInterval(() => {
        if (connectedAtRef.current) {
          setDuration(Math.floor((Date.now() - connectedAtRef.current) / 1000));
        }
      }, 1000);
    } else {
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
        durationTimerRef.current = null;
      }
      if (state === 'idle' || state === 'disconnected') {
        connectedAtRef.current = null;
      }
    }

    return () => {
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
      }
    };
  }, [state]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clientRef.current?.stop();
    };
  }, []);

  const start = useCallback(async () => {
    // Stop any previous call first to release its AudioContext (Chrome limits ~6 concurrent)
    if (clientRef.current) {
      await clientRef.current.stop();
      clientRef.current = null;
    }

    // Reset state for new call
    setTranscripts([]);
    setDuration(0);
    connectedAtRef.current = null;

    const client = new ConvisWebRTCClient({
      ...configRef.current,
      onStateChange: (newState) => {
        setState(newState);
      },
      onTranscript: (text, isFinal, speaker) => {
        setTranscripts((prev) => {
          // If not final, update the last interim transcript for this speaker
          if (!isFinal) {
            const lastIdx = prev.length - 1;
            if (lastIdx >= 0 && !prev[lastIdx].isFinal && prev[lastIdx].speaker === speaker) {
              const updated = [...prev];
              updated[lastIdx] = { speaker: speaker as 'user' | 'assistant', text, isFinal, timestamp: Date.now() };
              return updated;
            }
          }
          return [...prev, { speaker: speaker as 'user' | 'assistant', text, isFinal, timestamp: Date.now() }];
        });
      },
      onError: (error) => {
        console.error('[WebRTC Hook] Error:', error.message);
      },
    });

    clientRef.current = client;
    await client.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stop = useCallback(async () => {
    if (clientRef.current) {
      await clientRef.current.stop();
      clientRef.current = null;
    }
  }, []);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      clientRef.current?.setMuted(next);
      return next;
    });
  }, []);

  const setVolume = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    setVolumeState(clamped);
    clientRef.current?.setVolume(clamped);
  }, []);

  return { state, transcripts, duration, isMuted, volume, start, stop, toggleMute, setVolume };
}

export default ConvisWebRTCClient;
