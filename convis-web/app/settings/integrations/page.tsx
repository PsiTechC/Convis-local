'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SidebarNavigation } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';

interface StoredUser {
  _id: string;
  email: string;
}

interface IntegrationField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  placeholder?: string;
  help?: string;
  default?: any;
  options?: string[];
}

interface IntegrationType {
  type: string;
  name: string;
  description: string;
  icon: string;
  fields: IntegrationField[];
  auth_type?: string;
}

interface IntegrationCategory {
  label: string;
  icon: string;
  integrations: IntegrationType[];
}

interface SavedIntegration {
  _id: string;
  name: string;
  type: string;
  status: string;
  is_active: boolean;
  metadata?: Record<string, any>;
  last_tested_at?: string;
  last_error?: string;
  created_at: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

export default function IntegrationsSettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const [categories, setCategories] = useState<Record<string, IntegrationCategory>>({});
  const [savedIntegrations, setSavedIntegrations] = useState<SavedIntegration[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedIntegrationType, setSelectedIntegrationType] = useState<IntegrationType | null>(null);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [integrationName, setIntegrationName] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    const theme = localStorage.getItem('theme');

    if (!storedToken) {
      router.push('/login');
      return;
    }

    setToken(storedToken);
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    if (theme === 'light') {
      setIsDarkMode(false);
    }

    fetchIntegrationTypes(storedToken);
    fetchSavedIntegrations(storedToken);
  }, [router]);

  const fetchIntegrationTypes = async (authToken: string) => {
    try {
      const response = await fetch(`${API_URL}/api/integrations/types/available`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setCategories(data.categories);
        // Set first category as active
        const firstCategory = Object.keys(data.categories)[0];
        if (firstCategory) {
          setActiveCategory(firstCategory);
        }
      }
    } catch (err) {
      console.error('Error fetching integration types:', err);
    }
  };

  const fetchSavedIntegrations = async (authToken: string) => {
    try {
      const response = await fetch(`${API_URL}/api/integrations/`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setSavedIntegrations(data.integrations || []);
      }
    } catch (err) {
      console.error('Error fetching saved integrations:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddIntegration = (integrationType: IntegrationType) => {
    setSelectedIntegrationType(integrationType);
    setIntegrationName(`My ${integrationType.name}`);
    setFormData({});
    setTestResult(null);
    setError(null);
    setShowAddModal(true);
  };

  const handleFieldChange = (fieldName: string, value: any) => {
    setFormData((prev) => ({ ...prev, [fieldName]: value }));
  };

  const handleTestConnection = async () => {
    if (!selectedIntegrationType || !token) return;

    setIsTesting(true);
    setTestResult(null);
    setError(null);

    try {
      // First save the integration
      const createResponse = await fetch(`${API_URL}/api/integrations/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: integrationName,
          type: selectedIntegrationType.type,
          credentials: formData,
        }),
      });

      if (!createResponse.ok) {
        const errorData = await createResponse.json();
        throw new Error(errorData.detail || 'Failed to create integration');
      }

      const createData = await createResponse.json();
      const integrationId = createData.integration_id;

      // Test the connection
      const testResponse = await fetch(`${API_URL}/api/integrations/${integrationId}/test`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });

      const testData = await testResponse.json();

      // Build detailed error message with troubleshooting if available
      let errorMessage = testData.message || (testData.success ? 'Connection successful!' : 'Connection failed');
      if (!testData.success && testData.details?.troubleshooting) {
        errorMessage = testData.message + '\n\n' + testData.details.troubleshooting.join('\n');
      }

      setTestResult({
        success: testData.success,
        message: errorMessage,
      });

      if (testData.success) {
        // Refresh the list
        fetchSavedIntegrations(token);
        setTimeout(() => {
          setShowAddModal(false);
        }, 1500);
      } else {
        // Delete the failed integration
        await fetch(`${API_URL}/api/integrations/${integrationId}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch (err: any) {
      setError(err.message || 'Failed to test connection');
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveIntegration = async () => {
    if (!selectedIntegrationType || !token) return;

    setIsSaving(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/integrations/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: integrationName,
          type: selectedIntegrationType.type,
          credentials: formData,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save integration');
      }

      fetchSavedIntegrations(token);
      setShowAddModal(false);
    } catch (err: any) {
      setError(err.message || 'Failed to save integration');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteIntegration = async (integrationId: string) => {
    if (!token || !confirm('Are you sure you want to delete this integration?')) return;

    try {
      await fetch(`${API_URL}/api/integrations/${integrationId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchSavedIntegrations(token);
    } catch (err) {
      console.error('Error deleting integration:', err);
    }
  };

  const handleRetestIntegration = async (integrationId: string) => {
    if (!token) return;

    try {
      const response = await fetch(`${API_URL}/api/integrations/${integrationId}/test`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      alert(data.success ? 'Connection successful!' : `Connection failed: ${data.message}`);
      fetchSavedIntegrations(token);
    } catch (err) {
      console.error('Error testing integration:', err);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-500';
      case 'error':
        return 'bg-red-500';
      case 'testing':
        return 'bg-yellow-500';
      default:
        return 'bg-gray-500';
    }
  };

  const categoryIcons: Record<string, string> = {
    clipboard: '📋',
    users: '👥',
    'message-circle': '💬',
    calendar: '📅',
    database: '🗄️',
    cpu: '🤖',
    'hard-drive': '💾',
    'credit-card': '💳',
    link: '🔗',
  };

  if (isLoading) {
    return (
      <div className="flex h-screen bg-gray-900 items-center justify-center">
        <div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className={`flex h-screen ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
      <SidebarNavigation
        isSidebarCollapsed={isSidebarCollapsed}
        setIsSidebarCollapsed={setIsSidebarCollapsed}
        isDarkMode={isDarkMode}
      />

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

        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-7xl mx-auto">
            {/* Header */}
            <div className="mb-8">
              <h1 className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Integrations
              </h1>
              <p className={`mt-2 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                Connect your favorite apps and services to automate workflows
              </p>
            </div>

            {/* Connected Integrations */}
            {savedIntegrations.length > 0 && (
              <div className="mb-8">
                <h2 className={`text-xl font-semibold mb-4 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Connected ({savedIntegrations.length})
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {savedIntegrations.map((integration) => (
                    <div
                      key={integration._id}
                      className={`p-4 rounded-lg border ${
                        isDarkMode
                          ? 'bg-gray-800 border-gray-700'
                          : 'bg-white border-gray-200'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                              isDarkMode ? 'bg-gray-700' : 'bg-gray-100'
                            }`}
                          >
                            <span className="text-xl">
                              {integration.type === 'jira'
                                ? '📋'
                                : integration.type === 'email'
                                ? '📧'
                                : integration.type === 'slack'
                                ? '💬'
                                : integration.type === 'hubspot'
                                ? '👥'
                                : '🔗'}
                            </span>
                          </div>
                          <div>
                            <h3
                              className={`font-medium ${
                                isDarkMode ? 'text-white' : 'text-gray-900'
                              }`}
                            >
                              {integration.name}
                            </h3>
                            <p
                              className={`text-sm ${
                                isDarkMode ? 'text-gray-400' : 'text-gray-500'
                              }`}
                            >
                              {integration.type}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span
                            className={`w-2 h-2 rounded-full ${getStatusColor(
                              integration.status
                            )}`}
                          />
                        </div>
                      </div>

                      {integration.last_error && (
                        <p className="mt-2 text-xs text-red-400 truncate">
                          {integration.last_error}
                        </p>
                      )}

                      <div className="mt-4 flex gap-2">
                        <button
                          onClick={() => handleRetestIntegration(integration._id)}
                          className={`flex-1 px-3 py-1.5 text-sm rounded-lg ${
                            isDarkMode
                              ? 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}
                        >
                          Test
                        </button>
                        <button
                          onClick={() => handleDeleteIntegration(integration._id)}
                          className="px-3 py-1.5 text-sm rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Category Tabs */}
            <div className="mb-6 flex flex-wrap gap-2">
              {Object.entries(categories).map(([key, category]) => (
                <button
                  key={key}
                  onClick={() => setActiveCategory(key)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeCategory === key
                      ? 'bg-purple-600 text-white'
                      : isDarkMode
                      ? 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  <span className="mr-2">{categoryIcons[category.icon] || '🔗'}</span>
                  {category.label}
                </button>
              ))}
            </div>

            {/* Available Integrations */}
            {activeCategory && categories[activeCategory] && (
              <div>
                <h2
                  className={`text-xl font-semibold mb-4 ${
                    isDarkMode ? 'text-white' : 'text-gray-900'
                  }`}
                >
                  {categories[activeCategory].label}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {categories[activeCategory].integrations.map((integration) => {
                    const isConnected = savedIntegrations.some(
                      (s) => s.type === integration.type
                    );
                    return (
                      <div
                        key={integration.type}
                        className={`p-4 rounded-lg border ${
                          isDarkMode
                            ? 'bg-gray-800 border-gray-700'
                            : 'bg-white border-gray-200'
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <div
                            className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                              isDarkMode ? 'bg-gray-700' : 'bg-gray-100'
                            }`}
                          >
                            {integration.icon.startsWith('http') ? (
                              <img
                                src={integration.icon}
                                alt={integration.name}
                                className="w-6 h-6"
                              />
                            ) : (
                              <span className="text-2xl">
                                {integration.icon === 'mail'
                                  ? '📧'
                                  : integration.icon === 'webhook'
                                  ? '🔗'
                                  : integration.icon === 'key'
                                  ? '🔑'
                                  : '🔌'}
                              </span>
                            )}
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <h3
                                className={`font-medium ${
                                  isDarkMode ? 'text-white' : 'text-gray-900'
                                }`}
                              >
                                {integration.name}
                              </h3>
                              {isConnected && (
                                <span className="px-2 py-0.5 text-xs bg-green-500/20 text-green-400 rounded">
                                  Connected
                                </span>
                              )}
                            </div>
                            <p
                              className={`text-sm mt-1 ${
                                isDarkMode ? 'text-gray-400' : 'text-gray-500'
                              }`}
                            >
                              {integration.description}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => handleAddIntegration(integration)}
                          className={`w-full mt-4 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                            isConnected
                              ? isDarkMode
                                ? 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                              : 'bg-purple-600 text-white hover:bg-purple-700'
                          }`}
                        >
                          {isConnected ? 'Add Another' : 'Connect'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Add Integration Modal */}
      {showAddModal && selectedIntegrationType && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div
            className={`max-w-lg w-full rounded-xl ${
              isDarkMode ? 'bg-gray-800' : 'bg-white'
            } p-6 max-h-[90vh] overflow-y-auto`}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className={`text-xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Connect {selectedIntegrationType.name}
              </h2>
              <button
                onClick={() => setShowAddModal(false)}
                className={`p-2 rounded-lg ${
                  isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
                }`}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              {/* Integration Name */}
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? 'text-gray-300' : 'text-gray-700'
                  }`}
                >
                  Integration Name
                </label>
                <input
                  type="text"
                  value={integrationName}
                  onChange={(e) => setIntegrationName(e.target.value)}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white'
                      : 'bg-white border-gray-300 text-gray-900'
                  } focus:outline-none focus:ring-2 focus:ring-purple-500`}
                />
              </div>

              {/* Dynamic Fields */}
              {selectedIntegrationType.fields.map((field) => (
                <div key={field.name}>
                  <label
                    className={`block text-sm font-medium mb-2 ${
                      isDarkMode ? 'text-gray-300' : 'text-gray-700'
                    }`}
                  >
                    {field.label}
                    {field.required && <span className="text-red-500 ml-1">*</span>}
                  </label>

                  {field.type === 'select' ? (
                    <select
                      value={formData[field.name] || field.default || ''}
                      onChange={(e) => handleFieldChange(field.name, e.target.value)}
                      className={`w-full px-4 py-2 rounded-lg border ${
                        isDarkMode
                          ? 'bg-gray-700 border-gray-600 text-white'
                          : 'bg-white border-gray-300 text-gray-900'
                      } focus:outline-none focus:ring-2 focus:ring-purple-500`}
                    >
                      <option value="">Select...</option>
                      {field.options?.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : field.type === 'boolean' ? (
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={formData[field.name] ?? field.default ?? false}
                        onChange={(e) => handleFieldChange(field.name, e.target.checked)}
                        className="rounded border-gray-600 bg-gray-700 text-purple-500"
                      />
                      <span className={isDarkMode ? 'text-gray-300' : 'text-gray-700'}>
                        Enable
                      </span>
                    </label>
                  ) : (
                    <input
                      type={field.type === 'password' ? 'password' : field.type}
                      value={formData[field.name] || ''}
                      onChange={(e) => handleFieldChange(field.name, e.target.value)}
                      placeholder={field.placeholder}
                      className={`w-full px-4 py-2 rounded-lg border ${
                        isDarkMode
                          ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                          : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                      } focus:outline-none focus:ring-2 focus:ring-purple-500`}
                    />
                  )}

                  {field.help && (
                    <p className={`mt-1 text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                      {field.help}
                    </p>
                  )}
                </div>
              ))}

              {/* Error Message */}
              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <p className="text-sm text-red-400">{error}</p>
                </div>
              )}

              {/* Test Result */}
              {testResult && (
                <div
                  className={`p-3 rounded-lg border ${
                    testResult.success
                      ? 'bg-green-500/10 border-green-500/30'
                      : 'bg-red-500/10 border-red-500/30'
                  }`}
                >
                  <p className={`text-sm whitespace-pre-line ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                    {testResult.message}
                  </p>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setShowAddModal(false)}
                  className={`flex-1 px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                      : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleTestConnection}
                  disabled={isTesting}
                  className={`flex-1 px-4 py-2 rounded-lg font-medium ${
                    isTesting
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-purple-600 hover:bg-purple-700'
                  } text-white`}
                >
                  {isTesting ? 'Testing...' : 'Test & Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
