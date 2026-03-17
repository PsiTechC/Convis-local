'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import CreateCampaignModal from './create-campaign-modal';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import { NAV_ITEMS, NavigationItem } from '../components/Navigation';
import { TopBar } from '../components/TopBar';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

interface Campaign {
  id: string;
  _id?: string;
  name: string;
  country: string;
  status: string;
  caller_id: string;
  created_at: string;
  calendar_enabled?: boolean;
  system_prompt_override?: string | null;
  database_config?: {
    enabled: boolean;
    type: string;
  } | null;
  stats?: {
    total_leads: number;
    completed: number;
    queued: number;
    calling: number;
  };
}

type StoredUser = {
  id?: string;
  _id?: string;
  clientId?: string;
  [key: string]: unknown;
};

export default function CampaignsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [activeNav, setActiveNav] = useState('Campaigns');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const displayName = useMemo(() => {
    if (!user) return '';
    const possible = [
      user.name,
      user.fullName,
      user.firstName && user.lastName ? `${user.firstName} ${user.lastName}` : undefined,
      user.firstName,
      user.username,
      user.email,
    ].find((value) => typeof value === 'string' && value.trim().length > 0);
    return possible ? String(possible).trim() : '';
  }, [user]);

  const userInitial = useMemo(() => {
    if (!displayName) return 'U';
    return displayName.charAt(0).toUpperCase();
  }, [displayName]);

  const userGreeting = useMemo(() => {
    if (!displayName) return undefined;
    if (displayName.includes('@')) {
      return displayName.split('@')[0];
    }
    return displayName.split(' ')[0];
  }, [displayName]);

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');
    const savedTheme = localStorage.getItem('theme');

    if (!storedToken) {
      router.push('/login');
      return;
    }

    setToken(storedToken);

    if (savedTheme === 'dark') {
      setIsDarkMode(true);
    }

    if (userStr) {
      const parsedUser = JSON.parse(userStr);
      setUser(parsedUser);
      fetchCampaigns(parsedUser.id || parsedUser._id || parsedUser.clientId);
    }
  }, [router]);

  const fetchCampaigns = async (userId: string) => {
    try {
      setIsLoading(true);
      const response = await fetch(`${API_URL}/api/campaigns/user/${userId}`);
      if (response.ok) {
        const data = await response.json();
        setCampaigns(data.campaigns || []);
      } else {
        console.error('Failed to fetch campaigns');
      }
    } catch (error) {
      console.error('Error fetching campaigns:', error);
    } finally {
      setIsLoading(false);
    }
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

  const toggleTheme = () => {
    const newTheme = !isDarkMode;
    setIsDarkMode(newTheme);
    localStorage.setItem('theme', newTheme ? 'dark' : 'light');
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      case 'paused':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
      case 'completed':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
      case 'stopped':
        return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
    }
  };

  const getStatusLabel = (status: string) => (status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown');

  const getCampaignSummary = (campaign: Campaign) => {
    const summary = (campaign.system_prompt_override || '').trim();
    if (summary.length > 0) {
      return summary.length > 140 ? `${summary.slice(0, 137)}...` : summary;
    }
    return 'No campaign-specific instructions provided yet. Configure a prompt to guide the assistant during calls.';
  };

  const handleViewDetails = (campaignId: string) => {
    router.push(`/campaigns/${campaignId}`);
  };

  const handleManageLeads = (campaignId: string) => {
    router.push(`/campaigns/${campaignId}/leads`);
  };

  const handleExport = async (campaignId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/campaigns/${campaignId}/export`);
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `campaign_${campaignId}_report.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        alert('Failed to export campaign data');
      }
    } catch (error) {
      console.error('Error exporting campaign:', error);
      alert('Error exporting campaign data');
    }
  };

  const handleDeleteCampaign = async (campaignId: string, campaignName: string) => {
    if (!confirm(`Are you sure you want to delete campaign "${campaignName}"? This action cannot be undone.`)) {
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/campaigns/${campaignId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        alert('Campaign deleted successfully');
        // Refresh campaigns list
        const userId = user?.id || user?._id || user?.clientId;
        if (userId) {
          fetchCampaigns(userId);
        }
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to delete campaign');
      }
    } catch (error) {
      console.error('Error deleting campaign:', error);
      alert('Error deleting campaign');
    }
  };

  const navigationItems = useMemo(() => NAV_ITEMS, []);


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
                      activeNav === item.name || isCurrentPageInSubItems
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

                  {/* Dropdown Items */}
                  {hasSubItems && isDropdownOpen && !isSidebarCollapsed && (
                    <div className="ml-4 mt-1 space-y-1">
                      {item.subItems?.map((subItem) => (
                        <button
                          key={subItem.name}
                          onClick={() => router.push(subItem.href)}
                          className={`w-full flex items-center gap-3 px-4 py-2 rounded-lg transition-all duration-200 ${
                            pathname === subItem.href
                              ? `${isDarkMode ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'} font-semibold`
                              : `${isDarkMode ? 'text-gray-400 hover:bg-gray-700 hover:text-white' : 'text-neutral-mid hover:bg-neutral-light hover:text-neutral-dark'}`
                          }`}
                        >
                          {subItem.logo && (
                            <div className="w-5 h-5 flex-shrink-0">
                              {subItem.logo}
                            </div>
                          )}
                          {!subItem.logo && (
                            <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              {subItem.icon}
                            </svg>
                          )}
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
      <div className={`${isSidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'} transition-all duration-300`}>
        <TopBar
          isDarkMode={isDarkMode}
          toggleTheme={toggleTheme}
          onLogout={handleLogout}
          userInitial={userInitial}
          userLabel={userGreeting}
          onToggleMobileMenu={() => setIsMobileMenuOpen((prev) => !prev)}
          collapseSearchOnMobile
          token={token || undefined}
        />

        <main className="p-6 space-y-6">
          <div>
            <h1 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-dark'}`}>Campaigns</h1>
            <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} mt-1`}>Manage your outbound calling campaigns</p>
          </div>
          <div className="mb-6 flex justify-end items-center">
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-6 py-3 bg-primary text-white rounded-xl hover:bg-primary/90 transition-colors font-medium flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create Campaign
            </button>
          </div>

          {/* Campaigns List */}
          {isLoading ? (
            <div className="flex justify-center items-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            </div>
          ) : campaigns.length === 0 ? (
            <div className={`${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-2xl p-12 text-center`}>
              <svg className={`w-16 h-16 mx-auto mb-4 ${isDarkMode ? 'text-gray-600' : 'text-neutral-mid/40'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
              </svg>
              <h3 className={`text-xl font-bold mb-2 ${isDarkMode ? 'text-white' : 'text-dark'}`}>No Campaigns Yet</h3>
              <p className={`${isDarkMode ? 'text-gray-400' : 'text-dark/60'} mb-6`}>
                Get started by creating your first calling campaign
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="px-6 py-3 bg-primary text-white rounded-xl hover:bg-primary/90 transition-colors font-medium"
              >
                Create Your First Campaign
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
              {campaigns.map((campaign, idx) => {
                const campaignId = campaign.id || campaign._id || `${campaign.caller_id}-${idx}`;
                const summary = getCampaignSummary(campaign);
                const stats = campaign.stats;
                const hasCalendar = Boolean(campaign.calendar_enabled);
                return (
                  <div
                    key={campaignId}
                    className={`${isDarkMode ? 'bg-gray-800/90 border-gray-700' : 'bg-white border-neutral-mid/10'} rounded-2xl border shadow-sm hover:shadow-md transition-shadow flex flex-col`}
                  >
                    <div className="flex items-start justify-between gap-3 p-6 pb-4">
                      <div className="flex items-center gap-3">
                        <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${isDarkMode ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'}`}>
                          <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M5 8l7-5 7 5v9a4 4 0 01-4 4h-6a4 4 0 01-4-4z" />
                          </svg>
                        </div>
                        <div>
                          <p className={`text-sm font-semibold uppercase tracking-wide ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                            {campaign.country}
                          </p>
                          <h3 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-dark'}`}>
                            {campaign.name}
                          </h3>
                          <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-dark/70'}`}>
                            Caller ID: {campaign.caller_id || 'Not Assigned'}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2 text-right">
                        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getStatusColor(campaign.status)}`}>
                          {getStatusLabel(campaign.status)}
                        </span>
                        {hasCalendar && (
                          <span className={`text-xs font-medium ${isDarkMode ? 'text-green-300' : 'text-green-600'}`}>
                            Calendar Enabled
                          </span>
                        )}
                      </div>
                    </div>

                    <div className={`px-6 pb-4 text-sm ${isDarkMode ? 'text-gray-300' : 'text-dark/70'}`}>
                      {summary}
                    </div>

                    <div className={`px-6 pb-4 ${isDarkMode ? 'text-gray-200' : 'text-dark'}`}>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className={`${isDarkMode ? 'text-gray-500' : 'text-neutral-mid'}`}>Total Leads</p>
                          <p className="text-lg font-semibold">{stats ? stats.total_leads : '—'}</p>
                        </div>
                        <div>
                          <p className={`${isDarkMode ? 'text-gray-500' : 'text-neutral-mid'}`}>Completed</p>
                          <p className="text-lg font-semibold text-green-500">{stats ? stats.completed : '—'}</p>
                        </div>
                        <div>
                          <p className={`${isDarkMode ? 'text-gray-500' : 'text-neutral-mid'}`}>Queued</p>
                          <p className="text-lg font-semibold text-blue-500">{stats ? stats.queued : '—'}</p>
                        </div>
                        <div>
                          <p className={`${isDarkMode ? 'text-gray-500' : 'text-neutral-mid'}`}>Calling</p>
                          <p className="text-lg font-semibold text-yellow-500">{stats ? stats.calling : '—'}</p>
                        </div>
                      </div>
                    </div>

                    <div className="mt-auto border-t border-dashed border-neutral-mid/20 px-6 py-4 dark:border-gray-700">
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => handleViewDetails(campaign.id || campaign._id || '')}
                          className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-700 text-white hover:bg-gray-600' : 'bg-neutral-light text-dark hover:bg-neutral-mid/30'} transition-colors text-sm font-medium`}
                        >
                          View Details
                        </button>
                        <button
                          onClick={() => handleManageLeads(campaign.id || campaign._id || '')}
                          className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-700 text-white hover:bg-gray-600' : 'bg-neutral-light text-dark hover:bg-neutral-mid/30'} transition-colors text-sm font-medium`}
                        >
                          Manage Leads
                        </button>
                        <button
                          onClick={() => handleExport(campaign.id || campaign._id || '')}
                          className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-700 text-white hover:bg-gray-600' : 'bg-neutral-light text-dark hover:bg-neutral-mid/30'} transition-colors text-sm font-medium`}
                        >
                          Export
                        </button>
                        <button
                          onClick={() => handleDeleteCampaign(campaign.id || campaign._id || '', campaign.name)}
                          className={`px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors text-sm font-medium flex items-center gap-2`}
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>

      {/* Mobile Menu Overlay */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        ></div>
      )}

      {/* Create Campaign Modal */}
      <CreateCampaignModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={() => {
          // Refresh campaigns list
          const userId = user?.id || user?._id || user?.clientId;
          if (userId) {
            fetchCampaigns(userId);
          }
        }}
        isDarkMode={isDarkMode}
        userId={user?.id || user?._id || user?.clientId || ''}
      />
    </div>
  );
}
