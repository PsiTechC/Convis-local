'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { NAV_ITEMS, NavigationItem } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';

interface StoredUser {
  _id: string;
  email: string;
  companyName?: string;
  name?: string;
  fullName?: string;
}

interface JiraIntegration {
  _id: string;
  name: string;
  credentials: {
    masked: boolean;
  };
  metadata?: {
    base_url?: string;
    email?: string;
  };
  status: string;
  is_active: boolean;
  created_at: string;
}

export default function JiraIntegrationPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [activeNav, setActiveNav] = useState('Integrations');
  const [openDropdown, setOpenDropdown] = useState<string | null>('Integrations');

  const [integrations, setIntegrations] = useState<JiraIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showTroubleshootModal, setShowTroubleshootModal] = useState(false);
  const [troubleshootData, setTroubleshootData] = useState<{
    success: boolean;
    message: string;
    troubleshooting?: string[];
  } | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    domain: '',
    email: '',
    api_token: ''
  });

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

    fetchIntegrations();
  }, []);

  const fetchIntegrations = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/integrations/?type=jira`, {
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
    } finally {
      setLoading(false);
    }
  };

  // Helper function to normalize Jira URL
  const normalizeJiraUrl = (url: string): string => {
    if (!url) return url;

    let normalizedUrl = url.trim();

    // Add https:// if no scheme provided
    if (!normalizedUrl.startsWith('http://') && !normalizedUrl.startsWith('https://')) {
      normalizedUrl = 'https://' + normalizedUrl;
    }

    try {
      const parsed = new URL(normalizedUrl);
      // Extract just the hostname (removes path like /jira/software/projects/...)
      return `https://${parsed.hostname}`;
    } catch {
      // If URL parsing fails, return as-is (backend will handle)
      return normalizedUrl;
    }
  };

  const handleAddIntegration = async (e: React.FormEvent) => {
    e.preventDefault();

    // Normalize the Jira URL before sending
    const normalizedDomain = normalizeJiraUrl(formData.domain);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/integrations/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: formData.name,
          type: 'jira',
          credentials: {
            base_url: normalizedDomain,
            email: formData.email,
            api_token: formData.api_token
          }
        })
      });

      if (response.ok) {
        setShowAddModal(false);
        setFormData({ name: '', domain: '', email: '', api_token: '' });
        fetchIntegrations();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to add integration'}`);
      }
    } catch (error) {
      console.error('Error adding integration:', error);
      alert('Failed to add integration');
    }
  };

  const handleTestConnection = async (integrationId: string) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/integrations/${integrationId}/test`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const data = await response.json();

      // Show result in modal
      setTroubleshootData({
        success: data.success,
        message: data.message || (data.success ? 'Connection successful!' : 'Connection failed'),
        troubleshooting: data.details?.troubleshooting
      });
      setShowTroubleshootModal(true);

      // Refresh integrations list if successful
      if (data.success) {
        fetchIntegrations();
      }
    } catch (error) {
      console.error('Error testing connection:', error);
      setTroubleshootData({
        success: false,
        message: 'Failed to test connection. Please try again.',
        troubleshooting: ['Network error or server is unreachable', 'Please check your internet connection']
      });
      setShowTroubleshootModal(true);
    }
  };

  const handleDeleteIntegration = async (integrationId: string) => {
    if (!confirm('Are you sure you want to delete this integration?')) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/integrations/${integrationId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      // Remove from UI even if backend returns 404 (already deleted)
      if (response.ok || response.status === 404) {
        fetchIntegrations();
      } else {
        throw new Error('Failed to delete integration');
      }
    } catch (error) {
      console.error('Error deleting integration:', error);
      // Still refresh to clean up UI
      fetchIntegrations();
    }
  };

  const toggleTheme = () => {
    const newTheme = !isDarkMode;
    setIsDarkMode(newTheme);
    localStorage.setItem('theme', newTheme ? 'dark' : 'light');
  };

  const handleNavigation = (navItem: NavigationItem) => {
    setActiveNav(navItem.name);
    if (navItem.href) {
      router.push(navItem.href);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/login');
  };

  const navigationItems = useMemo(() => NAV_ITEMS, []);

  const userInitial = useMemo(() => {
    if (!user) return '?';
    const name = user.companyName || user.fullName || user.name || user.email;
    return name.charAt(0).toUpperCase();
  }, [user]);

  return (
    <div className={`min-h-screen ${isDarkMode ? 'bg-gray-900' : 'bg-neutral-light'}`}>
      {/* Sidebar */}
      <aside
        onMouseEnter={() => setIsSidebarCollapsed(false)}
        onMouseLeave={() => setIsSidebarCollapsed(true)}
        className={`fixed left-0 top-0 h-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} border-r ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} transition-all duration-300 z-40 ${isSidebarCollapsed ? 'w-20' : 'w-64'} ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className={`flex items-center ${isSidebarCollapsed ? 'justify-center' : 'justify-start gap-3'} ${isSidebarCollapsed ? 'px-4' : 'px-6'} py-4 border-b ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'}`}>
            <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center flex-shrink-0">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            {!isSidebarCollapsed && (
              <span className={`font-bold text-lg ${isDarkMode ? 'text-white' : 'text-neutral-dark'} whitespace-nowrap`}>Convis AI</span>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {navigationItems.map((item) => {
              const hasSubItems = item.subItems && item.subItems.length > 0;
              const isCurrentPageInSubItems = hasSubItems && item.subItems?.some(sub => pathname === sub.href);
              const isDropdownOpen = openDropdown === item.name || isCurrentPageInSubItems;

              return (
                <div key={item.name}>
                  <button
                    onClick={() => {
                      if (hasSubItems) {
                        setOpenDropdown(isDropdownOpen ? null : item.name);
                      } else {
                        handleNavigation(item);
                      }
                    }}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                      activeNav === item.name
                        ? `${isDarkMode ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'} font-semibold`
                        : `${isDarkMode ? 'text-gray-400 hover:bg-gray-700 hover:text-white' : 'text-neutral-mid hover:bg-neutral-light hover:text-neutral-dark'}`
                    } ${isSidebarCollapsed ? 'justify-center' : ''}`}
                  >
                    <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      {item.icon}
                    </svg>
                    {!isSidebarCollapsed && (
                      <>
                        <span className="text-sm flex-1 text-left">{item.name}</span>
                        {hasSubItems && (
                          <svg
                            className={`w-4 h-4 transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        )}
                      </>
                    )}
                  </button>

                  {/* Dropdown sub-items */}
                  {hasSubItems && isDropdownOpen && !isSidebarCollapsed && (
                    <div className="ml-4 mt-1 space-y-1">
                      {item.subItems?.map((subItem) => {
                        const isActive = pathname === subItem.href;
                        return (
                          <button
                            key={subItem.name}
                            onClick={() => router.push(subItem.href)}
                            className={`w-full flex items-center gap-3 px-4 py-2 rounded-lg transition-all duration-200 ${
                              isActive
                                ? `${isDarkMode ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'} font-semibold`
                                : `${isDarkMode ? 'text-gray-400 hover:bg-gray-700 hover:text-white' : 'text-neutral-mid hover:bg-neutral-light/50 hover:text-neutral-dark'}`
                            }`}
                          >
                            <div className={`flex-shrink-0 ${isActive ? 'text-primary' : isDarkMode ? 'text-gray-500' : 'text-neutral-mid'}`}>
                              {subItem.logo || (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  {subItem.icon}
                                </svg>
                              )}
                            </div>
                            <span className="text-sm">{subItem.name}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </div>
      </aside>

      {/* Main Content */}
      <div className={`transition-all duration-300 ${isSidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'}`}>
        <TopBar
          isDarkMode={isDarkMode}
          toggleTheme={toggleTheme}
          onToggleMobileMenu={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          userInitial={userInitial}
          onLogout={handleLogout}
          token={token || undefined}
        />

        <main className="p-6">
          {/* Header */}
          <div className="mb-8">
            <h1 className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'} mb-2`}>
              Jira Integration
            </h1>
            <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
              Connect your Jira account to automatically create tickets from call logs and sync project data.
            </p>
          </div>

          {/* Add Integration Button */}
          <div className="mb-6">
            <button
              onClick={() => setShowAddModal(true)}
              className="px-6 py-3 bg-primary text-white rounded-xl hover:bg-primary/90 transition-colors flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Jira Account
            </button>
          </div>

          {/* Integrations List */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
            </div>
          ) : integrations.length === 0 ? (
            <div className={`text-center py-12 ${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl border ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'}`}>
              <svg className="w-16 h-16 mx-auto mb-4 text-neutral-mid" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <h3 className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                No Jira integrations yet
              </h3>
              <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} mb-4`}>
                Add your first Jira account to get started
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {integrations.map((integration) => (
                <div
                  key={integration._id}
                  className={`p-6 ${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl border ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-blue-500 rounded-xl flex items-center justify-center">
                        <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.757a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0z"/>
                        </svg>
                      </div>
                      <div>
                        <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                          {integration.name}
                        </h3>
                        <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                          {integration.metadata?.base_url || 'N/A'} • {integration.metadata?.email || 'N/A'}
                        </p>
                        <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full mt-2 ${
                          integration.status === 'connected'
                            ? 'bg-green-500/10 text-green-500'
                            : 'bg-yellow-500/10 text-yellow-500'
                        }`}>
                          <span className={`w-2 h-2 rounded-full ${
                            integration.status === 'connected' ? 'bg-green-500' : 'bg-yellow-500'
                          }`}></span>
                          {integration.status}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleTestConnection(integration._id)}
                        className={`px-4 py-2 rounded-lg border transition-colors ${
                          isDarkMode
                            ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                            : 'border-neutral-mid/20 text-neutral-dark hover:bg-neutral-light'
                        }`}
                      >
                        Test Connection
                      </button>
                      <button
                        onClick={() => handleDeleteIntegration(integration._id)}
                        className="px-4 py-2 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors"
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

      {/* Add Integration Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className={`max-w-md w-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl p-6`}>
            <h2 className={`text-2xl font-bold mb-4 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
              Add Jira Integration
            </h2>
            <form onSubmit={handleAddIntegration} className="space-y-4">
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                  Integration Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white'
                      : 'bg-white border-neutral-mid/20 text-neutral-dark'
                  }`}
                  placeholder="My Jira Workspace"
                  required
                />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                  Jira Domain
                </label>
                <input
                  type="text"
                  value={formData.domain}
                  onChange={(e) => setFormData({ ...formData, domain: e.target.value })}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white'
                      : 'bg-white border-neutral-mid/20 text-neutral-dark'
                  }`}
                  placeholder="yourcompany.atlassian.net"
                  required
                />
                <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                  Enter just the domain (e.g., yourcompany.atlassian.net). Do not include /jira/software/... paths.
                </p>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                  Email
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white'
                      : 'bg-white border-neutral-mid/20 text-neutral-dark'
                  }`}
                  placeholder="your@email.com"
                  required
                />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                  API Token
                </label>
                <input
                  type="password"
                  value={formData.api_token}
                  onChange={(e) => setFormData({ ...formData, api_token: e.target.value })}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDarkMode
                      ? 'bg-gray-700 border-gray-600 text-white'
                      : 'bg-white border-neutral-mid/20 text-neutral-dark'
                  }`}
                  placeholder="Your Jira API token"
                  required
                />
                <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                  <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                    Generate API token
                  </a>
                </p>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddModal(false);
                    setFormData({ name: '', domain: '', email: '', api_token: '' });
                  }}
                  className={`flex-1 px-4 py-2 rounded-lg border transition-colors ${
                    isDarkMode
                      ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                      : 'border-neutral-mid/20 text-neutral-dark hover:bg-neutral-light'
                  }`}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors"
                >
                  Add Integration
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Troubleshooting Modal */}
      {showTroubleshootModal && troubleshootData && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className={`max-w-lg w-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl p-6`}>
            <div className="flex items-start gap-4 mb-4">
              {troubleshootData.success ? (
                <div className="w-12 h-12 bg-green-500/10 rounded-full flex items-center justify-center flex-shrink-0">
                  <svg className="w-6 h-6 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              ) : (
                <div className="w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center flex-shrink-0">
                  <svg className="w-6 h-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </div>
              )}
              <div className="flex-1">
                <h2 className={`text-xl font-bold mb-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                  {troubleshootData.success ? 'Connection Successful!' : 'Connection Failed'}
                </h2>
                <p className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-mid'} mb-4`}>
                  {troubleshootData.message}
                </p>
              </div>
            </div>

            {troubleshootData.troubleshooting && troubleshootData.troubleshooting.length > 0 && (
              <div className={`mt-4 p-4 rounded-lg ${isDarkMode ? 'bg-gray-700' : 'bg-gray-50'}`}>
                <h3 className={`text-sm font-semibold mb-3 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                  Troubleshooting Steps:
                </h3>
                <ul className={`space-y-2 text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-mid'}`}>
                  {troubleshootData.troubleshooting.map((step, index) => (
                    <li key={index} className="flex items-start gap-2">
                      {step.match(/^\d+\./) ? (
                        <span className="text-primary font-medium">{step.split('.')[0]}.</span>
                      ) : (
                        <span className="text-primary">•</span>
                      )}
                      <span className="flex-1">{step.replace(/^\d+\.\s*/, '')}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!troubleshootData.success && (
              <div className={`mt-4 p-3 rounded-lg border ${isDarkMode ? 'bg-blue-500/10 border-blue-500/20' : 'bg-blue-50 border-blue-200'}`}>
                <p className={`text-sm ${isDarkMode ? 'text-blue-300' : 'text-blue-700'}`}>
                  💡 <strong>Tip:</strong> Most connection issues are resolved by regenerating your Jira API token at{' '}
                  <a
                    href="https://id.atlassian.com/manage-profile/security/api-tokens"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline hover:no-underline"
                  >
                    Atlassian Security Settings
                  </a>
                </p>
              </div>
            )}

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  setShowTroubleshootModal(false);
                  setTroubleshootData(null);
                }}
                className={`flex-1 px-4 py-2 rounded-lg border transition-colors ${
                  isDarkMode
                    ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                    : 'border-neutral-mid/20 text-neutral-dark hover:bg-neutral-light'
                }`}
              >
                Close
              </button>
              {!troubleshootData.success && (
                <a
                  href="https://id.atlassian.com/manage-profile/security/api-tokens"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors text-center"
                >
                  Get New API Token
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
