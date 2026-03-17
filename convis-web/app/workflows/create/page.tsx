'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SidebarNavigation } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';

interface StoredUser {
  _id: string;
  email: string;
}

interface Integration {
  _id: string;
  name: string;
  type: string;
}

interface Condition {
  field: string;
  operator: string;
  value: any;
  logic?: string;
}

interface Action {
  type: string;
  integration_id: string;
  config: any;
  on_error?: string;
}

export default function CreateWorkflowPage() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [currentStep, setCurrentStep] = useState(1);

  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    trigger_event: 'call_completed',
    is_active: true,
    priority: 1
  });

  const [conditions, setConditions] = useState<Condition[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [currentAction, setCurrentAction] = useState<Partial<Action>>({
    type: '',
    integration_id: '',
    config: {},
    on_error: 'continue'
  });

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    const theme = localStorage.getItem('theme');

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }

    if (theme === 'dark') {
      setIsDarkMode(true);
    }

    fetchIntegrations();
  }, []);

  const fetchIntegrations = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/integrations/`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setIntegrations(data.integrations || []);
      }
    } catch (error) {
      console.error('Error fetching integrations:', error);
    }
  };

  const handleAddCondition = () => {
    setConditions([...conditions, {
      field: '',
      operator: 'equals',
      value: '',
      logic: conditions.length > 0 ? 'AND' : undefined
    }]);
  };

  const handleUpdateCondition = (index: number, updates: Partial<Condition>) => {
    const newConditions = [...conditions];
    newConditions[index] = { ...newConditions[index], ...updates };
    setConditions(newConditions);
  };

  const handleRemoveCondition = (index: number) => {
    setConditions(conditions.filter((_, i) => i !== index));
  };

  const handleAddAction = () => {
    if (!currentAction.type || !currentAction.integration_id) {
      alert('Please select action type and integration');
      return;
    }

    setActions([...actions, currentAction as Action]);
    setCurrentAction({
      type: '',
      integration_id: '',
      config: {},
      on_error: 'continue'
    });
  };

  const handleRemoveAction = (index: number) => {
    setActions(actions.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!formData.name) {
      alert('Please enter a workflow name');
      return;
    }

    if (actions.length === 0) {
      alert('Please add at least one action');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/workflows/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          ...formData,
          conditions,
          actions
        })
      });

      if (response.ok) {
        router.push('/workflows');
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to create workflow'}`);
      }
    } catch (error) {
      console.error('Error creating workflow:', error);
      alert('Failed to create workflow');
    }
  };

  const getActionIcon = (type: string) => {
    if (type.includes('jira')) {
      return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm-.5 17.5h-1v-11h1v11zm6 0h-1v-11h1v11z"/></svg>;
    } else if (type.includes('hubspot')) {
      return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M18.164 7.93V5.084a2.198 2.198 0 0 0-.975-1.834 2.17 2.17 0 0 0-2.016-.293l-1.677.616V2.198C13.496.982 12.514 0 11.298 0c-1.215 0-2.197.982-2.197 2.198v1.375L7.424 2.957a2.17 2.17 0 0 0-2.016.293 2.198 2.198 0 0 0-.975 1.834v2.847a4.393 4.393 0 0 0 0 8.138v2.847c0 .758.388 1.428.975 1.834a2.17 2.17 0 0 0 2.016.293l1.677-.616v1.375c0 1.216.982 2.198 2.197 2.198 1.216 0 2.198-.982 2.198-2.198v-1.375l1.677.616a2.17 2.17 0 0 0 2.016-.293 2.198 2.198 0 0 0 .975-1.834v-2.847a4.393 4.393 0 0 0 0-8.138z"/></svg>;
    } else {
      return <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>;
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
        />

        <main className={`flex-1 overflow-auto p-8 ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
          {/* Header */}
          <div className="mb-8">
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
                Create New Workflow
              </h1>
            </div>
          </div>

          {/* Progress Steps */}
          <div className="mb-8">
            <div className="flex items-center justify-between">
              {[1, 2, 3, 4].map((step) => (
                <div key={step} className="flex items-center flex-1">
                  <div className={`flex items-center justify-center w-10 h-10 rounded-full ${
                    currentStep >= step
                      ? isDarkMode ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white'
                      : isDarkMode ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-600'
                  }`}>
                    {step}
                  </div>
                  {step < 4 && (
                    <div className={`flex-1 h-1 mx-2 ${
                      currentStep > step
                        ? isDarkMode ? 'bg-purple-600' : 'bg-purple-500'
                        : isDarkMode ? 'bg-gray-700' : 'bg-gray-200'
                    }`} />
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-between mt-2">
              <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Basic Info</span>
              <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Trigger</span>
              <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Conditions</span>
              <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>Actions</span>
            </div>
          </div>

          {/* Step Content */}
          <div className={`p-8 rounded-xl ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border`}>
            {/* Step 1: Basic Info */}
            {currentStep === 1 && (
              <div className="space-y-6">
                <h2 className={`text-2xl font-bold mb-6 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Basic Information
                </h2>
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    Workflow Name *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className={`w-full px-4 py-3 rounded-lg border ${
                      isDarkMode
                        ? 'bg-gray-700 border-gray-600 text-white'
                        : 'bg-white border-gray-300 text-gray-900'
                    } focus:ring-2 focus:ring-purple-500`}
                    placeholder="e.g., Send Call Summary Email"
                  />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    Description (Optional)
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    rows={3}
                    className={`w-full px-4 py-3 rounded-lg border ${
                      isDarkMode
                        ? 'bg-gray-700 border-gray-600 text-white'
                        : 'bg-white border-gray-300 text-gray-900'
                    } focus:ring-2 focus:ring-purple-500`}
                    placeholder="Describe what this workflow does..."
                  />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    Priority
                  </label>
                  <select
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) })}
                    className={`w-full px-4 py-3 rounded-lg border ${
                      isDarkMode
                        ? 'bg-gray-700 border-gray-600 text-white'
                        : 'bg-white border-gray-300 text-gray-900'
                    } focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value={1}>Low</option>
                    <option value={5}>Medium</option>
                    <option value={10}>High</option>
                  </select>
                </div>
                <div className="flex items-center">
                  <input
                    type="checkbox"
                    id="is_active"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
                  />
                  <label htmlFor="is_active" className={`ml-2 text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    Activate workflow immediately
                  </label>
                </div>
              </div>
            )}

            {/* Step 2: Trigger */}
            {currentStep === 2 && (
              <div className="space-y-6">
                <h2 className={`text-2xl font-bold mb-6 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Choose Trigger Event
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <button
                    onClick={() => setFormData({ ...formData, trigger_event: 'call_completed' })}
                    className={`p-6 rounded-lg border-2 text-left transition-all ${
                      formData.trigger_event === 'call_completed'
                        ? isDarkMode
                          ? 'border-purple-600 bg-purple-900/30'
                          : 'border-purple-500 bg-purple-50'
                        : isDarkMode
                        ? 'border-gray-700 hover:border-gray-600'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <svg className={`w-6 h-6 ${formData.trigger_event === 'call_completed' ? 'text-purple-500' : isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <h3 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                        Call Completed
                      </h3>
                    </div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Trigger when a call successfully completes
                    </p>
                  </button>

                  <button
                    onClick={() => setFormData({ ...formData, trigger_event: 'call_failed' })}
                    className={`p-6 rounded-lg border-2 text-left transition-all ${
                      formData.trigger_event === 'call_failed'
                        ? isDarkMode
                          ? 'border-purple-600 bg-purple-900/30'
                          : 'border-purple-500 bg-purple-50'
                        : isDarkMode
                        ? 'border-gray-700 hover:border-gray-600'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <svg className={`w-6 h-6 ${formData.trigger_event === 'call_failed' ? 'text-purple-500' : isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <h3 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                        Call Failed
                      </h3>
                    </div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Trigger when a call fails or encounters an error
                    </p>
                  </button>

                  <button
                    onClick={() => setFormData({ ...formData, trigger_event: 'campaign_started' })}
                    className={`p-6 rounded-lg border-2 text-left transition-all ${
                      formData.trigger_event === 'campaign_started'
                        ? isDarkMode
                          ? 'border-purple-600 bg-purple-900/30'
                          : 'border-purple-500 bg-purple-50'
                        : isDarkMode
                        ? 'border-gray-700 hover:border-gray-600'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <svg className={`w-6 h-6 ${formData.trigger_event === 'campaign_started' ? 'text-purple-500' : isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <h3 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                        Campaign Started
                      </h3>
                    </div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Trigger when a campaign begins
                    </p>
                  </button>

                  <button
                    onClick={() => setFormData({ ...formData, trigger_event: 'campaign_completed' })}
                    className={`p-6 rounded-lg border-2 text-left transition-all ${
                      formData.trigger_event === 'campaign_completed'
                        ? isDarkMode
                          ? 'border-purple-600 bg-purple-900/30'
                          : 'border-purple-500 bg-purple-50'
                        : isDarkMode
                        ? 'border-gray-700 hover:border-gray-600'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <svg className={`w-6 h-6 ${formData.trigger_event === 'campaign_completed' ? 'text-purple-500' : isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                      </svg>
                      <h3 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                        Campaign Completed
                      </h3>
                    </div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Trigger when a campaign finishes
                    </p>
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Conditions */}
            {currentStep === 3 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                    Add Conditions (Optional)
                  </h2>
                  <button
                    onClick={handleAddCondition}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Add Condition
                  </button>
                </div>

                {conditions.length === 0 ? (
                  <div className={`text-center py-12 rounded-lg border-2 border-dashed ${isDarkMode ? 'border-gray-700' : 'border-gray-300'}`}>
                    <svg className={`w-12 h-12 mx-auto mb-4 ${isDarkMode ? 'text-gray-600' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                    </svg>
                    <p className={`mb-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      No conditions added. Workflow will run for all events.
                    </p>
                    <button
                      onClick={handleAddCondition}
                      className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      Add Your First Condition
                    </button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {conditions.map((condition, index) => (
                      <div key={index} className={`p-4 rounded-lg border ${isDarkMode ? 'bg-gray-750 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                        <div className="grid grid-cols-12 gap-4 items-center">
                          {index > 0 && (
                            <div className="col-span-2">
                              <select
                                value={condition.logic}
                                onChange={(e) => handleUpdateCondition(index, { logic: e.target.value })}
                                className={`w-full px-3 py-2 rounded-lg border ${
                                  isDarkMode
                                    ? 'bg-gray-700 border-gray-600 text-white'
                                    : 'bg-white border-gray-300 text-gray-900'
                                }`}
                              >
                                <option value="AND">AND</option>
                                <option value="OR">OR</option>
                              </select>
                            </div>
                          )}
                          <div className={index > 0 ? 'col-span-3' : 'col-span-5'}>
                            <input
                              type="text"
                              value={condition.field}
                              onChange={(e) => handleUpdateCondition(index, { field: e.target.value })}
                              className={`w-full px-3 py-2 rounded-lg border ${
                                isDarkMode
                                  ? 'bg-gray-700 border-gray-600 text-white'
                                  : 'bg-white border-gray-300 text-gray-900'
                              }`}
                              placeholder="Field (e.g., call.duration)"
                            />
                          </div>
                          <div className="col-span-3">
                            <select
                              value={condition.operator}
                              onChange={(e) => handleUpdateCondition(index, { operator: e.target.value })}
                              className={`w-full px-3 py-2 rounded-lg border ${
                                isDarkMode
                                  ? 'bg-gray-700 border-gray-600 text-white'
                                  : 'bg-white border-gray-300 text-gray-900'
                              }`}
                            >
                              <option value="equals">Equals</option>
                              <option value="not_equals">Not Equals</option>
                              <option value="greater_than">Greater Than</option>
                              <option value="less_than">Less Than</option>
                              <option value="contains">Contains</option>
                              <option value="exists">Exists</option>
                            </select>
                          </div>
                          <div className="col-span-3">
                            <input
                              type="text"
                              value={condition.value}
                              onChange={(e) => handleUpdateCondition(index, { value: e.target.value })}
                              className={`w-full px-3 py-2 rounded-lg border ${
                                isDarkMode
                                  ? 'bg-gray-700 border-gray-600 text-white'
                                  : 'bg-white border-gray-300 text-gray-900'
                              }`}
                              placeholder="Value"
                            />
                          </div>
                          <div className="col-span-1">
                            <button
                              onClick={() => handleRemoveCondition(index)}
                              className={`p-2 rounded-lg ${isDarkMode ? 'text-red-400 hover:bg-red-900/30' : 'text-red-600 hover:bg-red-50'}`}
                            >
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-blue-900/20 border-blue-800' : 'bg-blue-50 border-blue-200'} border`}>
                  <p className={`text-sm ${isDarkMode ? 'text-blue-300' : 'text-blue-800'}`}>
                    <strong>Tip:</strong> Use variables like <code className="px-1 bg-black/20 rounded">call.duration</code>, <code className="px-1 bg-black/20 rounded">customer_email</code>, <code className="px-1 bg-black/20 rounded">sentiment</code> to filter workflow execution.
                  </p>
                </div>
              </div>
            )}

            {/* Step 4: Actions */}
            {currentStep === 4 && (
              <div className="space-y-6">
                <h2 className={`text-2xl font-bold mb-6 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Add Actions
                </h2>

                {/* Existing Actions */}
                {actions.length > 0 && (
                  <div className="space-y-4 mb-6">
                    <h3 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                      Configured Actions ({actions.length})
                    </h3>
                    {actions.map((action, index) => (
                      <div key={index} className={`p-4 rounded-lg border ${isDarkMode ? 'bg-gray-750 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg ${isDarkMode ? 'bg-purple-900/30' : 'bg-purple-100'}`}>
                              {getActionIcon(action.type)}
                            </div>
                            <div>
                              <div className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                                {action.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                              </div>
                              <div className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                                {integrations.find(i => i._id === action.integration_id)?.name || 'Unknown'}
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={() => handleRemoveAction(index)}
                            className={`p-2 rounded-lg ${isDarkMode ? 'text-red-400 hover:bg-red-900/30' : 'text-red-600 hover:bg-red-50'}`}
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Add New Action Form */}
                <div className={`p-6 rounded-lg border ${isDarkMode ? 'bg-gray-750 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                  <h3 className={`font-semibold mb-4 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                    Add New Action
                  </h3>
                  <div className="space-y-4">
                    <div>
                      <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                        Integration
                      </label>
                      <select
                        value={currentAction.integration_id}
                        onChange={(e) => {
                          const integration = integrations.find(i => i._id === e.target.value);
                          setCurrentAction({
                            ...currentAction,
                            integration_id: e.target.value,
                            type: integration ? `${integration.type}_action` : ''
                          });
                        }}
                        className={`w-full px-4 py-3 rounded-lg border ${
                          isDarkMode
                            ? 'bg-gray-700 border-gray-600 text-white'
                            : 'bg-white border-gray-300 text-gray-900'
                        }`}
                      >
                        <option value="">Select Integration</option>
                        {integrations.map((integration) => (
                          <option key={integration._id} value={integration._id}>
                            {integration.name} ({integration.type})
                          </option>
                        ))}
                      </select>
                    </div>

                    {currentAction.integration_id && (
                      <>
                        <div>
                          <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                            Action Type
                          </label>
                          <select
                            value={currentAction.type}
                            onChange={(e) => setCurrentAction({ ...currentAction, type: e.target.value })}
                            className={`w-full px-4 py-3 rounded-lg border ${
                              isDarkMode
                                ? 'bg-gray-700 border-gray-600 text-white'
                                : 'bg-white border-gray-300 text-gray-900'
                            }`}
                          >
                            <option value="">Select Action</option>
                            {(() => {
                              const integration = integrations.find(i => i._id === currentAction.integration_id);
                              if (integration?.type === 'jira') {
                                return (
                                  <>
                                    <option value="create_jira_ticket">Create Jira Ticket</option>
                                    <option value="update_jira_ticket">Update Jira Ticket</option>
                                    <option value="add_jira_comment">Add Jira Comment</option>
                                  </>
                                );
                              } else if (integration?.type === 'hubspot') {
                                return (
                                  <>
                                    <option value="create_hubspot_contact">Create HubSpot Contact</option>
                                    <option value="update_hubspot_contact">Update HubSpot Contact</option>
                                    <option value="create_hubspot_note">Create HubSpot Note</option>
                                  </>
                                );
                              } else if (integration?.type === 'email') {
                                return <option value="send_email">Send Email</option>;
                              }
                              return null;
                            })()}
                          </select>
                        </div>

                        <div>
                          <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                            Configuration (JSON)
                          </label>
                          <textarea
                            value={JSON.stringify(currentAction.config, null, 2)}
                            onChange={(e) => {
                              try {
                                setCurrentAction({ ...currentAction, config: JSON.parse(e.target.value) });
                              } catch (_err) {
                                // Invalid JSON, don't update
                              }
                            }}
                            rows={6}
                            className={`w-full px-4 py-3 rounded-lg border font-mono text-sm ${
                              isDarkMode
                                ? 'bg-gray-700 border-gray-600 text-white'
                                : 'bg-white border-gray-300 text-gray-900'
                            }`}
                            placeholder='{"to": "{{customer_email}}", "subject": "Call Summary", "body": "{{call.summary}}"}'
                          />
                        </div>

                        <div>
                          <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                            On Error
                          </label>
                          <select
                            value={currentAction.on_error}
                            onChange={(e) => setCurrentAction({ ...currentAction, on_error: e.target.value })}
                            className={`w-full px-4 py-3 rounded-lg border ${
                              isDarkMode
                                ? 'bg-gray-700 border-gray-600 text-white'
                                : 'bg-white border-gray-300 text-gray-900'
                            }`}
                          >
                            <option value="continue">Continue to next action</option>
                            <option value="stop">Stop workflow execution</option>
                            <option value="retry">Retry action</option>
                          </select>
                        </div>

                        <button
                          onClick={handleAddAction}
                          className="w-full px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors"
                        >
                          Add Action
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {integrations.length === 0 && (
                  <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-yellow-900/20 border-yellow-800' : 'bg-yellow-50 border-yellow-200'} border`}>
                    <p className={`text-sm ${isDarkMode ? 'text-yellow-300' : 'text-yellow-800'}`}>
                      <strong>No integrations found!</strong> Please add an integration first before creating workflows.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Navigation Buttons */}
            <div className="flex justify-between mt-8 pt-6 border-t border-gray-700">
              <button
                onClick={() => setCurrentStep(Math.max(1, currentStep - 1))}
                disabled={currentStep === 1}
                className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                  currentStep === 1
                    ? isDarkMode
                      ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                      : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : isDarkMode
                    ? 'bg-gray-700 hover:bg-gray-600 text-white'
                    : 'bg-gray-100 hover:bg-gray-200 text-gray-900'
                }`}
              >
                Previous
              </button>
              {currentStep < 4 ? (
                <button
                  onClick={() => setCurrentStep(Math.min(4, currentStep + 1))}
                  className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors"
                >
                  Next Step
                </button>
              ) : (
                <button
                  onClick={handleSubmit}
                  disabled={actions.length === 0}
                  className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                    actions.length === 0
                      ? isDarkMode
                        ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                        : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                      : 'bg-green-600 hover:bg-green-700 text-white'
                  }`}
                >
                  Create Workflow
                </button>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
