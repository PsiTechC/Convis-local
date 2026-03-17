'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SidebarNavigation } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';
import { VisualWorkflowBuilder } from '../../components/VisualWorkflowBuilder';

interface StoredUser {
  _id: string;
  email: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

export default function CreateVisualWorkflowPage() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [showNameModal, setShowNameModal] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [currentSteps, setCurrentSteps] = useState<any[]>([]);

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
  }, []);

  const handleSaveWorkflow = async (steps: any[]) => {
    if (!workflowName) {
      setShowNameModal(true);
      return;
    }

    setIsSaving(true);

    try {
      const token = localStorage.getItem('token');

      // Extract trigger
      const trigger = steps.find(s => s.type === 'trigger');
      const filters = steps.filter(s => s.type === 'filter');
      const actions = steps.filter(s => s.type === 'action');

      const workflowData = {
        name: workflowName,
        description: workflowDescription,
        trigger_event: trigger?.config?.trigger_event || 'call_completed',
        conditions: filters.map(f => f.config),
        actions: actions.map(a => ({
          type: a.name.toLowerCase().replace(/\s+/g, '_'),
          config: a.config,
          integration_id: a.config.integration_id
        })),
        is_active: true,
        priority: 1
      };

      const response = await fetch(`${API_URL}/api/workflows/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(workflowData)
      });

      if (response.ok) {
        router.push('/workflows');
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to create workflow'}`);
      }
    } catch (error) {
      console.error('Error saving workflow:', error);
      alert('Failed to save workflow');
    } finally {
      setIsSaving(false);
    }
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
          token={token || undefined}
        />

        {/* Top Action Bar */}
        <div className={`border-b ${isDarkMode ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'} px-6 py-4`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/workflows')}
                className={`p-2 rounded-lg ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
              >
                <svg className={`w-5 h-5 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div>
                <h1 className={`text-xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  {workflowName || 'Untitled Workflow'}
                </h1>
                <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  {workflowDescription || 'Add a description'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowNameModal(true)}
                className={`px-4 py-2 rounded-lg border transition-colors ${
                  isDarkMode
                    ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                Edit Name
              </button>
              <button
                onClick={() => handleSaveWorkflow(currentSteps)}
                disabled={isSaving}
                className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                  isSaving
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-purple-600 hover:bg-purple-700'
                } text-white`}
              >
                {isSaving ? 'Publishing...' : 'Publish'}
              </button>
            </div>
          </div>
        </div>

        {/* Visual Workflow Builder */}
        <div className="flex-1 overflow-hidden">
          <VisualWorkflowBuilder
            isDarkMode={isDarkMode}
            onSave={handleSaveWorkflow}
            onChange={(steps) => setCurrentSteps(steps)}
          />
        </div>
      </div>

      {/* Name/Description Modal */}
      {showNameModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className={`max-w-md w-full rounded-xl ${isDarkMode ? 'bg-gray-800' : 'bg-white'} p-6`}>
            <h2 className={`text-2xl font-bold mb-4 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
              Name Your Workflow
            </h2>
            <div className="space-y-4">
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Workflow Name *
                </label>
                <input
                  type="text"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  placeholder="e.g., Send email after call"
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  } focus:outline-none focus:ring-2 focus:ring-purple-500`}
                />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Description (optional)
                </label>
                <textarea
                  value={workflowDescription}
                  onChange={(e) => setWorkflowDescription(e.target.value)}
                  placeholder="What does this workflow do?"
                  rows={3}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  } focus:outline-none focus:ring-2 focus:ring-purple-500`}
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setShowNameModal(false)}
                  className={`flex-1 px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                      : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  Cancel
                </button>
                <button
                  onClick={() => setShowNameModal(false)}
                  disabled={!workflowName}
                  className={`flex-1 px-4 py-2 rounded-lg font-medium text-white ${
                    !workflowName
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-purple-600 hover:bg-purple-700'
                  }`}
                >
                  Continue
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
