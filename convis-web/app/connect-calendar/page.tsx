'use client';

import { useCallback, useEffect, useMemo, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import { NAV_ITEMS, NavigationItem } from '../components/Navigation';
import { TopBar } from '../components/TopBar';
import { MonthlyCalendar } from '../components/MonthlyCalendar';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

type Provider = 'google' | 'microsoft';

interface StoredUser {
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
}

interface CalendarAccount {
  id: string;
  provider: Provider;
  email?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface CalendarEvent {
  id: string;
  provider: Provider;
  title: string;
  start?: string | null;
  end?: string | null;
  location?: string | null;
  meeting_link?: string | null;
  organizer?: string | null;
  account_email?: string | null;
}

interface BannerState {
  type: 'success' | 'error';
  message: string;
}

const PROVIDER_LABELS: Record<Provider, string> = {
  google: 'Google Calendar',
  microsoft: 'Microsoft Teams / Outlook',
};

const PROVIDER_BADGE_CLASSES: Record<Provider, string> = {
  google: 'bg-red-500 text-white dark:bg-red-600 dark:text-white',
  microsoft: 'bg-blue-500 text-white dark:bg-blue-600 dark:text-white',
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
};

function ConnectCalendarContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [accounts, setAccounts] = useState<CalendarAccount[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(true);
  const [isLoadingEvents, setIsLoadingEvents] = useState(true);
  const [banner, setBanner] = useState<BannerState | null>(null);
  const [connectingProvider, setConnectingProvider] = useState<Provider | null>(null);
  const [activeNav, setActiveNav] = useState('Connect calendar');
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const navigationItems = useMemo(() => NAV_ITEMS, []);

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

  const resolvedUserId = useMemo(() => {
    return user?.id || user?._id || user?.clientId || '';
  }, [user]);

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');
    const savedTheme = localStorage.getItem('theme');

    if (!storedToken || !userStr) {
      router.push('/login');
      return;
    }

    setToken(storedToken);

    if (savedTheme === 'dark') {
      setIsDarkMode(true);
    }

    try {
      setUser(JSON.parse(userStr));
    } catch {
      localStorage.removeItem('user');
      router.push('/login');
    }
  }, [router]);

  const fetchAccounts = useCallback(async (userId: string) => {
    try {
      setIsLoadingAccounts(true);
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/calendar/accounts/${userId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (!response.ok) {
        throw new Error('Failed to load connected calendars');
      }

      const data = await response.json();
      setAccounts(Array.isArray(data.accounts) ? (data.accounts as CalendarAccount[]) : []);
    } catch (error) {
      console.error(error);
      setAccounts([]);
      setBanner({ type: 'error', message: error instanceof Error ? error.message : 'Unable to load calendar accounts.' });
    } finally {
      setIsLoadingAccounts(false);
    }
  }, []);

  const fetchEvents = useCallback(async (userId: string, timeMin?: string, timeMax?: string) => {
    try {
      setIsLoadingEvents(true);
      const token = localStorage.getItem('token');

      // Build query parameters
      const params = new URLSearchParams({
        limit: '100',  // Fetch up to 100 events for monthly view
      });

      if (timeMin) params.append('time_min', timeMin);
      if (timeMax) params.append('time_max', timeMax);

      const response = await fetch(`${API_URL}/api/calendar/events/${userId}?${params}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (!response.ok) {
        throw new Error('Failed to load calendar events');
      }

      const data = await response.json();
      setEvents(Array.isArray(data.events) ? (data.events as CalendarEvent[]) : []);
    } catch (error) {
      console.error(error);
      setEvents([]);
    } finally {
      setIsLoadingEvents(false);
    }
  }, []);

  useEffect(() => {
    if (!resolvedUserId) return;
    fetchAccounts(resolvedUserId);

    // Fetch events for current month (3 months range: last month, current, next month)
    const now = new Date();
    const startOfRange = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const endOfRange = new Date(now.getFullYear(), now.getMonth() + 2, 0);

    fetchEvents(
      resolvedUserId,
      startOfRange.toISOString(),
      endOfRange.toISOString()
    );
  }, [resolvedUserId, fetchAccounts, fetchEvents]);

  useEffect(() => {
    const status = searchParams?.get('status');
    if (!status) return;

    const provider = searchParams.get('provider') as Provider | null;
    const message = searchParams.get('message');

    if (status === 'success') {
      const friendly = provider ? `${PROVIDER_LABELS[provider]} connected successfully.` : 'Calendar connected successfully.';
      setBanner({ type: 'success', message: friendly });
      if (resolvedUserId) {
        fetchAccounts(resolvedUserId);
        fetchEvents(resolvedUserId);
      }
    } else if (status === 'error') {
      setBanner({ type: 'error', message: message || 'Unable to connect calendar. Please try again.' });
    }

    router.replace('/connect-calendar');
  }, [searchParams, router, resolvedUserId, fetchAccounts, fetchEvents]);

  const handleNavigation = (item: NavigationItem) => {
    setActiveNav(item.name);
    if (item.href) {
      router.push(item.href);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('clientId');
    router.push('/login');
  };

  const toggleTheme = () => {
    const newTheme = !isDarkMode;
    setIsDarkMode(newTheme);
    localStorage.setItem('theme', newTheme ? 'dark' : 'light');
  };

  const handleConnect = async (provider: Provider) => {
    if (!resolvedUserId) {
      setBanner({ type: 'error', message: 'Missing user information. Please sign in again.' });
      return;
    }

    try {
      setConnectingProvider(provider);
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/calendar/${provider}/auth-url?user_id=${resolvedUserId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const errorDetail = data.detail || 'Unable to start the calendar connection flow.';

        // Check if it's a configuration error
        if (errorDetail.includes('credentials') || errorDetail.includes('not configured') || errorDetail.includes('CLIENT_ID')) {
          throw new Error(
            `${provider === 'google' ? 'Google' : 'Microsoft'} Calendar is not configured. ` +
            'Please configure OAuth credentials in the backend .env file. ' +
            'See QUICK_CALENDAR_FIX.md for setup instructions.'
          );
        }

        throw new Error(errorDetail);
      }

      const data = await response.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        throw new Error('Authorization URL missing in response.');
      }
    } catch (error) {
      console.error(error);
      setBanner({ type: 'error', message: error instanceof Error ? error.message : 'Failed to initiate calendar connection.' });
    } finally {
      setConnectingProvider(null);
    }
  };

  const handleDisconnect = async (accountId: string) => {
    if (!confirm('Are you sure you want to disconnect this calendar?')) {
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/calendar/accounts/${accountId}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to disconnect calendar');
      }

      setBanner({ type: 'success', message: 'Calendar disconnected.' });
      if (resolvedUserId) {
        fetchAccounts(resolvedUserId);

        // Refetch events for current range
        const now = new Date();
        const startOfRange = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        const endOfRange = new Date(now.getFullYear(), now.getMonth() + 2, 0);
        fetchEvents(resolvedUserId, startOfRange.toISOString(), endOfRange.toISOString());
      }
    } catch (error) {
      console.error(error);
      setBanner({ type: 'error', message: error instanceof Error ? error.message : 'Failed to disconnect calendar.' });
    }
  };

  const handleMonthChange = useCallback((year: number, month: number) => {
    if (!resolvedUserId) return;

    // Fetch events for the selected month +/- 1 month buffer
    const startOfRange = new Date(year, month - 1, 1);
    const endOfRange = new Date(year, month + 2, 0);

    fetchEvents(
      resolvedUserId,
      startOfRange.toISOString(),
      endOfRange.toISOString()
    );
  }, [resolvedUserId, fetchEvents]);

  if (!user) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${isDarkMode ? 'bg-gray-900' : 'bg-neutral-light'}`}>
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${isDarkMode ? 'dark bg-gray-900' : 'bg-neutral-light'}`}>
      <aside
        onMouseEnter={() => setIsSidebarCollapsed(false)}
        onMouseLeave={() => setIsSidebarCollapsed(true)}
        className={`fixed left-0 top-0 h-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} border-r ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} transition-all duration-300 z-40 ${isSidebarCollapsed ? 'w-20' : 'w-64'} ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}
      >
        <div className="flex flex-col h-full">
          <div className={`flex items-center ${isSidebarCollapsed ? 'justify-center' : 'justify-start gap-3'} ${isSidebarCollapsed ? 'px-4' : 'px-6'} py-4 border-b ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'}`}>
            <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center flex-shrink-0">
              <DotLottieReact src="/microphone-animation.lottie" loop autoplay style={{ width: '24px', height: '24px' }} />
            </div>
            {!isSidebarCollapsed && (
              <span className={`font-bold text-lg ${isDarkMode ? 'text-white' : 'text-neutral-dark'} whitespace-nowrap`}>Convis AI</span>
            )}
          </div>

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
          <div className="flex flex-col gap-2">
            <h1 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-dark'}`}>Connect Calendar</h1>
            <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
              Link your Google or Microsoft calendars to sync appointments, view availability, and let Convis AI
              book meetings automatically.
            </p>
          </div>

          {banner && (
            <div
              className={`rounded-xl border px-4 py-3 flex items-center gap-3 ${
                banner.type === 'success'
                  ? isDarkMode
                    ? 'bg-green-900/20 border-green-700 text-green-200'
                    : 'bg-green-50 border-green-200 text-green-700'
                  : isDarkMode
                    ? 'bg-red-900/20 border-red-700 text-red-200'
                    : 'bg-red-50 border-red-200 text-red-700'
              }`}
            >
              <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm font-medium">{banner.message}</span>
            </div>
          )}

          <section className={`${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-2xl p-6 shadow-sm`}>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-dark'}`}>Connect a calendar</h2>
                <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                  Authorize Convis AI to read availability and create events on your behalf.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => handleConnect('google')}
                  disabled={connectingProvider !== null}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl border ${
                    isDarkMode ? 'border-gray-600 text-white hover:bg-gray-700' : 'border-neutral-mid/20 text-dark hover:bg-neutral-light'
                  } transition-colors`}
                >
                  <span role="img" aria-label="Google">🗓️</span>
                  {connectingProvider === 'google' ? 'Redirecting…' : 'Connect Google'}
                </button>
                <button
                  onClick={() => handleConnect('microsoft')}
                  disabled={connectingProvider !== null}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl border ${
                    isDarkMode ? 'border-gray-600 text-white hover:bg-gray-700' : 'border-neutral-mid/20 text-dark hover:bg-neutral-light'
                  } transition-colors`}
                >
                  <span role="img" aria-label="Microsoft">💼</span>
                  {connectingProvider === 'microsoft' ? 'Redirecting…' : 'Connect Microsoft'}
                </button>
              </div>
            </div>

            <div className={`mt-6 grid gap-4 ${accounts.length === 0 ? 'md:grid-cols-1' : 'md:grid-cols-2'}`}>
              <div className={`${isDarkMode ? 'bg-gray-900/50' : 'bg-neutral-light'} rounded-2xl p-4`}>
                <h3 className={`text-sm font-semibold uppercase tracking-wide mb-3 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                  Connected calendars
                </h3>
                {isLoadingAccounts ? (
                  <div className="flex items-center justify-center py-6">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                  </div>
                ) : accounts.length === 0 ? (
                  <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    No calendars connected yet. Click a button above to connect Google or Microsoft.
                  </p>
                ) : (
                  <div className="space-y-4">
                    {accounts.map((account) => (
                      <div
                        key={account.id}
                        className={`${isDarkMode ? 'bg-gray-800/70 border-gray-700' : 'bg-white border-neutral-mid/10'} border rounded-xl p-4 flex items-center justify-between gap-4`}
                      >
                        <div className="flex flex-col">
                          <span className={`text-xs font-semibold px-2 py-1 rounded-full w-fit ${PROVIDER_BADGE_CLASSES[account.provider]}`}>
                            {PROVIDER_LABELS[account.provider]}
                          </span>
                          <span className={`text-sm mt-2 ${isDarkMode ? 'text-white' : 'text-dark'}`}>{account.email || 'Unknown account'}</span>
                          <span className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                            Connected {account.updated_at ? formatDateTime(account.updated_at) : 'just now'}
                          </span>
                        </div>
                        <button
                          onClick={() => handleDisconnect(account.id)}
                          className="text-sm font-medium text-red-500 hover:text-red-600"
                        >
                          Disconnect
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className={`${isDarkMode ? 'bg-gray-900/50' : 'bg-neutral-light'} rounded-2xl p-4`}>
                <h3 className={`text-sm font-semibold uppercase tracking-wide mb-3 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                  Upcoming events
                </h3>
                {isLoadingEvents ? (
                  <div className="flex items-center justify-center py-6">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                  </div>
                ) : events.length === 0 ? (
                  <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    No upcoming events detected. Once connected, your upcoming events will appear here.
                  </p>
                ) : (
                  <div className="space-y-4 max-h-[360px] overflow-y-auto pr-2">
                    {events.map((event) => (
                      <div key={`${event.provider}-${event.id}`} className={`${isDarkMode ? 'bg-gray-800/70 border-gray-700' : 'bg-white border-neutral-mid/10'} border rounded-xl p-4`}>
                        <div className="flex items-center justify-between gap-2">
                          <h4 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-dark'}`}>{event.title || '(No title)'}</h4>
                          <span className={`text-xs font-semibold px-2 py-1 rounded-full ${PROVIDER_BADGE_CLASSES[event.provider]}`}>
                            {event.provider === 'google' ? 'Google' : 'Microsoft'}
                          </span>
                        </div>
                        <p className={`text-sm mt-2 ${isDarkMode ? 'text-gray-300' : 'text-dark/70'}`}>{formatDateTime(event.start)}</p>
                        {event.location && <p className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>{event.location}</p>}
                        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                          {event.meeting_link && (
                            <a
                              href={event.meeting_link}
                              target="_blank"
                              rel="noreferrer"
                              className="text-primary font-medium hover:underline"
                            >
                              Join meeting
                            </a>
                          )}
                          {event.account_email && (
                            <span className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                              via {event.account_email}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Monthly Calendar View */}
          {events.length > 0 && (
            <section className={`${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-2xl p-6 shadow-sm`}>
              <MonthlyCalendar
                events={events}
                isDarkMode={isDarkMode}
                onDateClick={(date) => {
                  console.log('Date clicked:', date);
                }}
                onMonthChange={handleMonthChange}
              />
            </section>
          )}

          <section className={`${isDarkMode ? 'bg-gray-800/70 border-gray-700' : 'bg-white border-neutral-mid/10'} border rounded-2xl p-6`}>
            <h2 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-dark'}`}>How it works</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              {[
                {
                  title: '1. Connect',
                  body: 'Authorize Convis AI to read free/busy times and create events on your calendar.',
                },
                {
                  title: '2. Sync availability',
                  body: 'Your connected campaigns can check availability before proposing a meeting slot.',
                },
                {
                  title: '3. Auto-book meetings',
                  body: 'When a conversation results in a booking, we drop the appointment onto your calendar instantly.',
                },
              ].map((item) => (
                <div key={item.title} className={`${isDarkMode ? 'bg-gray-900/40' : 'bg-neutral-light'} rounded-2xl p-4`}>
                  <h3 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-dark'}`}>{item.title}</h3>
                  <p className={`text-sm mt-2 ${isDarkMode ? 'text-gray-300' : 'text-dark/70'}`}>{item.body}</p>
                </div>
              ))}
            </div>
          </section>
        </main>
      </div>

      {isMobileMenuOpen && (
        <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={() => setIsMobileMenuOpen(false)}></div>
      )}
    </div>
  );
}

function ConnectCalendarPageContent() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-neutral-light dark:bg-gray-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    }>
      <ConnectCalendarContent />
    </Suspense>
  );
}

export default function ConnectCalendarPage() {
  return <ConnectCalendarPageContent />;
}
