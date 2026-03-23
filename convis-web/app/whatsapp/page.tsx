'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import { NAV_ITEMS, NavigationItem } from '../components/Navigation';
import { TopBar } from '../components/TopBar';
import AddCredentialModal from './components/AddCredentialModal';
import SendMessageModal from './components/SendMessageModal';
import MessageHistoryModal from './components/MessageHistoryModal';
import {
  getWhatsAppCredentials,
  deleteWhatsAppCredential,
  verifyWhatsAppCredential,
  getWhatsAppStats
} from '@/lib/whatsapp-api';

type StoredUser = {
  id?: string;
  _id?: string;
  clientId?: string;
  name?: string;
  fullName?: string;
  firstName?: string;
  lastName?: string;
  username?: string;
  email?: string;
  [key: string]: unknown;
};

interface WhatsAppCredential {
  id: string;
  label: string;
  last_four: string;
  api_url_masked: string;
  status: 'active' | 'disconnected' | 'error';
  created_at: string;
}

interface WhatsAppStats {
  total_messages: number;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  credentials_count: number;
  active_credentials: number;
}

export default function WhatsAppPage() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [activeNav, setActiveNav] = useState('WhatsApp');
  const [activeTab, setActiveTab] = useState<'credentials' | 'messages' | 'analytics'>('credentials');
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const [credentials, setCredentials] = useState<WhatsAppCredential[]>([]);
  const [stats, setStats] = useState<WhatsAppStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isSendModalOpen, setIsSendModalOpen] = useState(false);
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const [selectedCredential, setSelectedCredential] = useState<string | null>(null);

  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');

    if (!storedToken) {
      router.push('/login');
      return;
    }

    setToken(storedToken);

    if (userStr) {
      const parsedUser: StoredUser = JSON.parse(userStr);
      setUser(parsedUser);
    }

    const savedTheme = localStorage.getItem('theme');
    setIsDarkMode(savedTheme === 'dark');

    fetchCredentials();
    fetchStats();
  }, [router]);

  const fetchCredentials = async () => {
    try {
      setLoading(true);
      const data = await getWhatsAppCredentials();
      setCredentials(data);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load WhatsApp credentials');
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const data = await getWhatsAppStats();
      setStats(data);
    } catch (err: any) {
      console.error('Failed to load stats:', err);
    }
  };

  const handleAddCredential = () => {
    setIsAddModalOpen(true);
  };

  const handleCredentialAdded = () => {
    fetchCredentials();
    fetchStats();
  };

  const handleVerifyCredential = async (credentialId: string) => {
    setVerifyingId(credentialId);
    try {
      const result = await verifyWhatsAppCredential(credentialId);

      if (result.success) {
        alert(`✅ ${result.message}\n\nTemplates Found: ${result.templates_count || 0}`);
        fetchCredentials(); // Refresh to show updated status
      } else {
        alert(`❌ ${result.message}`);
      }
    } catch (err: any) {
      alert(`Failed to verify: ${err.message}`);
    } finally {
      setVerifyingId(null);
    }
  };

  const handleDeleteCredential = async (credentialId: string, label: string) => {
    if (!confirm(`Are you sure you want to delete "${label}"?`)) {
      return;
    }

    setDeletingId(credentialId);
    try {
      await deleteWhatsAppCredential(credentialId);
      fetchCredentials();
      fetchStats();
    } catch (err: any) {
      alert(`Failed to delete: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleSendMessage = (credentialId: string) => {
    setSelectedCredential(credentialId);
    setIsSendModalOpen(true);
  };

  const handleViewHistory = (credentialId: string) => {
    setSelectedCredential(credentialId);
    setIsHistoryModalOpen(true);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return isDarkMode ? 'text-green-400 bg-green-900/30' : 'text-green-600 bg-green-100';
      case 'disconnected':
        return isDarkMode ? 'text-gray-400 bg-gray-700/30' : 'text-gray-600 bg-gray-100';
      case 'error':
        return isDarkMode ? 'text-red-400 bg-red-900/30' : 'text-red-600 bg-red-100';
      default:
        return isDarkMode ? 'text-gray-400 bg-gray-700/30' : 'text-gray-600 bg-gray-100';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return '✓';
      case 'error':
        return '✕';
      default:
        return '⋯';
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('clientId');
    localStorage.removeItem('isAdmin');
    router.push('/login');
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

  const navigationItems = useMemo(() => NAV_ITEMS, []);

  const userInitial = useMemo(() => {
    const possible = user?.fullName || user?.name || user?.username || user?.email;
    if (!possible || typeof possible !== 'string' || possible.length === 0) {
      return 'U';
    }
    return possible.trim().charAt(0).toUpperCase();
  }, [user]);

  const userGreeting = useMemo(() => {
    const candidates = [
      user?.firstName && user?.firstName,
      user?.fullName,
      user?.name,
      user?.username,
      user?.email,
    ].filter((value) => typeof value === 'string' && value.trim().length > 0) as string[];
    if (candidates.length === 0) return undefined;
    const primary = candidates[0];
    if (primary.includes('@')) {
      return primary.split('@')[0];
    }
    return primary.split(' ')[0];
  }, [user]);

  if (!user) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${isDarkMode ? 'bg-gray-900' : 'bg-neutral-light'}`}>
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${isDarkMode ? 'dark bg-gray-900' : 'bg-neutral-light'}`}>
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
              <DotLottieReact
                src="/microphone-animation.lottie"
                loop
                autoplay
                style={{ width: '24px', height: '24px' }}
              />
            </div>
            {!isSidebarCollapsed && (
              <span className={`font-bold text-lg ${isDarkMode ? 'text-white' : 'text-neutral-dark'} whitespace-nowrap`}>Convis AI</span>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {navigationItems.map((item) => {
              const hasSubItems = item.subItems && item.subItems.length > 0;
              const isCurrentPageInSubItems = hasSubItems && item.subItems?.some(sub => window.location.pathname === sub.href);
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
                      {item.subItems?.map((subItem) => (
                        <button
                          key={subItem.name}
                          onClick={() => router.push(subItem.href)}
                          className={`w-full flex items-center gap-3 px-4 py-2 rounded-lg transition-all duration-200 ${
                            isDarkMode
                              ? 'text-gray-400 hover:bg-gray-700 hover:text-white'
                              : 'text-neutral-mid hover:bg-neutral-light/50 hover:text-neutral-dark'
                          }`}
                        >
                          <div className={`flex-shrink-0 ${isDarkMode ? 'text-gray-500' : 'text-neutral-mid'}`}>
                            {subItem.logo || (
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                {subItem.icon}
                              </svg>
                            )}
                          </div>
                          <span className="text-sm">{subItem.name}</span>
                        </button>
                      ))}
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
          onLogout={handleLogout}
          userInitial={userInitial}
          userLabel={userGreeting}
          onToggleMobileMenu={() => setIsMobileMenuOpen((prev) => !prev)}
          token={token || undefined}
        />

        <main className="px-4 py-6 sm:px-6 lg:px-8">
          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <div className={`${isDarkMode ? 'bg-gray-800/90 border-gray-700' : 'bg-white border-neutral-mid/10'} rounded-2xl p-6 shadow-sm border`}>
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl ${isDarkMode ? 'bg-green-900/30' : 'bg-green-100'} flex items-center justify-center`}>
                    <svg className={`w-6 h-6 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>Total Messages</p>
                    <p className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>{stats.total_messages}</p>
                  </div>
                </div>
              </div>

              <div className={`${isDarkMode ? 'bg-gray-800/90 border-gray-700' : 'bg-white border-neutral-mid/10'} rounded-2xl p-6 shadow-sm border`}>
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl ${isDarkMode ? 'bg-blue-900/30' : 'bg-blue-100'} flex items-center justify-center`}>
                    <svg className={`w-6 h-6 ${isDarkMode ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>Delivered</p>
                    <p className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>{stats.delivered}</p>
                  </div>
                </div>
              </div>

              <div className={`${isDarkMode ? 'bg-gray-800/90 border-gray-700' : 'bg-white border-neutral-mid/10'} rounded-2xl p-6 shadow-sm border`}>
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl ${isDarkMode ? 'bg-purple-900/30' : 'bg-purple-100'} flex items-center justify-center`}>
                    <svg className={`w-6 h-6 ${isDarkMode ? 'text-purple-400' : 'text-purple-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </div>
                  <div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>Read</p>
                    <p className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>{stats.read}</p>
                  </div>
                </div>
              </div>

              <div className={`${isDarkMode ? 'bg-gray-800/90 border-gray-700' : 'bg-white border-neutral-mid/10'} rounded-2xl p-6 shadow-sm border`}>
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl ${isDarkMode ? 'bg-orange-900/30' : 'bg-orange-100'} flex items-center justify-center`}>
                    <svg className={`w-6 h-6 ${isDarkMode ? 'text-orange-400' : 'text-orange-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                  </div>
                  <div>
                    <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>Active Accounts</p>
                    <p className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>{stats.active_credentials}/{stats.credentials_count}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tabs */}
          <div className={`${isDarkMode ? 'bg-gray-800/90 border-gray-700' : 'bg-white border-neutral-mid/10'} rounded-2xl shadow-sm border mb-6`}>
            <div className={`border-b ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'}`}>
              <div className="flex gap-4 px-6">
                <button
                  onClick={() => setActiveTab('credentials')}
                  className={`py-4 px-2 font-medium border-b-2 transition-colors ${
                    activeTab === 'credentials'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-neutral-mid hover:text-neutral-dark'
                  }`}
                >
                  Credentials
                </button>
                <button
                  onClick={() => setActiveTab('messages')}
                  className={`py-4 px-2 font-medium border-b-2 transition-colors ${
                    activeTab === 'messages'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-neutral-mid hover:text-neutral-dark'
                  }`}
                >
                  Messages
                </button>
                <button
                  onClick={() => setActiveTab('analytics')}
                  className={`py-4 px-2 font-medium border-b-2 transition-colors ${
                    activeTab === 'analytics'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-neutral-mid hover:text-neutral-dark'
                  }`}
                >
                  Analytics
                </button>
              </div>
            </div>

            <div className="p-6">
              {/* Credentials Tab */}
              {activeTab === 'credentials' && (
                <div>
                  <div className="flex justify-between items-center mb-6">
                    <div>
                      <h2 className={`text-xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>WhatsApp Business Accounts</h2>
                      <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                        Connect your WhatsApp Business accounts to send messages
                      </p>
                    </div>
                    <button
                      onClick={handleAddCredential}
                      className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-green-500 to-green-600 text-white font-semibold shadow-lg hover:shadow-xl transition-all duration-200 flex items-center gap-2"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      Add Account
                    </button>
                  </div>

                  {loading ? (
                    <div className="text-center py-12">
                      <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent"></div>
                      <p className={`mt-4 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>Loading credentials...</p>
                    </div>
                  ) : error ? (
                    <div className="text-center py-12">
                      <p className="text-red-600">{error}</p>
                    </div>
                  ) : credentials.length === 0 ? (
                    <div className="text-center py-12">
                      <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 ${isDarkMode ? 'bg-green-900/30' : 'bg-green-100'}`}>
                        <svg className={`w-10 h-10 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                      </div>
                      <h3 className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>No WhatsApp accounts connected</h3>
                      <p className={`mb-6 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                        Add your first WhatsApp Business account to start sending messages
                      </p>
                      <button
                        onClick={handleAddCredential}
                        className="px-6 py-3 rounded-xl bg-gradient-to-r from-green-500 to-green-600 text-white font-semibold shadow-lg hover:shadow-xl transition-all duration-200"
                      >
                        Add Your First Account
                      </button>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {credentials.map((credential) => (
                        <div
                          key={credential.id}
                          className={`${isDarkMode ? 'bg-gray-700/50 border-gray-600' : 'bg-gradient-to-br from-white to-green-50/30 border-neutral-mid/20'} border rounded-2xl p-6 hover:shadow-lg transition-all duration-200`}
                        >
                          <div className="flex justify-between items-start mb-4">
                            <div>
                              <h3 className={`font-semibold text-lg ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>{credential.label}</h3>
                              <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>{credential.api_url_masked}</p>
                            </div>
                            <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(credential.status)}`}>
                              {getStatusIcon(credential.status)} {credential.status}
                            </span>
                          </div>

                          <div className={`text-xs mb-4 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                            API Key: ••••{credential.last_four}
                          </div>

                          <div className="flex gap-2">
                            <button
                              onClick={() => handleSendMessage(credential.id)}
                              disabled={credential.status !== 'active'}
                              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${isDarkMode ? 'bg-green-900/40 text-green-300 hover:bg-green-900/60' : 'bg-green-100 text-green-700 hover:bg-green-200'}`}
                            >
                              Send
                            </button>
                            <button
                              onClick={() => handleViewHistory(credential.id)}
                              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${isDarkMode ? 'bg-blue-900/40 text-blue-300 hover:bg-blue-900/60' : 'bg-blue-100 text-blue-700 hover:bg-blue-200'}`}
                            >
                              History
                            </button>
                            <button
                              onClick={() => handleVerifyCredential(credential.id)}
                              disabled={verifyingId === credential.id}
                              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${isDarkMode ? 'bg-purple-900/40 text-purple-300 hover:bg-purple-900/60' : 'bg-purple-100 text-purple-700 hover:bg-purple-200'}`}
                              title="Verify connection"
                            >
                              {verifyingId === credential.id ? '...' : '✓'}
                            </button>
                            <button
                              onClick={() => handleDeleteCredential(credential.id, credential.label)}
                              disabled={deletingId === credential.id}
                              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${isDarkMode ? 'bg-red-900/40 text-red-300 hover:bg-red-900/60' : 'bg-red-100 text-red-700 hover:bg-red-200'}`}
                              title="Delete"
                            >
                              {deletingId === credential.id ? '...' : '✕'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Messages Tab */}
              {activeTab === 'messages' && (
                <div className="text-center py-12">
                  <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 ${isDarkMode ? 'bg-blue-900/30' : 'bg-blue-100'}`}>
                    <svg className={`w-10 h-10 ${isDarkMode ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </div>
                  <h3 className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>Message Center</h3>
                  <p className={`mb-6 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    Select a credential from the Credentials tab to send messages
                  </p>
                  {credentials.length > 0 && (
                    <button
                      onClick={() => setActiveTab('credentials')}
                      className="px-6 py-3 rounded-xl bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold shadow-lg hover:shadow-xl transition-all duration-200"
                    >
                      Go to Credentials
                    </button>
                  )}
                </div>
              )}

              {/* Analytics Tab */}
              {activeTab === 'analytics' && (
                <div className="text-center py-12">
                  <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 ${isDarkMode ? 'bg-purple-900/30' : 'bg-purple-100'}`}>
                    <svg className={`w-10 h-10 ${isDarkMode ? 'text-purple-400' : 'text-purple-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </div>
                  <h3 className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>Advanced Analytics</h3>
                  <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    Detailed analytics and insights coming soon
                  </p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>

      {/* Modals */}
      {isAddModalOpen && (
        <AddCredentialModal
          onClose={() => setIsAddModalOpen(false)}
          onSuccess={handleCredentialAdded}
        />
      )}

      {isSendModalOpen && selectedCredential && (
        <SendMessageModal
          credentialId={selectedCredential}
          onClose={() => {
            setIsSendModalOpen(false);
            setSelectedCredential(null);
          }}
          onSuccess={fetchStats}
        />
      )}

      {isHistoryModalOpen && selectedCredential && (
        <MessageHistoryModal
          credentialId={selectedCredential}
          onClose={() => {
            setIsHistoryModalOpen(false);
            setSelectedCredential(null);
          }}
        />
      )}

      {/* Mobile Menu Overlay */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        ></div>
      )}
    </div>
  );
}
