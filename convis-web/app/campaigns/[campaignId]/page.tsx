'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useParams, usePathname } from 'next/navigation';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import { NAV_ITEMS, NavigationItem } from '../../components/Navigation';
import { TopBar } from '../../components/TopBar';
import CreateCampaignModal from '../create-campaign-modal';
import LeadViewerModal from '../components/LeadViewerModal';
import BrowserCallModal from '../../components/BrowserCallModal';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

interface Campaign {
  id?: string;
  _id?: string;
  name: string;
  country: string;
  status: string;
  caller_id: string;
  working_window: {
    timezone: string;
    start: string;
    end: string;
    days: number[];
  };
  retry_policy: {
    max_attempts: number;
    retry_after_minutes: number[];
  };
  pacing: {
    calls_per_minute: number;
    max_concurrent: number;
  };
  assistant_id?: string | null;
  start_at?: string | null;
  stop_at?: string | null;
  calendar_enabled?: boolean;
  system_prompt_override?: string | null;
  database_config?: {
    enabled?: boolean;
    type?: string;
    host?: string;
    port?: string;
    database?: string;
    username?: string;
    table_name?: string;
    search_columns?: string[];
  } | null;
  created_at: string;
  updated_at: string;
}

interface CampaignStats {
  total_leads: number;
  queued: number;
  completed: number;
  failed: number;
  no_answer: number;
  busy: number;
  calling: number;
  avg_sentiment_score?: number | null;
  calendar_bookings: number;
  total_calls: number;
  avg_call_duration?: number | null;
}

interface Lead {
  id: string;
  _id?: string;
  first_name?: string | null;
  last_name?: string | null;
  name?: string | null;
  email?: string | null;
  e164?: string | null;
  raw_number?: string | null;
  batch_name?: string | null;
  status: string;
  last_outcome?: string | null;
  attempts: number;
  timezone?: string | null;
  custom_fields?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  order_index?: number | null;
}

interface AssistantSummary {
  id: string;
  name: string;
}

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

type VerifiedCallerId = string | {
  phone_number?: string | null;
  friendly_name?: string | null;
  [key: string]: unknown;
};


function formatDateTime(value?: string | null) {
  if (!value) return 'Not scheduled';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatMinutesList(values: number[]) {
  if (!values?.length) return '—';
  return values.join(', ');
}

function formatDuration(seconds?: number | null) {
  if (!seconds) return '—';
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

  const getLeadDisplayName = (lead: Lead) => {
    if (lead.first_name || lead.last_name) {
      const combined = `${lead.first_name ?? ''} ${lead.last_name ?? ''}`.trim();
      if (combined) {
        return combined;
      }
    }
    return lead.name || '—';
  };

export default function CampaignDetailPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams<{ campaignId: string }>();
  const campaignId = useMemo(() => {
    if (!params) return '';
    const value = params.campaignId;
    return Array.isArray(value) ? value[0] : value;
  }, [params]);

  const [user, setUser] = useState<StoredUser | null>(null);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [stats, setStats] = useState<CampaignStats | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const [activeNav, setActiveNav] = useState('Campaigns');
  const [isTestingCall, setIsTestingCall] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigationItems = useMemo(() => NAV_ITEMS, []);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isLeadViewerOpen, setIsLeadViewerOpen] = useState(false);
  const [assistantInfo, setAssistantInfo] = useState<AssistantSummary | null>(null);
  const [isCallModalOpen, setIsCallModalOpen] = useState(false);
  const [callToNumber, setCallToNumber] = useState('');
  const [isInitiatingCall, setIsInitiatingCall] = useState(false);
  const [verifiedCallerIds, setVerifiedCallerIds] = useState<VerifiedCallerId[]>([]);
  const [isLoadingCallerIds, setIsLoadingCallerIds] = useState(false);
  const [activeCallSid, setActiveCallSid] = useState<string | null>(null);
  const [activeCallStatus, setActiveCallStatus] = useState('');
  const [isCallActive, setIsCallActive] = useState(false);
  const [isBrowserCallOpen, setIsBrowserCallOpen] = useState(false);
  const [activeCalls, setActiveCalls] = useState<Lead[]>([]);
  const [isLoadingActiveCalls, setIsLoadingActiveCalls] = useState(false);
  const callStatusIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const nextQueuedLead = useMemo(() => {
    const queued = leads.filter((lead) => lead.status === 'queued');
    if (!queued.length) return null;
    const sorted = [...queued].sort((a, b) => {
      const orderA = a.order_index ?? Number.MAX_SAFE_INTEGER;
      const orderB = b.order_index ?? Number.MAX_SAFE_INTEGER;
      if (orderA !== orderB) return orderA - orderB;
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    });
    return sorted[0];
  }, [leads]);

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

  const userIdValue = useMemo(() => {
    return (user?.id || user?._id || user?.clientId || '') as string;
  }, [user]);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
      setIsDarkMode(true);
    }

    const token = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');

    if (!token || !userStr) {
      router.push('/login');
      return;
    }

    const parsedUser: StoredUser = JSON.parse(userStr);
    setUser(parsedUser);
  }, [router]);

  const resolvedCampaignId = useMemo(() => {
    return campaignId || '';
  }, [campaignId]);

  const fetchCampaign = useCallback(async () => {
    if (!resolvedCampaignId) return;
    try {
      setIsLoading(true);
      const response = await fetch(`${API_URL}/api/campaigns/${resolvedCampaignId}`);
      if (!response.ok) {
        throw new Error('Failed to fetch campaign');
      }
      const data = await response.json();
      setCampaign(data);
    } catch (err) {
      console.error('Error fetching campaign', err);
      setError('Unable to load campaign details.');
    } finally {
      setIsLoading(false);
    }
  }, [resolvedCampaignId]);

  const fetchStats = useCallback(async () => {
    if (!resolvedCampaignId) return;
    try {
      const response = await fetch(`${API_URL}/api/campaigns/${resolvedCampaignId}/stats`);
      if (!response.ok) {
        throw new Error('Failed to fetch stats');
      }
      const data = await response.json();
      setStats(data);
    } catch (err) {
      console.error('Error fetching stats', err);
    }
  }, [resolvedCampaignId]);

  const fetchLeads = useCallback(async () => {
    if (!resolvedCampaignId) return;
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/campaigns/${resolvedCampaignId}/leads?limit=20`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!response.ok) {
        throw new Error('Failed to fetch leads');
      }
      const data = await response.json();
      setLeads(data || []);
    } catch (err) {
      console.error('Error fetching leads', err);
    }
  }, [resolvedCampaignId]);

  const fetchActiveCalls = useCallback(async () => {
    if (!resolvedCampaignId) return;
    try {
      setIsLoadingActiveCalls(true);
      const response = await fetch(`${API_URL}/api/campaigns/${resolvedCampaignId}/active-call`);
      if (response.ok) {
        const data = await response.json();
        const list = Array.isArray(data?.active_calls) ? data.active_calls : [];
        setActiveCalls(list);
      } else {
        setActiveCalls([]);
      }
    } catch (err) {
      console.error('Error fetching active call info', err);
      setActiveCalls([]);
    } finally {
      setIsLoadingActiveCalls(false);
    }
  }, [resolvedCampaignId]);

  useEffect(() => {
    if (!resolvedCampaignId) return;
    fetchCampaign();
    fetchStats();
    fetchLeads();
    fetchActiveCalls();
  }, [resolvedCampaignId, fetchCampaign, fetchStats, fetchLeads, fetchActiveCalls]);

  useEffect(() => {
    if (!resolvedCampaignId) return;
    setIsLoadingActiveCalls(true);
    fetchActiveCalls();
    const interval = setInterval(fetchActiveCalls, 1000);
    return () => clearInterval(interval);
  }, [resolvedCampaignId, fetchActiveCalls]);

  // ULTRA-FAST MODE: Poll leads every 1 second for instant status updates
  useEffect(() => {
    if (!resolvedCampaignId) return;
    const leadsInterval = setInterval(() => {
      fetchLeads();
      fetchStats();
    }, 1000);
    return () => clearInterval(leadsInterval);
  }, [resolvedCampaignId, fetchLeads, fetchStats]);

  useEffect(() => {
    const loadAssistantInfo = async () => {
      if (!campaign?.assistant_id) {
        setAssistantInfo(null);
        return;
      }
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_URL}/api/ai-assistants/${campaign.assistant_id}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!response.ok) {
          setAssistantInfo(null);
          return;
        }
        const data = await response.json();
        const assistantId = data.id || data._id || campaign.assistant_id;
        setAssistantInfo({
          id: assistantId,
          name: data.name || 'Unnamed Assistant',
        });
      } catch (assistantError) {
        console.error('Failed to load assistant info', assistantError);
        setAssistantInfo(null);
      }
    };

    loadAssistantInfo();
  }, [campaign?.assistant_id]);

  useEffect(() => {
    return () => {
      if (callStatusIntervalRef.current) {
        clearInterval(callStatusIntervalRef.current);
        callStatusIntervalRef.current = null;
      }
    };
  }, []);

  const handleNavigation = (navItem: NavigationItem) => {
    setActiveNav(navItem.name);
    if (navItem.href) {
      router.push(navItem.href);
    }
  };

  const toggleTheme = () => {
    const newTheme = !isDarkMode;
    setIsDarkMode(newTheme);
    localStorage.setItem('theme', newTheme ? 'dark' : 'light');
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/login');
  };

  const handleStatusUpdate = async (status: 'running' | 'paused' | 'stopped') => {
    if (!resolvedCampaignId) return;
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/campaigns/${resolvedCampaignId}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ status }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update campaign status');
      }

      await fetchCampaign();
      await fetchStats();
      await fetchLeads();
      await fetchActiveCalls();
      alert(`Campaign ${status === 'running' ? 'started' : status === 'paused' ? 'paused' : 'stopped'} successfully.`);
    } catch (err) {
      console.error('Error updating campaign status', err);
      alert(err instanceof Error ? err.message : 'Failed to update campaign status');
    }
  };

  const handleTestCall = async () => {
    if (!resolvedCampaignId || isTestingCall) return;
    try {
      setIsTestingCall(true);
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/campaigns/${resolvedCampaignId}/test-call`, {
        method: 'POST',
        headers: {
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detailMessage =
          typeof errorData.detail === 'string' && errorData.detail.trim().length > 0
            ? errorData.detail
            : 'Unable to initiate test call';
        console.warn('Test call could not be initiated', detailMessage);
        alert(detailMessage);
        return;
      }

      const data = await response.json().catch(() => null);
      await fetchStats();
      await fetchLeads();
      await fetchActiveCalls();
      alert((data && data.message) || 'Test call initiated successfully.');
    } catch (err) {
      console.error('Error triggering test call', err);
      alert(err instanceof Error ? err.message : 'Failed to trigger test call');
    } finally {
      setIsTestingCall(false);
    }
  };

  const fetchVerifiedCallerIds = useCallback(async () => {
    if (!userIdValue) {
      setVerifiedCallerIds([]);
      return;
    }
    try {
      setIsLoadingCallerIds(true);
      const token = localStorage.getItem('token');
      if (!token) {
        setVerifiedCallerIds([]);
        return;
      }
      const response = await fetch(`${API_URL}/api/phone-numbers/twilio/verified-caller-ids/${userIdValue}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      if (response.ok) {
        const data = await response.json();
        setVerifiedCallerIds(Array.isArray(data.verified_caller_ids) ? data.verified_caller_ids : []);
      } else {
        setVerifiedCallerIds([]);
      }
    } catch (callerIdError) {
      console.error('Failed to load verified caller IDs', callerIdError);
      setVerifiedCallerIds([]);
    } finally {
      setIsLoadingCallerIds(false);
    }
  }, [userIdValue]);

  const checkCallStatus = useCallback(async (callSid: string) => {
    if (!userIdValue) return;
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const response = await fetch(`${API_URL}/api/outbound-calls/call-status/${callSid}/${userIdValue}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setActiveCallStatus(data.status || '');
        if (['completed', 'failed', 'canceled'].includes(data.status)) {
          setIsCallActive(false);
          setActiveCallSid(null);
          if (callStatusIntervalRef.current) {
            clearInterval(callStatusIntervalRef.current);
            callStatusIntervalRef.current = null;
          }
          fetchStats();
          fetchLeads();
          fetchActiveCalls();
        }
      }
    } catch (statusError) {
      console.error('Error checking call status', statusError);
    }
  }, [fetchActiveCalls, fetchLeads, fetchStats, userIdValue]);

  const hangupCall = useCallback(async () => {
    if (!activeCallSid || !userIdValue) return;
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const response = await fetch(`${API_URL}/api/outbound-calls/hangup/${activeCallSid}/${userIdValue}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (response.ok) {
        setIsCallActive(false);
        setActiveCallSid(null);
        setActiveCallStatus('completed');
        if (callStatusIntervalRef.current) {
          clearInterval(callStatusIntervalRef.current);
          callStatusIntervalRef.current = null;
        }
        fetchStats();
        fetchLeads();
        fetchActiveCalls();
        alert('Call ended successfully');
      } else {
        alert('Failed to end call');
      }
    } catch (hangupError) {
      console.error('Error ending call', hangupError);
      alert('An error occurred while ending the call');
    }
  }, [activeCallSid, fetchActiveCalls, fetchLeads, fetchStats, userIdValue]);

  const handleMakeCall = async () => {
    if (!assistantInfo?.id) {
      alert('This campaign does not have an AI assistant assigned.');
      return;
    }
    if (!campaign?.caller_id) {
      alert('Campaign is missing a caller ID. Update the campaign configuration first.');
      return;
    }
    if (!callToNumber.trim()) {
      alert('Please enter a phone number to call');
      return;
    }

    const sanitized = callToNumber.replace(/[\s-()]/g, '');
    const phoneRegex = /^\+?[1-9]\d{1,14}$/;
    if (!phoneRegex.test(sanitized)) {
      alert('Please enter a valid phone number (e.g., +1234567890)');
      return;
    }

    try {
      setIsInitiatingCall(true);
      const token = localStorage.getItem('token');
      if (!token) {
        alert('You are not authenticated. Please log in again.');
        return;
      }
      const response = await fetch(`${API_URL}/api/outbound-calls/make-call/${assistantInfo.id}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ phone_number: sanitized }),
      });

      if (response.ok) {
        const data = await response.json();
        const callSid = data.call_sid;
        if (callSid) {
          setActiveCallSid(callSid);
          setActiveCallStatus('initiated');
          setIsCallActive(true);
          fetchStats();
          fetchLeads();
          fetchActiveCalls();
          if (callStatusIntervalRef.current) {
            clearInterval(callStatusIntervalRef.current);
          }
          callStatusIntervalRef.current = setInterval(() => {
            checkCallStatus(callSid);
          }, 2000);
        }
        setIsCallModalOpen(false);
        setCallToNumber('');
        alert('Outbound call initiated. Your assistant will handle the conversation.');
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(errorData.detail || 'Failed to initiate call');
      }
    } catch (callError) {
      console.error('Error initiating call', callError);
      alert('An error occurred while initiating the call');
    } finally {
      setIsInitiatingCall(false);
    }
  };

  const statusBadgeClass = (status: string) => {
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

  const leadStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'queued':
        return 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200';
      case 'completed':
        return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200';
      case 'failed':
      case 'no-answer':
        return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200';
      case 'busy':
        return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-200';
      case 'calling':
      case 'initiated':
      case 'ringing':
      case 'answered':
        return 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-200 animate-pulse';
      case 'machine':
        return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200';
      default:
        return 'bg-neutral-light text-neutral-dark dark:bg-gray-900 dark:text-gray-200';
    }
  };

  const formatLeadStatus = (status: string) => {
    if (!status) return 'Unknown';

    // Map specific statuses to user-friendly names
    const statusMap: Record<string, string> = {
      'no-answer': 'Not Connected',
      'failed': 'Not Connected',
      'busy': 'Busy',
      'completed': 'Call Completed',
      'queued': 'Queued',
      'calling': 'Ongoing Call',
      'machine': 'Voicemail',
      'initiated': 'Initiating...',
      'ringing': 'Ringing...',
      'answered': 'Answered',
    };

    // Return mapped status or format the original
    if (statusMap[status]) {
      return statusMap[status];
    }

    return status
      .split(/[-_]/)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

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

      <div className={`${isSidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'} transition-all duration-300`}>
        <TopBar
          isDarkMode={isDarkMode}
          toggleTheme={toggleTheme}
          onLogout={handleLogout}
          userInitial={userInitial}
          userLabel={userGreeting}
          onToggleMobileMenu={() => setIsMobileMenuOpen((prev) => !prev)}
          collapseSearchOnMobile
        />

        <main className="p-6 space-y-6">
          <button
            onClick={() => router.push('/campaigns')}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg border ${isDarkMode ? 'border-gray-700 text-gray-300 hover:bg-gray-800' : 'border-neutral-mid/20 text-dark hover:bg-neutral-light'} transition-colors text-sm font-medium`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Campaigns
          </button>

          <div>
            <h1 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-dark'}`}>Campaign Details</h1>
            <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} mt-1`}>Review configuration and trigger an instant test call.</p>
          </div>

          {error && (
            <div className={`${isDarkMode ? 'bg-red-900/20 border-red-800 text-red-300' : 'bg-red-50 border-red-200 text-red-700'} border rounded-xl px-4 py-3`}>
              {error}
            </div>
          )}

          {isLoading || !campaign ? (
            <div className="flex justify-center items-center py-16">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            </div>
          ) : (
            <>
              <section className={`${isDarkMode ? 'bg-gray-800 text-gray-100' : 'bg-white text-dark'} rounded-2xl p-6 shadow-sm`}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-bold mb-1">{campaign.name}</h2>
                    <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                      {campaign.country} • Caller ID {campaign.caller_id}
                    </p>
                    <p className={`${isDarkMode ? 'text-gray-500' : 'text-neutral-mid'} text-sm mt-2`}>
                      Created {formatDateTime(campaign.created_at)} • Updated {formatDateTime(campaign.updated_at)}
                    </p>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusBadgeClass(campaign.status)}`}>
                    {campaign.status.charAt(0).toUpperCase() + campaign.status.slice(1)}
                  </span>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
                  <div className={`${isDarkMode ? 'bg-gray-900' : 'bg-neutral-light'} rounded-xl p-4`}>
                    <h3 className="text-sm font-semibold mb-2">Working Window</h3>
                    <p className="text-sm">
                      {campaign.working_window.start} – {campaign.working_window.end} ({campaign.working_window.timezone})
                    </p>
                    <p className="text-xs mt-1">
                      Days: {campaign.working_window.days.map((d) => ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d]).join(', ')}
                    </p>
                  </div>
                  <div className={`${isDarkMode ? 'bg-gray-900' : 'bg-neutral-light'} rounded-xl p-4`}>
                    <h3 className="text-sm font-semibold mb-2">Schedule</h3>
                    <p className="text-sm">Start: {formatDateTime(campaign.start_at)}</p>
                    <p className="text-sm mt-1">Stop: {formatDateTime(campaign.stop_at)}</p>
                  </div>
                  <div className={`${isDarkMode ? 'bg-gray-900' : 'bg-neutral-light'} rounded-xl p-4`}>
                    <h3 className="text-sm font-semibold mb-2">Retry Policy</h3>
                    <p className="text-sm">Max attempts: {campaign.retry_policy.max_attempts}</p>
                    <p className="text-sm mt-1">Delays (min): {formatMinutesList(campaign.retry_policy.retry_after_minutes)}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3 mt-6">
                  <button
                    onClick={() => handleStatusUpdate('running')}
                    className="px-4 py-2 rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors text-sm font-semibold"
                  >
                    Start Campaign
                  </button>
                  <button
                    onClick={() => handleStatusUpdate('paused')}
                    className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-700 text-white hover:bg-gray-600' : 'bg-neutral-light text-dark hover:bg-neutral-mid/20'} transition-colors text-sm font-semibold`}
                  >
                    Pause Campaign
                  </button>
                  <button
                    onClick={() => handleStatusUpdate('stopped')}
                    className="px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors text-sm font-semibold"
                  >
                    Stop Campaign
                  </button>
                  <button
                    onClick={handleTestCall}
                    disabled={isTestingCall}
                    className={`px-4 py-2 rounded-lg ${isTestingCall ? 'bg-gray-400 cursor-not-allowed text-white' : 'bg-green-500 text-white hover:bg-green-600'} transition-colors text-sm font-semibold flex items-center gap-2`}
                  >
                    {isTestingCall ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Testing...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
                        </svg>
                        Instant Test Call
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => setIsBrowserCallOpen(true)}
                    disabled={!assistantInfo}
                    className={`px-4 py-2 rounded-lg ${!assistantInfo ? 'bg-gray-400 cursor-not-allowed text-white' : isDarkMode ? 'bg-purple-600 text-white hover:bg-purple-700' : 'bg-purple-500 text-white hover:bg-purple-600'} transition-colors text-sm font-semibold flex items-center gap-2`}
                    title={!assistantInfo ? 'Assign an AI assistant first' : 'Browser voice call (no phone needed)'}
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                    Browser Test
                  </button>
                  <button
                    onClick={() => {
                      setIsCallModalOpen(true);
                      setCallToNumber('');
                      fetchVerifiedCallerIds();
                    }}
                    disabled={!assistantInfo || isInitiatingCall}
                    className={`px-4 py-2 rounded-lg ${!assistantInfo || isInitiatingCall ? 'bg-gray-400 cursor-not-allowed text-white' : 'bg-blue-500 text-white hover:bg-blue-600'} transition-colors text-sm font-semibold flex items-center gap-2`}
                    title={!assistantInfo ? 'Assign an AI assistant to this campaign to enable outbound calls' : undefined}
                  >
                    {isInitiatingCall ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Dialing...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                        </svg>
                        Manual Outbound Call
                      </>
                    )}
                  </button>
                </div>

                {isCallActive && (
                  <div className={`mt-4 p-4 rounded-xl ${isDarkMode ? 'bg-blue-900/30 border border-blue-800 text-blue-200' : 'bg-blue-50 border border-blue-200 text-blue-900'} flex flex-wrap items-center justify-between gap-3`}>
                    <div>
                      <p className="text-sm font-semibold">Active outbound call in progress</p>
                      <p className="text-xs mt-1">
                        Status: <span className="font-medium">{activeCallStatus || 'in-progress'}</span>
                      </p>
                    </div>
                    <button
                      onClick={hangupCall}
                      className={`px-4 py-2 rounded-lg text-sm font-semibold ${isDarkMode ? 'bg-red-700 hover:bg-red-600 text-white' : 'bg-red-500 hover:bg-red-600 text-white'} transition-colors`}
                    >
                      Hang Up
                    </button>
                  </div>
                )}

                <div className="flex flex-wrap gap-3 mt-4">
                  <button
                    onClick={() => setIsEditModalOpen(true)}
                    className={`px-4 py-2 rounded-lg border ${isDarkMode ? 'border-gray-600 text-white hover:bg-gray-700' : 'border-neutral-mid/20 text-dark hover:bg-neutral-light'} transition-colors text-sm font-semibold`}
                  >
                    Edit Campaign
                  </button>
                  <button
                    onClick={() => setIsUploadModalOpen(true)}
                    className="px-4 py-2 rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors text-sm font-semibold"
                  >
                    Upload Leads CSV
                  </button>
                  <button
                    onClick={() => setIsLeadViewerOpen(true)}
                    className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-700 text-white hover:bg-gray-600' : 'bg-neutral-light text-dark hover:bg-neutral-mid/20'} transition-colors text-sm font-semibold`}
                  >
                    View All Leads
                  </button>
                </div>
              </section>

              <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className={`${isDarkMode ? 'bg-gray-800 text-gray-100' : 'bg-white text-dark'} rounded-2xl p-6 shadow-sm`}>
                  <h3 className="text-lg font-semibold mb-4">Performance</h3>
                  {stats ? (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>Total Leads</p>
                        <p className="text-2xl font-bold">{stats.total_leads}</p>
                      </div>
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>Queued</p>
                        <p className="text-2xl font-bold text-blue-500">{stats.queued}</p>
                      </div>
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>Completed</p>
                        <p className="text-2xl font-bold text-green-500">{stats.completed}</p>
                      </div>
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>Failed</p>
                        <p className="text-2xl font-bold text-red-500">{stats.failed}</p>
                      </div>
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>No Answer</p>
                        <p className="text-2xl font-bold">{stats.no_answer}</p>
                      </div>
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>Busy</p>
                        <p className="text-2xl font-bold">{stats.busy}</p>
                      </div>
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>Avg Sentiment</p>
                        <p className="text-2xl font-bold">{stats.avg_sentiment_score != null ? stats.avg_sentiment_score.toFixed(2) : '—'}</p>
                      </div>
                      <div>
                        <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} text-sm`}>Avg Call Duration</p>
                        <p className="text-2xl font-bold">{formatDuration(stats.avg_call_duration)}</p>
                      </div>
                    </div>
                  ) : (
                    <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>No statistics available yet.</p>
                  )}
                </div>

                <div className={`${isDarkMode ? 'bg-gray-800 text-gray-100' : 'bg-white text-dark'} rounded-2xl p-6 shadow-sm`}>
                  <h3 className="text-lg font-semibold mb-4">Configuration</h3>
                  <div className="space-y-3 text-sm">
                    <div>
                      <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} uppercase text-xs font-semibold`}>Calendar Booking</p>
                      <p>{campaign.calendar_enabled ? 'Enabled' : 'Disabled'}</p>
                    </div>
                    <div>
                      <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} uppercase text-xs font-semibold`}>System Prompt Override</p>
                      <p>{campaign.system_prompt_override ? campaign.system_prompt_override : 'Using assistant default prompt.'}</p>
                    </div>
                    <div>
                      <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} uppercase text-xs font-semibold`}>Database Lookup</p>
                      {campaign.database_config?.enabled ? (
                        <ul className="list-disc pl-5 space-y-1">
                          <li>Type: {campaign.database_config.type || 'postgresql'}</li>
                          <li>Host: {campaign.database_config.host || '—'}</li>
                          <li>Database: {campaign.database_config.database || '—'}</li>
                          <li>Table: {campaign.database_config.table_name || '—'}</li>
                          <li>Search Columns: {campaign.database_config.search_columns?.join(', ') || '—'}</li>
                        </ul>
                      ) : (
                        <p>Disabled</p>
                      )}
                    </div>
                  </div>
                </div>

                <div className={`${isDarkMode ? 'bg-gray-800 text-gray-100' : 'bg-white text-dark'} rounded-2xl p-6 shadow-sm`}>
                  <h3 className="text-lg font-semibold mb-4">Live Call Monitor</h3>
                  {isLoadingActiveCalls ? (
                    <p className="text-sm text-gray-500">Checking active calls…</p>
                  ) : activeCalls.length > 0 ? (
                    <div className="space-y-4">
                      {activeCalls.map((lead, idx) => {
                        const uniqueKey = lead.id || (lead as { _id?: string })._id || `${lead.e164 || lead.raw_number}-${idx}`;
                        return (
                          <div key={uniqueKey} className={`p-3 rounded-xl ${isDarkMode ? 'bg-gray-700' : 'bg-neutral-light'}`}>
                            <p className="text-xs uppercase tracking-wide text-primary font-semibold">Dialing Lead #{typeof lead.order_index === 'number' ? lead.order_index + 1 : '—'}</p>
                            <p className="text-lg font-bold mt-1">{getLeadDisplayName(lead)}</p>
                            <p className="font-mono text-sm">{lead.e164 || lead.raw_number || '—'}</p>
                            <p className="text-xs mt-1">{formatLeadStatus(lead.status)}</p>
                            <p className="text-xs text-gray-500">Last updated {formatDateTime(lead.updated_at)}</p>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">No calls are in progress at the moment.</p>
                  )}

                  {nextQueuedLead && (
                    <div className={`mt-6 border-t pt-4 ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/20'}`}>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Next in Queue</p>
                      <p className="text-base font-semibold">#{typeof nextQueuedLead.order_index === 'number' ? nextQueuedLead.order_index + 1 : '—'} · {getLeadDisplayName(nextQueuedLead)}</p>
                      <p className="font-mono text-sm">{nextQueuedLead.e164 || nextQueuedLead.raw_number || '—'}</p>
                    </div>
                  )}
                </div>
              </section>

              <section className={`${isDarkMode ? 'bg-gray-800 text-gray-100' : 'bg-white text-dark'} rounded-2xl p-6 shadow-sm`}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold">Recent Leads</h3>
                  <button
                    onClick={() => setIsLeadViewerOpen(true)}
                    className={`text-sm font-medium ${isDarkMode ? 'text-primary' : 'text-primary'} hover:underline`}
                  >
                    View All
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                    <thead className={isDarkMode ? 'bg-gray-900 text-gray-300' : 'bg-neutral-light text-gray-600'}>
                      <tr>
                        <th className="px-4 py-2 text-left font-semibold">#</th>
                        <th className="px-4 py-2 text-left font-semibold">Batch</th>
                        <th className="px-4 py-2 text-left font-semibold">Lead</th>
                        <th className="px-4 py-2 text-left font-semibold">Contact Number</th>
                        <th className="px-4 py-2 text-left font-semibold">Email</th>
                        <th className="px-4 py-2 text-left font-semibold">Status</th>
                        <th className="px-4 py-2 text-left font-semibold">Timezone</th>
                        <th className="px-4 py-2 text-left font-semibold">Updated</th>
                      </tr>
                    </thead>
                    <tbody className={isDarkMode ? 'divide-y divide-gray-700' : 'divide-y divide-gray-200'}>
                      {leads.length === 0 ? (
                        <tr key="no-leads">
                          <td colSpan={8} className="px-4 py-6 text-center text-gray-500">
                            No leads found for this campaign.
                          </td>
                        </tr>
                      ) : (
                        leads.map((lead, index) => (
                          <tr key={lead.id || lead._id || `lead-row-${index}`}>
                            <td className="px-4 py-2 font-mono text-xs">{typeof lead.order_index === 'number' ? lead.order_index + 1 : index + 1}</td>
                            <td className="px-4 py-2">{lead.batch_name || '—'}</td>
                            <td className="px-4 py-2">{getLeadDisplayName(lead)}</td>
                            <td className="px-4 py-2 font-mono">{lead.e164 || lead.raw_number || '—'}</td>
                            <td className="px-4 py-2">{lead.email || '—'}</td>
                            <td className="px-4 py-2">
                              <div className="flex flex-col gap-1">
                                <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold ${leadStatusBadgeClass(lead.status)}`}>
                                  {formatLeadStatus(lead.status)}
                                </span>
                                {lead.last_outcome && lead.last_outcome !== lead.status && (
                                  <span className="text-xs text-gray-500">
                                    Last: {formatLeadStatus(lead.last_outcome)}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-4 py-2">{lead.timezone || '—'}</td>
                            <td className="px-4 py-2">{formatDateTime(lead.updated_at)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </main>
      </div>

      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        ></div>
      )}

      {campaign && userIdValue && (
        <>
          <CreateCampaignModal
            isOpen={isEditModalOpen}
            onClose={() => setIsEditModalOpen(false)}
            onSuccess={() => {
              fetchCampaign();
              fetchStats();
            }}
            isDarkMode={isDarkMode}
            userId={userIdValue}
            mode="edit"
            campaignId={resolvedCampaignId}
            initialCampaign={campaign}
            initialStep={1}
          />
          <CreateCampaignModal
            isOpen={isUploadModalOpen}
            onClose={() => setIsUploadModalOpen(false)}
            onSuccess={() => {
              fetchStats();
              fetchLeads();
            }}
            isDarkMode={isDarkMode}
            userId={userIdValue}
            mode="edit"
            campaignId={resolvedCampaignId}
            initialCampaign={campaign}
            initialStep={3}
          />
          <LeadViewerModal
            isOpen={isLeadViewerOpen}
            onClose={() => setIsLeadViewerOpen(false)}
            campaignId={resolvedCampaignId}
            isDarkMode={isDarkMode}
          />
          {/* Browser Call Modal */}
          {isBrowserCallOpen && assistantInfo && (
            <BrowserCallModal
              isOpen={true}
              onClose={() => setIsBrowserCallOpen(false)}
              assistantId={assistantInfo.id}
              assistantName={assistantInfo.name}
              isDarkMode={isDarkMode}
              apiBaseUrl={API_URL}
              userId={userIdValue || undefined}
            />
          )}

          {isCallModalOpen && (
            <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 animate-fadeIn">
              <div className={`${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-2xl max-w-md w-full shadow-2xl`}>
                <div className={`px-6 py-5 border-b ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} flex items-center justify-between`}>
                  <div>
                    <h2 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                      Manual Outbound Call
                    </h2>
                    <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                      From: {campaign.caller_id || 'No caller ID configured'}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setIsCallModalOpen(false);
                      setCallToNumber('');
                    }}
                    className={`p-2 rounded-xl ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-neutral-light'} transition-colors`}
                  >
                    <svg className={`w-6 h-6 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <div className="p-6">
                  <div className={`mb-6 p-4 rounded-xl ${isDarkMode ? 'bg-blue-900/20 border border-blue-800' : 'bg-blue-50 border border-blue-200'}`}>
                    <div className="flex items-center gap-3">
                      <div className={`w-12 h-12 rounded-full flex items-center justify-center ${isDarkMode ? 'bg-blue-800' : 'bg-blue-100'}`}>
                        <svg className="w-6 h-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                      </div>
                      <div>
                        <p className={`text-xs font-semibold uppercase tracking-wider ${isDarkMode ? 'text-blue-400' : 'text-blue-700'}`}>
                          AI Assistant
                        </p>
                        <p className={`text-lg font-semibold ${isDarkMode ? 'text-blue-300' : 'text-blue-900'}`}>
                          {assistantInfo?.name || 'No assistant assigned'}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mb-6">
                    <label className={`block text-sm font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                      Number to call
                    </label>
                    <input
                      type="tel"
                      value={callToNumber}
                      onChange={(event) => setCallToNumber(event.target.value)}
                      placeholder="Enter phone number (e.g., +1234567890)"
                      className={`w-full px-4 py-3 rounded-xl border focus:outline-none focus:ring-2 ${
                        isDarkMode
                          ? 'bg-gray-900 border-gray-700 text-white focus:ring-primary/60'
                          : 'bg-white border-gray-300 text-neutral-dark focus:ring-primary/40'
                      }`}
                    />
                    <p className={`text-xs mt-2 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                      You can also pick from your verified caller IDs below to auto-fill this field.
                    </p>
                  </div>

                  <div className="mb-6">
                    <label className={`block text-sm font-semibold mb-3 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                      Verified Caller IDs
                    </label>
                    {isLoadingCallerIds ? (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                      </div>
                    ) : verifiedCallerIds.length > 0 ? (
                      <div className="space-y-2 max-h-72 overflow-y-auto">
                        {verifiedCallerIds.map((caller, index) => {
                          const callerNumber = typeof caller === 'string' ? caller : caller?.phone_number;
                          const callerLabel =
                            typeof caller === 'string'
                              ? caller
                              : caller?.friendly_name || caller?.phone_number || 'Verified Number';
                          if (!callerNumber) {
                            return null;
                          }
                          return (
                            <button
                              key={index}
                              onClick={() => setCallToNumber(callerNumber)}
                              className={`w-full text-left p-4 rounded-xl border-2 transition-all duration-200 ${
                                callToNumber === callerNumber
                                  ? `${isDarkMode ? 'bg-primary/20 border-primary' : 'bg-primary/10 border-primary'}`
                                  : `${isDarkMode ? 'bg-gray-700 border-gray-600 hover:border-gray-500' : 'bg-white border-gray-200 hover:border-gray-300'}`
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3 flex-1">
                                  <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                                    callToNumber === callerNumber
                                      ? 'bg-primary text-white'
                                      : `${isDarkMode ? 'bg-gray-600 text-gray-300' : 'bg-gray-200 text-gray-600'}`
                                  }`}>
                                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                    </svg>
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <h4 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                                      {callerLabel || 'Verified Number'}
                                    </h4>
                                    <p className={`text-sm font-mono ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                                      {callerNumber}
                                    </p>
                                  </div>
                                </div>
                                {callToNumber === callerNumber && (
                                  <svg className="w-6 h-6 text-primary flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                  </svg>
                                )}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className={`p-6 rounded-xl text-center ${isDarkMode ? 'bg-yellow-900/20 border border-yellow-800' : 'bg-yellow-50 border border-yellow-200'}`}>
                        <svg className="w-12 h-12 mx-auto mb-3 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <p className={`text-sm font-semibold mb-2 ${isDarkMode ? 'text-yellow-400' : 'text-yellow-900'}`}>
                          No Verified Caller IDs
                        </p>
                        <p className={`text-xs ${isDarkMode ? 'text-yellow-300' : 'text-yellow-800'}`}>
                          Verify numbers in your Twilio console to quickly select them from here.
                        </p>
                        <a
                          href="https://console.twilio.com/us1/develop/phone-numbers/manage/verified"
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`inline-block mt-3 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                            isDarkMode ? 'bg-yellow-800 hover:bg-yellow-700 text-yellow-200' : 'bg-yellow-600 hover:bg-yellow-700 text-white'
                          }`}
                        >
                          Verify Numbers in Twilio →
                        </a>
                      </div>
                    )}
                  </div>

                  <div className={`p-4 rounded-xl ${isDarkMode ? 'bg-green-900/20 border border-green-800' : 'bg-green-50 border border-green-200'}`}>
                    <div className="flex items-start gap-2">
                      <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <div>
                        <p className={`text-sm font-semibold ${isDarkMode ? 'text-green-400' : 'text-green-900'}`}>
                          What to expect
                        </p>
                        <p className={`text-xs mt-1 ${isDarkMode ? 'text-green-300' : 'text-green-800'}`}>
                          The recipient will receive a call from <strong>{campaign.caller_id || 'your Twilio number'}</strong> and will be handled by <strong>{assistantInfo?.name || 'your AI assistant'}</strong>.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className={`px-6 py-4 border-t ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} flex gap-3`}>
                  <button
                    onClick={() => {
                      setIsCallModalOpen(false);
                      setCallToNumber('');
                    }}
                    className={`flex-1 px-4 py-3 rounded-xl ${isDarkMode ? 'bg-gray-700 hover:bg-gray-600 text-white' : 'bg-neutral-light hover:bg-neutral-mid/20 text-neutral-dark'} transition-colors font-semibold`}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleMakeCall}
                    disabled={isInitiatingCall || !callToNumber.trim()}
                    className={`flex-1 px-4 py-3 rounded-xl font-semibold transition-all duration-200 ${
                      isInitiatingCall || !callToNumber.trim()
                        ? 'bg-gray-400 cursor-not-allowed text-gray-600'
                        : 'bg-gradient-to-r from-green-500 to-green-600 text-white hover:shadow-lg hover:shadow-green-500/25'
                    }`}
                  >
                    {isInitiatingCall ? (
                      <div className="flex items-center justify-center gap-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        Calling...
                      </div>
                    ) : (
                      <div className="flex items-center justify-center gap-2">
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                        </svg>
                        Make Call
                      </div>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
