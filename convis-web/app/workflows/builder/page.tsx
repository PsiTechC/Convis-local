'use client';

import { Suspense, useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Node, Edge } from 'reactflow';
import { SidebarNavigation } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';
import { WorkflowCanvasWithProvider } from '../../components/WorkflowCanvas';

interface StoredUser {
  _id: string;
  email: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

function WorkflowBuilderContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workflowId = searchParams.get('id');

  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(true); // Dark mode by default for builder
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);

  const [workflowName, setWorkflowName] = useState('Untitled Workflow');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [showNameModal, setShowNameModal] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(!!workflowId);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  // Load user and theme
  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    const theme = localStorage.getItem('theme');

    setToken(storedToken);

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }

    if (theme === 'light') {
      setIsDarkMode(false);
    }

    // Show name modal for new workflows
    if (!workflowId) {
      setShowNameModal(true);
    }
  }, [workflowId]);

  // Load existing workflow if editing
  useEffect(() => {
    if (workflowId && token) {
      loadWorkflow(workflowId);
    }
  }, [workflowId, token]);

  const loadWorkflow = async (id: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/workflows/${id}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        const workflow = data.workflow;

        setWorkflowName(workflow.name || 'Untitled Workflow');
        setWorkflowDescription(workflow.description || '');

        // Load graph data if available
        if (workflow.graph_data) {
          setNodes(workflow.graph_data.nodes || []);
          setEdges(workflow.graph_data.edges || []);
        }
      } else {
        console.error('Failed to load workflow');
        router.push('/workflows');
      }
    } catch (error) {
      console.error('Error loading workflow:', error);
      router.push('/workflows');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCanvasChange = useCallback((newNodes: Node[], newEdges: Edge[]) => {
    setNodes(newNodes);
    setEdges(newEdges);
  }, []);

  const handleSave = async (publish: boolean = false) => {
    if (!workflowName.trim()) {
      setShowNameModal(true);
      return;
    }

    setIsSaving(true);

    try {
      // Find trigger node to determine trigger event
      const triggerNode = nodes.find((n) => n.type === 'trigger');
      const triggerEvent = triggerNode?.data.triggerType || 'webhook';

      // Convert nodes/edges to workflow format
      const workflowData = {
        name: workflowName,
        description: workflowDescription,
        trigger_event: triggerEvent,
        is_active: publish,
        // Store full graph data for the visual builder
        graph_data: {
          nodes: nodes.map((n) => ({
            id: n.id,
            type: n.type,
            position: n.position,
            data: n.data,
          })),
          edges: edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle,
            targetHandle: e.targetHandle,
          })),
        },
        // Also convert to legacy format for execution engine
        conditions: nodes
          .filter((n) => n.type === 'condition')
          .map((n) => n.data.config || {}),
        actions: nodes
          .filter((n) => n.type === 'action' || n.type === 'code')
          .map((n) => ({
            type: n.data.actionType || n.data.codeType || n.type,
            config: n.data.config || {},
          })),
      };

      const method = workflowId ? 'PUT' : 'POST';
      const url = workflowId
        ? `${API_URL}/api/workflows/${workflowId}`
        : `${API_URL}/api/workflows/`;

      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(workflowData),
      });

      if (response.ok) {
        const result = await response.json();
        if (!workflowId && result.workflow_id) {
          // Redirect to edit URL for newly created workflow
          router.replace(`/workflows/builder?id=${result.workflow_id}`);
        }

        // Show success feedback
        if (publish) {
          alert('Workflow published successfully!');
          router.push('/workflows');
        }
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to save workflow'}`);
      }
    } catch (error) {
      console.error('Error saving workflow:', error);
      alert('Failed to save workflow. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-screen bg-gray-900 items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading workflow...</p>
        </div>
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
      <div
        className={`flex-1 flex flex-col overflow-hidden ${
          isSidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'
        } transition-all duration-300`}
      >
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
        <div
          className={`border-b ${
            isDarkMode ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'
          } px-6 py-3`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/workflows')}
                className={`p-2 rounded-lg ${
                  isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
                }`}
              >
                <svg
                  className={`w-5 h-5 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 19l-7-7 7-7"
                  />
                </svg>
              </button>

              <div
                className="cursor-pointer"
                onClick={() => setShowNameModal(true)}
              >
                <h1
                  className={`text-lg font-bold ${
                    isDarkMode ? 'text-white' : 'text-gray-900'
                  }`}
                >
                  {workflowName}
                </h1>
                {workflowDescription && (
                  <p
                    className={`text-sm ${
                      isDarkMode ? 'text-gray-400' : 'text-gray-600'
                    }`}
                  >
                    {workflowDescription}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Node Count */}
              <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                {nodes.length} nodes
              </span>

              <button
                onClick={() => handleSave(false)}
                disabled={isSaving}
                className={`px-4 py-2 rounded-lg border transition-colors ${
                  isDarkMode
                    ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                } ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {isSaving ? 'Saving...' : 'Save Draft'}
              </button>

              <button
                onClick={() => handleSave(true)}
                disabled={isSaving || nodes.length === 0}
                className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                  isSaving || nodes.length === 0
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
          <WorkflowCanvasWithProvider
            initialNodes={nodes}
            initialEdges={edges}
            onChange={handleCanvasChange}
          />
        </div>
      </div>

      {/* Name/Description Modal */}
      {showNameModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div
            className={`max-w-md w-full rounded-xl ${
              isDarkMode ? 'bg-gray-800' : 'bg-white'
            } p-6`}
          >
            <h2
              className={`text-2xl font-bold mb-4 ${
                isDarkMode ? 'text-white' : 'text-gray-900'
              }`}
            >
              {workflowId ? 'Edit Workflow' : 'Create New Workflow'}
            </h2>
            <div className="space-y-4">
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? 'text-gray-300' : 'text-gray-700'
                  }`}
                >
                  Workflow Name *
                </label>
                <input
                  type="text"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  placeholder="e.g., Process incoming webhook"
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  } focus:outline-none focus:ring-2 focus:ring-purple-500`}
                  autoFocus
                />
              </div>
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? 'text-gray-300' : 'text-gray-700'
                  }`}
                >
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
                {workflowId && (
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
                )}
                <button
                  onClick={() => setShowNameModal(false)}
                  disabled={!workflowName.trim()}
                  className={`flex-1 px-4 py-2 rounded-lg font-medium text-white ${
                    !workflowName.trim()
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-purple-600 hover:bg-purple-700'
                  }`}
                >
                  {workflowId ? 'Update' : 'Start Building'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Loading component for Suspense fallback
function WorkflowBuilderLoading() {
  return (
    <div className="flex h-screen bg-gray-900 items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-gray-400">Loading workflow builder...</p>
      </div>
    </div>
  );
}

export default function WorkflowBuilderPage() {
  return (
    <Suspense fallback={<WorkflowBuilderLoading />}>
      <WorkflowBuilderContent />
    </Suspense>
  );
}
