'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SidebarNavigation } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';

interface StoredUser {
  _id: string;
  email: string;
}

interface WorkflowExecution {
  _id: string;
  workflow_id: string;
  workflow_name?: string;
  trigger_event: string;
  status: 'completed' | 'failed' | 'partial';
  conditions_met: boolean;
  actions_executed: number;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  error_message?: string;
}

function ExecutionsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workflowId = searchParams.get('workflow_id');

  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);

  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'completed' | 'failed'>('all');

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    const theme = localStorage.getItem('theme');

    setToken(storedToken);

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }

    if (theme === 'dark') {
      setIsDarkMode(true);
    }

    fetchExecutions();
  }, [workflowId]);

  const fetchExecutions = async () => {
    try {
      const token = localStorage.getItem('token');
      const url = workflowId
        ? `${process.env.NEXT_PUBLIC_API_URL}/api/workflows/${workflowId}/executions`
        : `${process.env.NEXT_PUBLIC_API_URL}/api/workflows/executions`;

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setExecutions(data.executions || []);
      }
    } catch (error) {
      console.error('Error fetching executions:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredExecutions = executions.filter(execution => {
    if (filter === 'all') return true;
    return execution.status === filter;
  });


  return (
    <div className={`flex h-screen ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
      {/* Sidebar */}
      <SidebarNavigation
        isSidebarCollapsed={isSidebarCollapsed}
        setIsSidebarCollapsed={setIsSidebarCollapsed}
        isDarkMode={isDarkMode}
      />

      {/* Main Content */}
      <div className={`flex-1 flex flex-col overflow-hidden ${isSidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'} transition-all duration-300`}>
        <TopBar
          user={user}
          isDarkMode={isDarkMode}
          isSidebarCollapsed={isSidebarCollapsed}
          onToggleSidebar={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          onToggleTheme={() => {
            setIsDarkMode(!isDarkMode);
            localStorage.setItem('theme', !isDarkMode ? 'dark' : 'light');
          }}
          token={token || undefined}
        />

        <main className={`flex-1 overflow-auto p-8 ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <button
                  onClick={() => router.push('/workflows')}
                  className={`p-2 rounded-lg ${isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'}`}
                >
                  <svg className={`w-5 h-5 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
                <h1 className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Workflow Execution Logs
                </h1>
              </div>
              <p className={`ml-14 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                View and monitor workflow execution history
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setFilter('all')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'all'
                    ? isDarkMode ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white'
                    : isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                All
              </button>
              <button
                onClick={() => setFilter('completed')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'completed'
                    ? isDarkMode ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white'
                    : isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                Completed
              </button>
              <button
                onClick={() => setFilter('failed')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'failed'
                    ? isDarkMode ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white'
                    : isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                Failed
              </button>
            </div>
          </div>

          {/* Executions List */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500 mx-auto"></div>
            </div>
          ) : filteredExecutions.length === 0 ? (
            <div className={`text-center py-16 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border`}>
              <svg className={`w-16 h-16 mx-auto mb-4 ${isDarkMode ? 'text-gray-600' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <h3 className={`text-xl font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                No executions found
              </h3>
              <p className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                Workflows haven&apos;t been triggered yet
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredExecutions.map((execution) => (
                <div
                  key={execution._id}
                  className={`p-6 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border`}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                          {execution.workflow_name || `Workflow ${execution.workflow_id}`}
                        </h3>
                        <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                          execution.status === 'completed'
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                            : execution.status === 'failed'
                            ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                            : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                        }`}>
                          {execution.status.charAt(0).toUpperCase() + execution.status.slice(1)}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-4 text-sm mb-3">
                        <span className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          <strong>Trigger:</strong> {execution.trigger_event}
                        </span>
                        <span className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          <strong>Actions:</strong> {execution.actions_executed}
                        </span>
                        <span className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          <strong>Duration:</strong> {execution.duration_ms}ms
                        </span>
                        <span className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          <strong>Started:</strong> {new Date(execution.started_at).toLocaleString()}
                        </span>
                      </div>
                      {!execution.conditions_met && (
                        <div className={`px-3 py-2 rounded-lg text-sm ${
                          isDarkMode ? 'bg-yellow-900/20 text-yellow-400' : 'bg-yellow-50 text-yellow-700'
                        }`}>
                          Skipped: Conditions not met
                        </div>
                      )}
                      {execution.error_message && (
                        <div className={`px-3 py-2 rounded-lg text-sm ${
                          isDarkMode ? 'bg-red-900/20 text-red-400' : 'bg-red-50 text-red-700'
                        }`}>
                          <strong>Error:</strong> {execution.error_message}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default function ExecutionsPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    }>
      <ExecutionsContent />
    </Suspense>
  );
}
