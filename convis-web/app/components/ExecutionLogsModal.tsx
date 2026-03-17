'use client';

import { useEffect, useState } from 'react';

interface ExecutionLogsProps {
  callId: string;
  isOpen: boolean;
  onClose: () => void;
  isDarkMode: boolean;
}

interface PerformanceMetrics {
  total_turns: number;
  session_duration_ms: number;
  stats: {
    asr?: {
      count: number;
      avg_ms: number;
      min_ms: number;
      max_ms: number;
    };
    llm?: {
      count: number;
      avg_ms: number;
      min_ms: number;
      max_ms: number;
    };
    tts?: {
      count: number;
      avg_ms: number;
      min_ms: number;
      max_ms: number;
    };
  };
  metrics: Array<{
    operation: string;
    elapsed_ms: number;
    turn: number;
    metadata?: Record<string, any>;
  }>;
}

interface TimelineEvent {
  timestamp: string;
  elapsed_ms: number;
  event: string;
  data: Record<string, any>;
}

interface ExecutionLogsData {
  call_id: string;
  has_execution_logs: boolean;
  providers: {
    asr: string;
    tts: string;
    llm: string;
  };
  performance_metrics: PerformanceMetrics;
  timeline: TimelineEvent[];
  timestamp?: string;
  message?: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

export function ExecutionLogsModal({ callId, isOpen, onClose, isDarkMode }: ExecutionLogsProps) {
  const [executionLogs, setExecutionLogs] = useState<ExecutionLogsData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only log in development
  const isDev = process.env.NODE_ENV === 'development';

  useEffect(() => {
    if (isOpen && callId) {
      if (isDev) {
        console.log('[ExecutionLogsModal] Opening modal with callId:', callId);
      }
      fetchExecutionLogs();
    }
  }, [isOpen, callId]);

  const fetchExecutionLogs = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      if (!token) {
        setError('Authentication required');
        return;
      }

      const apiUrl = `${API_URL}/api/dashboard/calls/${callId}/execution-logs`;

      const response = await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        const errorText = await response.text();
        if (isDev) {
          console.error('[ExecutionLogsModal] API Error:', response.status, errorText);
        }
        throw new Error(`Failed to fetch execution logs: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      setExecutionLogs(data);
    } catch (err: any) {
      if (isDev) {
        console.error('[ExecutionLogsModal] Error:', err);
      }
      setError(err.message || 'Failed to load execution logs');
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  const formatMs = (ms: number) => `${Math.round(ms)}ms`;
  const formatDuration = (ms: number) => {
    const seconds = ms / 1000;
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.round(seconds % 60);
    return `${minutes}m ${remainingSeconds}s`;
  };

  // Group metrics by turn
  const metricsByTurn: Record<number, any[]> = {};
  if (executionLogs?.performance_metrics?.metrics) {
    executionLogs.performance_metrics.metrics.forEach(metric => {
      if (!metricsByTurn[metric.turn]) {
        metricsByTurn[metric.turn] = [];
      }
      metricsByTurn[metric.turn].push(metric);
    });
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4 animate-fadeIn" onClick={onClose}>
      <div
        className={`${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className={`px-6 py-5 border-b ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} flex items-center justify-between bg-gradient-to-r from-purple-500/10 to-blue-500/10`}>
          <div>
            <h2 className={`text-2xl font-bold flex items-center gap-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
              <svg className="w-7 h-7 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 00-2-2m0 0h2a2 2 0 012 2v0a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Agent Execution Logs
            </h2>
            <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
              Millisecond-precision performance breakdown
            </p>
          </div>
          <button
            onClick={onClose}
            className={`p-2 rounded-xl ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-neutral-light'} transition-colors`}
          >
            <svg className={`w-6 h-6 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500 mx-auto mb-4"></div>
                <p className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Loading execution logs...</p>
              </div>
            </div>
          ) : error ? (
            <div className={`p-6 rounded-xl ${isDarkMode ? 'bg-red-900/20 border border-red-800' : 'bg-red-50 border border-red-200'} text-center`}>
              <svg className="w-12 h-12 text-red-500 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <p className={`text-lg font-semibold ${isDarkMode ? 'text-red-400' : 'text-red-700'}`}>
                {error}
              </p>
            </div>
          ) : !executionLogs?.has_execution_logs ? (
            <div className={`p-8 rounded-xl ${isDarkMode ? 'bg-yellow-900/20 border border-yellow-800' : 'bg-yellow-50 border border-yellow-200'} text-center`}>
              <svg className="w-16 h-16 text-yellow-500 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-yellow-400' : 'text-yellow-700'}`}>
                No Execution Logs Available
              </p>
              <p className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                {executionLogs?.message || 'This feature is only available for calls made after the execution logging system was enabled.'}
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Providers Section */}
              <div className={`p-5 rounded-xl ${isDarkMode ? 'bg-gradient-to-br from-purple-900/20 to-blue-900/20 border border-purple-800' : 'bg-gradient-to-br from-purple-50 to-blue-50 border border-purple-200'}`}>
                <h3 className={`text-lg font-bold mb-4 flex items-center gap-2 ${isDarkMode ? 'text-purple-300' : 'text-purple-900'}`}>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  Voice Provider Configuration
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Speech-to-Text (ASR)
                    </p>
                    <p className={`text-lg font-bold ${isDarkMode ? 'text-purple-300' : 'text-purple-700'}`}>
                      {executionLogs.providers.asr}
                    </p>
                  </div>
                  <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Language Model (LLM)
                    </p>
                    <p className={`text-lg font-bold ${isDarkMode ? 'text-blue-300' : 'text-blue-700'}`}>
                      {executionLogs.providers.llm}
                    </p>
                  </div>
                  <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Text-to-Speech (TTS)
                    </p>
                    <p className={`text-lg font-bold ${isDarkMode ? 'text-green-300' : 'text-green-700'}`}>
                      {executionLogs.providers.tts}
                    </p>
                  </div>
                </div>
              </div>

              {/* Session Summary */}
              <div className={`p-5 rounded-xl ${isDarkMode ? 'bg-gradient-to-br from-green-900/20 to-teal-900/20 border border-green-800' : 'bg-gradient-to-br from-green-50 to-teal-50 border border-green-200'}`}>
                <h3 className={`text-lg font-bold mb-4 flex items-center gap-2 ${isDarkMode ? 'text-green-300' : 'text-green-900'}`}>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 00-2 2z" />
                  </svg>
                  Session Summary
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className={`p-4 rounded-lg text-center ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Total Turns
                    </p>
                    <p className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                      {executionLogs.performance_metrics.total_turns}
                    </p>
                  </div>
                  <div className={`p-4 rounded-lg text-center ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Duration
                    </p>
                    <p className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                      {formatDuration(executionLogs.performance_metrics.session_duration_ms)}
                    </p>
                  </div>
                  <div className={`p-4 rounded-lg text-center ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Avg ASR
                    </p>
                    <p className={`text-3xl font-bold text-purple-500`}>
                      {executionLogs.performance_metrics.stats.asr ? formatMs(executionLogs.performance_metrics.stats.asr.avg_ms) : 'N/A'}
                    </p>
                  </div>
                  <div className={`p-4 rounded-lg text-center ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Avg LLM
                    </p>
                    <p className={`text-3xl font-bold text-blue-500`}>
                      {executionLogs.performance_metrics.stats.llm ? formatMs(executionLogs.performance_metrics.stats.llm.avg_ms) : 'N/A'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Per-Turn Breakdown */}
              {Object.keys(metricsByTurn).length > 0 && (
                <div>
                  <h3 className={`text-lg font-bold mb-4 flex items-center gap-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Turn-by-Turn Performance
                  </h3>
                  <div className="space-y-3">
                    {Object.keys(metricsByTurn).sort((a, b) => Number(b) - Number(a)).map(turn => {
                      const turnMetrics = metricsByTurn[Number(turn)];
                      const asrMetric = turnMetrics.find(m => m.operation === 'asr');
                      const llmMetric = turnMetrics.find(m => m.operation === 'llm');
                      const ttsMetric = turnMetrics.find(m => m.operation === 'tts');
                      const totalMs = (asrMetric?.elapsed_ms || 0) + (llmMetric?.elapsed_ms || 0) + (ttsMetric?.elapsed_ms || 0);

                      return (
                        <div key={turn} className={`p-4 rounded-lg ${isDarkMode ? 'bg-gray-700/50 border border-gray-600' : 'bg-gray-50 border border-gray-200'}`}>
                          <div className="flex items-center justify-between mb-3">
                            <h4 className={`font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                              Turn {turn}
                            </h4>
                            <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                              totalMs < 500
                                ? 'bg-green-500/20 text-green-400'
                                : totalMs < 1000
                                ? 'bg-yellow-500/20 text-yellow-400'
                                : 'bg-red-500/20 text-red-400'
                            }`}>
                              Total: {formatMs(totalMs)}
                            </span>
                          </div>
                          <div className="grid grid-cols-3 gap-3">
                            {asrMetric && (
                              <div className={`p-3 rounded ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                                <p className={`text-xs mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>ASR</p>
                                <p className="text-lg font-bold text-purple-500">{formatMs(asrMetric.elapsed_ms)}</p>
                              </div>
                            )}
                            {llmMetric && (
                              <div className={`p-3 rounded ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                                <p className={`text-xs mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>LLM</p>
                                <p className="text-lg font-bold text-blue-500">{formatMs(llmMetric.elapsed_ms)}</p>
                              </div>
                            )}
                            {ttsMetric && (
                              <div className={`p-3 rounded ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                                <p className={`text-xs mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>TTS</p>
                                <p className="text-lg font-bold text-green-500">{formatMs(ttsMetric.elapsed_ms)}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={`px-6 py-4 border-t ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} flex justify-end`}>
          <button
            onClick={onClose}
            className={`px-6 py-2.5 rounded-xl font-semibold transition-all ${isDarkMode ? 'bg-gray-700 hover:bg-gray-600 text-white' : 'bg-gray-200 hover:bg-gray-300 text-neutral-dark'}`}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
