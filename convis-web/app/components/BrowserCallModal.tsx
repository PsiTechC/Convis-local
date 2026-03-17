"use client";

import React, { useEffect, useRef } from "react";
import { useWebRTCCall, CallState, Transcript } from "@/lib/webrtc-client";
import { API_BASE_URL } from "@/lib/api";

interface BrowserCallModalProps {
  isOpen: boolean;
  onClose: () => void;
  assistantId: string;
  assistantName: string;
  isDarkMode: boolean;
  apiBaseUrl?: string;
  userId?: string;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function stateLabel(state: CallState): string {
  switch (state) {
    case "idle":
      return "Ready";
    case "connecting":
      return "Connecting...";
    case "connected":
      return "Connected";
    case "listening":
      return "Listening";
    case "ai-speaking":
      return "AI Speaking";
    case "disconnected":
      return "Call Ended";
    case "error":
      return "Error";
    default:
      return state;
  }
}

function stateColor(state: CallState, isDarkMode: boolean): string {
  switch (state) {
    case "connecting":
      return isDarkMode ? "text-yellow-400" : "text-yellow-600";
    case "connected":
    case "listening":
      return isDarkMode ? "text-green-400" : "text-green-600";
    case "ai-speaking":
      return isDarkMode ? "text-blue-400" : "text-blue-600";
    case "disconnected":
      return isDarkMode ? "text-gray-400" : "text-gray-500";
    case "error":
      return isDarkMode ? "text-red-400" : "text-red-600";
    default:
      return isDarkMode ? "text-gray-300" : "text-gray-700";
  }
}

export default function BrowserCallModal({
  isOpen,
  onClose,
  assistantId,
  assistantName,
  isDarkMode,
  apiBaseUrl,
  userId,
}: BrowserCallModalProps) {
  const resolvedApiBaseUrl =
    apiBaseUrl ||
    process.env.NEXT_PUBLIC_API_URL ||
    API_BASE_URL;

  const {
    state,
    transcripts,
    duration,
    isMuted,
    volume,
    start,
    stop,
    toggleMute,
    setVolume,
  } = useWebRTCCall({
    apiBaseUrl: resolvedApiBaseUrl,
    assistantId,
    userId,
  });

  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Auto-start call on mount, auto-stop on unmount.
  // The component returns null when !isOpen, so mount ≡ modal opened, unmount ≡ modal closed.
  // start/stop are stable refs (never change), so this effect fires exactly once.
  useEffect(() => {
    start().catch((err) => {
      console.error("[BrowserCallModal] Failed to start:", err);
    });

    return () => {
      stop().catch(console.error);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcripts]);

  // Cleanup on close
  const handleClose = async () => {
    if (
      state === "connected" ||
      state === "listening" ||
      state === "ai-speaking" ||
      state === "connecting"
    ) {
      await stop();
    }
    onClose();
  };

  if (!isOpen) return null;

  const isActive =
    state === "connected" ||
    state === "listening" ||
    state === "ai-speaking";

  return (
    <div
      className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4"
      onClick={handleClose}
    >
      <div
        className={`${
          isDarkMode ? "bg-gray-800" : "bg-white"
        } rounded-2xl w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className={`px-6 py-4 border-b ${
            isDarkMode ? "border-gray-700" : "border-gray-200"
          } flex items-center justify-between`}
        >
          <div className="flex items-center gap-3">
            {/* Phone icon */}
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                isActive
                  ? "bg-green-500/20"
                  : state === "connecting"
                  ? "bg-yellow-500/20"
                  : "bg-gray-500/20"
              }`}
            >
              <svg
                className={`w-5 h-5 ${
                  isActive
                    ? "text-green-500"
                    : state === "connecting"
                    ? "text-yellow-500"
                    : isDarkMode
                    ? "text-gray-400"
                    : "text-gray-500"
                }`}
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z"
                />
              </svg>
            </div>
            <div>
              <h3
                className={`font-semibold ${
                  isDarkMode ? "text-white" : "text-gray-900"
                }`}
              >
                {assistantName}
              </h3>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-medium ${stateColor(state, isDarkMode)}`}>
                  {stateLabel(state)}
                </span>
                {isActive && (
                  <span
                    className={`text-xs ${
                      isDarkMode ? "text-gray-400" : "text-gray-500"
                    }`}
                  >
                    {formatDuration(duration)}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Close button */}
          <button
            onClick={handleClose}
            className={`p-2 rounded-xl ${
              isDarkMode ? "hover:bg-gray-700" : "hover:bg-gray-100"
            } transition-colors`}
          >
            <svg
              className={`w-5 h-5 ${
                isDarkMode ? "text-gray-400" : "text-gray-500"
              }`}
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Transcript area */}
        <div
          className={`flex-1 overflow-y-auto p-4 min-h-[250px] max-h-[400px] ${
            isDarkMode ? "bg-gray-900/50" : "bg-gray-50"
          }`}
        >
          {state === "connecting" && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3" />
                <p
                  className={`text-sm ${
                    isDarkMode ? "text-gray-400" : "text-gray-500"
                  }`}
                >
                  Connecting to {assistantName}...
                </p>
              </div>
            </div>
          )}

          {(state === "idle" || state === "error") && (
            <div className="flex items-center justify-center h-full">
              <p
                className={`text-sm ${
                  isDarkMode ? "text-gray-400" : "text-gray-500"
                }`}
              >
                {state === "error"
                  ? "Connection failed. Close and try again."
                  : "Click to start a browser call."}
              </p>
            </div>
          )}

          {(isActive || state === "disconnected") && transcripts.length === 0 && state !== "disconnected" && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="flex justify-center gap-1 mb-3">
                  <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                  <span
                    className="w-2 h-2 bg-green-500 rounded-full animate-pulse"
                    style={{ animationDelay: "0.2s" }}
                  />
                  <span
                    className="w-2 h-2 bg-green-500 rounded-full animate-pulse"
                    style={{ animationDelay: "0.4s" }}
                  />
                </div>
                <p
                  className={`text-sm ${
                    isDarkMode ? "text-gray-400" : "text-gray-500"
                  }`}
                >
                  Listening... Start speaking.
                </p>
              </div>
            </div>
          )}

          {transcripts.length > 0 && (
            <div className="space-y-3">
              {transcripts.map((t, i) => (
                <TranscriptBubble
                  key={i}
                  transcript={t}
                  isDarkMode={isDarkMode}
                />
              ))}
              <div ref={transcriptEndRef} />
            </div>
          )}

          {state === "disconnected" && transcripts.length > 0 && (
            <div className="mt-4 text-center">
              <p
                className={`text-xs ${
                  isDarkMode ? "text-gray-500" : "text-gray-400"
                }`}
              >
                Call ended — {formatDuration(duration)}
              </p>
            </div>
          )}
        </div>

        {/* Controls */}
        <div
          className={`px-6 py-4 border-t ${
            isDarkMode ? "border-gray-700" : "border-gray-200"
          }`}
        >
          {/* Volume slider */}
          {isActive && (
            <div className="flex items-center gap-3 mb-4">
              <svg
                className={`w-4 h-4 ${
                  isDarkMode ? "text-gray-400" : "text-gray-500"
                }`}
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z"
                />
              </svg>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={volume}
                onChange={(e) => setVolume(parseFloat(e.target.value))}
                className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer accent-blue-500"
                style={{
                  background: isDarkMode
                    ? `linear-gradient(to right, #3B82F6 ${volume * 100}%, #374151 ${volume * 100}%)`
                    : `linear-gradient(to right, #3B82F6 ${volume * 100}%, #E5E7EB ${volume * 100}%)`,
                }}
              />
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            {/* Mute button */}
            {isActive && (
              <button
                onClick={toggleMute}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                  isMuted
                    ? "bg-red-500/20 text-red-500 hover:bg-red-500/30"
                    : isDarkMode
                    ? "bg-gray-700 text-gray-300 hover:bg-gray-600"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                {isMuted ? (
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z"
                    />
                  </svg>
                ) : (
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
                    />
                  </svg>
                )}
                {isMuted ? "Unmute" : "Mute"}
              </button>
            )}

            {/* Hang up / Retry */}
            <button
              onClick={
                isActive || state === "connecting"
                  ? handleClose
                  : state === "disconnected" || state === "error"
                  ? () => {
                      start().catch(console.error);
                    }
                  : handleClose
              }
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                isActive || state === "connecting"
                  ? "bg-red-500 hover:bg-red-600 text-white"
                  : state === "disconnected" || state === "error"
                  ? "bg-green-500 hover:bg-green-600 text-white"
                  : "bg-red-500 hover:bg-red-600 text-white"
              }`}
            >
              {isActive || state === "connecting" ? (
                <>
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M15.75 3.75L18 6m0 0l2.25 2.25M18 6l2.25-2.25M18 6l-2.25 2.25m-7.5 8.25c-2.444-2.444-4.243-5.203-5.07-7.527a.75.75 0 01.592-.92l3.062-.51a.75.75 0 01.832.475l1.3 3.25a.75.75 0 01-.218.79l-1.8 1.5a.75.75 0 00-.22.71c.522 2.092 2.168 3.738 4.26 4.26a.75.75 0 00.71-.22l1.5-1.8a.75.75 0 01.79-.218l3.25 1.3a.75.75 0 01.475.832l-.51 3.062a.75.75 0 01-.92.592c-2.324-.827-5.083-2.626-7.527-5.07z"
                    />
                  </svg>
                  Hang Up
                </>
              ) : state === "disconnected" || state === "error" ? (
                <>
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182"
                    />
                  </svg>
                  Call Again
                </>
              ) : (
                "Close"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TranscriptBubble({
  transcript,
  isDarkMode,
}: {
  transcript: Transcript;
  isDarkMode: boolean;
}) {
  const isUser = transcript.speaker === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] px-3.5 py-2 rounded-xl text-sm ${
          isUser
            ? isDarkMode
              ? "bg-blue-600 text-white"
              : "bg-blue-500 text-white"
            : isDarkMode
            ? "bg-gray-700 text-gray-200"
            : "bg-gray-200 text-gray-900"
        } ${!transcript.isFinal ? "opacity-60" : ""}`}
      >
        <p className="leading-relaxed">{transcript.text}</p>
      </div>
    </div>
  );
}
