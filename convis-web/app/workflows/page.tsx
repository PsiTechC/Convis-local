'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SidebarNavigation } from '../components/Navigation';
import { TopBar } from '../components/TopBar';
import { N8nImportModal } from '../components/N8nImportModal';

interface StoredUser {
  _id: string;
  email: string;
  companyName?: string;
  name?: string;
  fullName?: string;
}

interface Workflow {
  _id: string;
  name: string;
  description?: string;
  trigger_event: string;
  is_active: boolean;
  priority: number;
  execution_count: number;
  success_count: number;
  created_at: string;
  actions: any[];
  conditions: any[];
}

interface WorkflowStats {
  total_workflows: number;
  active_workflows: number;
  total_executions: number;
  success_rate: number;
}

export default function WorkflowsPage() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [stats, setStats] = useState<WorkflowStats>({
    total_workflows: 0,
    active_workflows: 0,
    total_executions: 0,
    success_rate: 0
  });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [showImportModal, setShowImportModal] = useState(false);

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

    fetchWorkflows();
    fetchStats();
  }, []);

  const fetchWorkflows = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/workflows/`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setWorkflows(data.workflows || []);
      }
    } catch (error) {
      console.error('Error fetching workflows:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/workflows/workflow-stats`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setStats(data.statistics || data);
      }
    } catch (error) {
      console.error('Error fetching stats:', error);
    }
  };

  const handleToggleWorkflow = async (workflowId: string) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/workflows/${workflowId}/toggle`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        fetchWorkflows();
        fetchStats();
      }
    } catch (error) {
      console.error('Error toggling workflow:', error);
    }
  };

  const handleDeleteWorkflow = async (workflowId: string) => {
    if (!confirm('Are you sure you want to delete this workflow?')) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/workflows/${workflowId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        fetchWorkflows();
        fetchStats();
      }
    } catch (error) {
      console.error('Error deleting workflow:', error);
    }
  };

  const filteredWorkflows = workflows.filter(workflow => {
    if (filter === 'all') return true;
    if (filter === 'active') return workflow.is_active;
    if (filter === 'inactive') return !workflow.is_active;
    return true;
  });

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('clientId');
    localStorage.removeItem('isAdmin');
    router.push('/login');
  };

  const getTriggerLabel = (event: string) => {
    const labels: Record<string, string> = {
      'call_completed': 'Call Completed',
      'call_failed': 'Call Failed',
      'campaign_started': 'Campaign Started',
      'campaign_completed': 'Campaign Completed'
    };
    return labels[event] || event;
  };

  const handleImportComplete = () => {
    // Refresh workflows list after successful import
    fetchWorkflows();
    fetchStats();
  };

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
          onLogout={handleLogout}
          token={token || undefined}
        />

        <main className={`flex-1 overflow-auto p-8 ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className={`text-3xl font-bold mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Workflows
              </h1>
              <p className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                Automate your call processing with smart workflows
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowImportModal(true)}
                className="px-6 py-3 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white rounded-lg font-medium transition-all shadow-lg shadow-green-500/30 flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                Import n8n
              </button>
              <button
                onClick={() => router.push('/workflows/n8n?page=new')}
                className="px-6 py-3 bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white rounded-lg font-medium transition-all shadow-lg shadow-orange-500/30 flex items-center gap-2"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                </svg>
                n8n Editor (400+ Apps)
              </button>
              <button
                onClick={() => router.push('/workflows/builder')}
                className="px-6 py-3 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white rounded-lg font-medium transition-all shadow-lg shadow-purple-500/30 flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Visual Builder (150+ Nodes)
              </button>
              <button
                onClick={() => router.push('/workflows/create')}
                className="px-6 py-3 bg-gray-600 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Form Builder
              </button>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div className={`p-6 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border shadow-sm`}>
              <div className="flex items-center justify-between mb-2">
                <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Total Workflows</span>
                <svg className={`w-5 h-5 ${isDarkMode ? 'text-purple-400' : 'text-purple-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                {stats.total_workflows}
              </div>
            </div>

            <div className={`p-6 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border shadow-sm`}>
              <div className="flex items-center justify-between mb-2">
                <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Active</span>
                <svg className={`w-5 h-5 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                {stats.active_workflows}
              </div>
            </div>

            <div className={`p-6 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border shadow-sm`}>
              <div className="flex items-center justify-between mb-2">
                <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Executions</span>
                <svg className={`w-5 h-5 ${isDarkMode ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
              </div>
              <div className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                {stats.total_executions}
              </div>
            </div>

            <div className={`p-6 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border shadow-sm`}>
              <div className="flex items-center justify-between mb-2">
                <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Success Rate</span>
                <svg className={`w-5 h-5 ${isDarkMode ? 'text-yellow-400' : 'text-yellow-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
              </div>
              <div className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                {(stats.success_rate || 0).toFixed(0)}%
              </div>
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex gap-2">
              <button
                onClick={() => setFilter('all')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'all'
                    ? isDarkMode ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white'
                    : isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                All Workflows
              </button>
              <button
                onClick={() => setFilter('active')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'active'
                    ? isDarkMode ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white'
                    : isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                Active
              </button>
              <button
                onClick={() => setFilter('inactive')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'inactive'
                    ? isDarkMode ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white'
                    : isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                Inactive
              </button>
            </div>
            <button
              onClick={() => router.push('/workflows/executions')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isDarkMode
                  ? 'bg-gray-700 hover:bg-gray-600 text-white'
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-900'
              }`}
            >
              View Execution Logs
            </button>
          </div>

          {/* Workflows List */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500 mx-auto"></div>
            </div>
          ) : filteredWorkflows.length === 0 ? (
            <div className={`text-center py-16 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border`}>
              <div className={`p-4 rounded-full inline-block mb-4 ${isDarkMode ? 'bg-purple-900/30' : 'bg-purple-100'}`}>
                <svg className={`w-12 h-12 ${isDarkMode ? 'text-purple-400' : 'text-purple-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className={`text-xl font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                No workflows yet
              </h3>
              <p className={`mb-6 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                Create your first workflow to automate call processing
              </p>
              <button
                onClick={() => router.push('/workflows/create')}
                className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors"
              >
                Create Your First Workflow
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {filteredWorkflows.map((workflow) => (
                <div
                  key={workflow._id}
                  className={`p-6 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border hover:shadow-lg transition-shadow`}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                          {workflow.name}
                        </h3>
                        <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                          workflow.is_active
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                        }`}>
                          {workflow.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                      {workflow.description && (
                        <p className={`text-sm mb-3 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          {workflow.description}
                        </p>
                      )}
                      <div className="flex flex-wrap gap-2 mb-3">
                        <span className={`px-3 py-1 rounded-lg text-xs font-medium ${
                          isDarkMode ? 'bg-blue-900/30 text-blue-400' : 'bg-blue-100 text-blue-600'
                        }`}>
                          Trigger: {getTriggerLabel(workflow.trigger_event)}
                        </span>
                        <span className={`px-3 py-1 rounded-lg text-xs font-medium ${
                          isDarkMode ? 'bg-purple-900/30 text-purple-400' : 'bg-purple-100 text-purple-600'
                        }`}>
                          {workflow.actions.length} Action{workflow.actions.length !== 1 ? 's' : ''}
                        </span>
                        {workflow.conditions.length > 0 && (
                          <span className={`px-3 py-1 rounded-lg text-xs font-medium ${
                            isDarkMode ? 'bg-orange-900/30 text-orange-400' : 'bg-orange-100 text-orange-600'
                          }`}>
                            {workflow.conditions.length} Condition{workflow.conditions.length !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Executions: <span className="font-semibold">{workflow.execution_count}</span>
                        </span>
                        <span className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Success: <span className="font-semibold text-green-500">{workflow.success_count}</span>
                        </span>
                        {workflow.execution_count > 0 && (
                          <span className={`${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                            Rate: <span className="font-semibold">{((workflow.success_count / workflow.execution_count) * 100).toFixed(0)}%</span>
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggleWorkflow(workflow._id)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                          workflow.is_active
                            ? isDarkMode
                              ? 'bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-400'
                              : 'bg-yellow-50 hover:bg-yellow-100 text-yellow-600'
                            : isDarkMode
                            ? 'bg-green-600/20 hover:bg-green-600/30 text-green-400'
                            : 'bg-green-50 hover:bg-green-100 text-green-600'
                        }`}
                      >
                        {workflow.is_active ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        onClick={() => router.push(`/workflows/${workflow._id}`)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                          isDarkMode
                            ? 'bg-blue-600 hover:bg-blue-700 text-white'
                            : 'bg-blue-500 hover:bg-blue-600 text-white'
                        }`}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDeleteWorkflow(workflow._id)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                          isDarkMode
                            ? 'bg-red-600/20 hover:bg-red-600/30 text-red-400'
                            : 'bg-red-50 hover:bg-red-100 text-red-600'
                        }`}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>
      </div>

      {/* n8n Import Modal */}
      <N8nImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={handleImportComplete}
        isDarkMode={isDarkMode}
      />
    </div>
  );
}
