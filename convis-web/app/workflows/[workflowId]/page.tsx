'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { SidebarNavigation } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';
import { VisualWorkflowBuilder } from '../../components/VisualWorkflowBuilder';

interface StoredUser {
  _id: string;
  email: string;
}

interface Step {
  id: string;
  type: 'trigger' | 'filter' | 'action';
  name: string;
  icon: string;
  config: any;
  position: number;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

export default function EditWorkflowPage() {
  const router = useRouter();
  const params = useParams();
  const workflowId = params.workflowId as string;

  const [user, setUser] = useState<StoredUser | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [showNameModal, setShowNameModal] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [initialSteps, setInitialSteps] = useState<Step[]>([]);
  const [currentSteps, setCurrentSteps] = useState<Step[]>([]);

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    const theme = localStorage.getItem('theme');

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }

    if (theme === 'dark') {
      setIsDarkMode(true);
    }
  }, []);

  // Load existing workflow
  useEffect(() => {
    const loadWorkflow = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_URL}/api/workflows/${workflowId}`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        if (!response.ok) {
          throw new Error('Failed to load workflow');
        }

        const data = await response.json();
        const workflow = data.workflow || data;

        // Check if this is a visual workflow (has graph_data with nodes)
        // If so, redirect to the visual builder
        if (workflow.graph_data && workflow.graph_data.nodes && workflow.graph_data.nodes.length > 0) {
          router.replace(`/workflows/builder?id=${workflowId}`);
          return;
        }

        // Set workflow metadata
        setWorkflowName(workflow.name || '');
        setWorkflowDescription(workflow.description || '');

        // Convert workflow to steps format
        const steps: Step[] = [];

        // Add trigger step
        steps.push({
          id: 'trigger-1',
          type: 'trigger',
          name: getTriggerName(workflow.trigger_event),
          icon: getTriggerIcon(workflow.trigger_event),
          config: { trigger_event: workflow.trigger_event },
          position: 0
        });

        // Add filter steps (conditions)
        if (workflow.conditions && workflow.conditions.length > 0) {
          workflow.conditions.forEach((condition: any, index: number) => {
            steps.push({
              id: `filter-${Date.now()}-${index}`,
              type: 'filter',
              name: 'Filter',
              icon: '🔍',
              config: condition,
              position: steps.length
            });
          });
        }

        // Add action steps
        if (workflow.actions && workflow.actions.length > 0) {
          workflow.actions.forEach((action: any, index: number) => {
            steps.push({
              id: `action-${Date.now()}-${index}`,
              type: 'action',
              name: getActionName(action.type),
              icon: getActionIcon(action.type),
              config: action.config || {},
              position: steps.length
            });
          });
        }

        setInitialSteps(steps);
      } catch (error) {
        console.error('Error loading workflow:', error);
        alert('Failed to load workflow');
        router.push('/workflows');
      } finally {
        setIsLoading(false);
      }
    };

    if (workflowId) {
      loadWorkflow();
    }
  }, [workflowId, router]);

  const getTriggerName = (event: string): string => {
    const triggers: { [key: string]: string } = {
      'call_completed': 'Call Completed',
      'call_failed': 'Call Failed',
      'call_no_answer': 'Call No Answer',
      'call_busy': 'Call Busy',
      'call_voicemail': 'Call Voicemail',
      'campaign_completed': 'Campaign Completed'
    };
    return triggers[event] || 'When this happens...';
  };

  const getTriggerIcon = (event: string): string => {
    const icons: { [key: string]: string } = {
      'call_completed': '📞',
      'call_failed': '❌',
      'call_no_answer': '📵',
      'call_busy': '📴',
      'call_voicemail': '📬',
      'campaign_completed': '📊'
    };
    return icons[event] || '⚡';
  };

  const getActionName = (type: string): string => {
    const names: { [key: string]: string } = {
      'send_email': 'Send Email',
      'create_jira_ticket': 'Create Jira Ticket',
      'update_jira_ticket': 'Update Jira Ticket',
      'create_hubspot_contact': 'Create HubSpot Contact',
      'update_hubspot_contact': 'Update HubSpot Contact',
      'create_hubspot_note': 'Create HubSpot Note',
      'send_slack_message': 'Send Slack Message',
      'call_webhook': 'Call Webhook',
      'update_database': 'Update Database'
    };
    return names[type] || type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  const getActionIcon = (type: string): string => {
    const icons: { [key: string]: string } = {
      'send_email': '📧',
      'create_jira_ticket': '🎫',
      'update_jira_ticket': '✏️',
      'create_hubspot_contact': '👤',
      'update_hubspot_contact': '✏️',
      'create_hubspot_note': '📝',
      'send_slack_message': '💬',
      'call_webhook': '🔗',
      'update_database': '💾'
    };
    return icons[type] || '⚙️';
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('clientId');
    localStorage.removeItem('isAdmin');
    router.push('/login');
  };

  const handleSaveWorkflow = async (steps: Step[]) => {
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

      // Map action names back to their type identifiers
      const getActionType = (name: string): string => {
        const typeMap: { [key: string]: string } = {
          'Send Email': 'send_email',
          'Create Jira Ticket': 'create_jira_ticket',
          'Update Jira Ticket': 'update_jira_ticket',
          'Create HubSpot Contact': 'create_hubspot_contact',
          'Update HubSpot Contact': 'update_hubspot_contact',
          'Create HubSpot Note': 'create_hubspot_note',
          'Send Slack Message': 'send_slack_message',
          'Call Webhook': 'call_webhook',
          'Update Database': 'update_database'
        };
        return typeMap[name] || name.toLowerCase().replace(/\s+/g, '_');
      };

      const workflowData = {
        name: workflowName,
        description: workflowDescription,
        trigger_event: trigger?.config?.trigger_event || 'call_completed',
        conditions: filters.map(f => f.config),
        actions: actions.map(a => ({
          type: getActionType(a.name),
          config: a.config,
          integration_id: a.config.integration_id
        })),
        is_active: true,
        priority: 1
      };

      const response = await fetch(`${API_URL}/api/workflows/${workflowId}`, {
        method: 'PUT',
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
        alert(`Error: ${error.detail || 'Failed to update workflow'}`);
      }
    } catch (error) {
      console.error('Error saving workflow:', error);
      alert('Failed to save workflow');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
      </div>
    );
  }

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
                onClick={() => handleSaveWorkflow(currentSteps.length > 0 ? currentSteps : initialSteps)}
                disabled={isSaving}
                className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                  isSaving
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-purple-600 hover:bg-purple-700'
                } text-white`}
              >
                {isSaving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>

        {/* Visual Workflow Builder */}
        <div className="flex-1 overflow-hidden">
          <VisualWorkflowBuilder
            isDarkMode={isDarkMode}
            onSave={(steps) => {
              setCurrentSteps(steps);
              handleSaveWorkflow(steps);
            }}
            onChange={(steps) => {
              setCurrentSteps(steps);
            }}
            initialSteps={initialSteps}
          />
        </div>
      </div>

      {/* Name/Description Modal */}
      {showNameModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className={`max-w-md w-full rounded-xl ${isDarkMode ? 'bg-gray-800' : 'bg-white'} p-6`}>
            <h2 className={`text-2xl font-bold mb-4 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
              Edit Workflow Name
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
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
