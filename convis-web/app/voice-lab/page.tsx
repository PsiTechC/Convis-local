'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import { NAV_ITEMS, NavigationItem } from '../components/Navigation';
import { TopBar } from '../components/TopBar';

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

interface Voice {
  id: string;
  name: string;
  provider: 'cartesia' | 'elevenlabs' | 'openai' | 'sarvam' | 'piper';
  gender: 'male' | 'female' | 'neutral';
  accent: string;
  language: string;
  description?: string;
  age_group?: 'young' | 'middle-aged' | 'old';
  use_case?: string;
  model?: string;
  nickname?: string;
  added_at?: string;
}

interface VoiceListResponse {
  voices: Voice[];
  total: number;
  providers: string[];
}

export default function VoiceLabPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [voices, setVoices] = useState<Voice[]>([]);
  const [savedVoices, setSavedVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentlyPlaying, setCurrentlyPlaying] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [user, setUser] = useState<StoredUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);

  // UI State
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [activeNav, setActiveNav] = useState('Voice Lab');
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  // Filters
  const [selectedProvider, setSelectedProvider] = useState<string>('all');
  const [selectedGender, setSelectedGender] = useState<string>('all');
  const [selectedAccent, setSelectedAccent] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showOnlySaved, setShowOnlySaved] = useState(false);
  const [isSyncingVoices, setIsSyncingVoices] = useState(false);
  const [syncMessage, setSyncMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Audio ref
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Provider colors matching your design system
  const providerColors: Record<string, { bg: string; text: string; border: string }> = {
    cartesia: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-400', border: 'border-purple-300 dark:border-purple-700' },
    elevenlabs: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400', border: 'border-blue-300 dark:border-blue-700' },
    openai: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400', border: 'border-green-300 dark:border-green-700' },
    sarvam: { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-700 dark:text-orange-400', border: 'border-orange-300 dark:border-orange-700' },
    piper: { bg: 'bg-emerald-100 dark:bg-emerald-900/30', text: 'text-emerald-700 dark:text-emerald-400', border: 'border-emerald-300 dark:border-emerald-700' },
    xtts: { bg: 'bg-cyan-100 dark:bg-cyan-900/30', text: 'text-cyan-700 dark:text-cyan-400', border: 'border-cyan-300 dark:border-cyan-700' },
  };

  const defaultProviderColors = {
    bg: 'bg-gray-100 dark:bg-gray-800/60',
    text: 'text-gray-700 dark:text-gray-300',
    border: 'border-gray-300 dark:border-gray-700',
  };

  // Gender icons
  const genderIcons: Record<string, string> = {
    male: '♂',
    female: '♀',
    neutral: '⚥',
  };

  useEffect(() => {
    // Check authentication
    const storedToken = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');

    if (!storedToken) {
      router.push('/login');
      return;
    }

    setToken(storedToken);

    // Get userId from user object
    if (userStr) {
      const parsedUser: StoredUser = JSON.parse(userStr);
      setUser(parsedUser);
      const resolvedUserId = parsedUser.id || parsedUser._id || parsedUser.clientId;
      if (resolvedUserId) {
        setUserId(resolvedUserId);

        // Check dark mode
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'dark') {
          setIsDarkMode(true);
        }

        // Fetch voices and saved preferences
        fetchVoices();
        fetchSavedVoices(resolvedUserId);
      } else {
        router.push('/login');
      }
    } else {
      router.push('/login');
    }
  }, []);

  const fetchVoices = async (filters?: { provider?: string; gender?: string; accent?: string }) => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      const userStr = localStorage.getItem('user');
      let currentUserId = userId;

      // Get userId if not already set
      if (!currentUserId && userStr) {
        const parsedUser: StoredUser = JSON.parse(userStr);
        currentUserId = parsedUser.id || parsedUser._id || parsedUser.clientId || null;
      }

      // Build query params
      const params = new URLSearchParams();
      if (filters?.provider && filters.provider !== 'all') {
        params.append('provider', filters.provider);
      }
      if (filters?.gender && filters.gender !== 'all') {
        params.append('gender', filters.gender);
      }
      if (filters?.accent && filters.accent !== 'all') {
        params.append('accent', filters.accent);
      }
      // Include user_id and include_custom to fetch ElevenLabs voices from user's account
      if (currentUserId) {
        params.append('user_id', currentUserId);
        params.append('include_custom', 'true');
      }

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai'}/api/voices/list?${params.toString()}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch voices');
      }

      const data: VoiceListResponse = await response.json();
      setVoices(data.voices);
      setError(null);
    } catch (err) {
      console.error('Error fetching voices:', err);
      setError('Failed to load voices. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const fetchSavedVoices = async (uid: string) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai'}/api/voices/preferences/${uid}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch saved voices');
      }

      const data = await response.json();
      setSavedVoices(data.saved_voices || []);
    } catch (err) {
      console.error('Error fetching saved voices:', err);
    }
  };

  const isVoiceSaved = (voiceId: string, provider: string): boolean => {
    return savedVoices.some(v => v.id === voiceId && v.provider === provider);
  };

  const handleSaveVoice = async (voice: Voice) => {
    if (!userId) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai'}/api/voices/preferences/${userId}/save`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            voice_id: voice.id,
            provider: voice.provider,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to save voice');
      }

      // Refresh saved voices
      await fetchSavedVoices(userId);
    } catch (err) {
      console.error('Error saving voice:', err);
      alert('Failed to save voice. Please try again.');
    }
  };

  const handleRemoveVoice = async (voice: Voice) => {
    if (!userId) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai'}/api/voices/preferences/${userId}/remove`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            voice_id: voice.id,
            provider: voice.provider,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to remove voice');
      }

      // Refresh saved voices
      await fetchSavedVoices(userId);
    } catch (err) {
      console.error('Error removing voice:', err);
      alert('Failed to remove voice. Please try again.');
    }
  };

  const handlePlayVoice = async (voice: Voice) => {
    if (!userId) return;

    // Stop current audio if playing
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    // If already playing this voice, stop it
    if (currentlyPlaying === voice.id) {
      setCurrentlyPlaying(null);
      return;
    }

    try {
      setCurrentlyPlaying(voice.id);
      const token = localStorage.getItem('token');

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai'}/api/voices/demo`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            voice_id: voice.id,
            provider: voice.provider,
            user_id: userId,
            text: `This is the text you can play using ${voice.name}. Experience the natural tone and clarity.`,
            model: voice.model,
          }),
        }
      );

      if (!response.ok) {
        let errorMessage = 'Failed to generate voice demo';
        try {
          const errorData = await response.json();
          errorMessage = errorData?.detail || errorData?.message || errorMessage;
        } catch {
          // Fallback to status text if JSON parse fails
          errorMessage = response.statusText || errorMessage;
        }

        // Provide clearer guidance based on provider/key issues
        if (voice.provider === 'openai' && errorMessage.toLowerCase().includes('no openai api key')) {
          errorMessage = 'Please add an OpenAI TTS API key in Settings (Custom Provider) or add OPENAI_API_KEY to .env.';
        } else if (voice.provider === 'cartesia' && response.status >= 500) {
          errorMessage = 'Cartesia demo failed (500). Please verify your Cartesia API key in Settings (.env fallback) and try again.';
        }

        throw new Error(errorMessage);
      }

      // Create audio from blob
      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);

      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      audio.onended = () => {
        setCurrentlyPlaying(null);
        URL.revokeObjectURL(audioUrl);
      };

      audio.onerror = () => {
        setCurrentlyPlaying(null);
        URL.revokeObjectURL(audioUrl);
        alert('Failed to play audio. Please try again.');
      };

      await audio.play();
    } catch (err) {
      console.error('Error playing voice:', err);
      setCurrentlyPlaying(null);
      alert(err instanceof Error ? err.message : 'Failed to play voice demo. Please try again.');
    }
  };

  const handleSyncElevenLabsVoices = async () => {
    if (!userId) return;

    try {
      setIsSyncingVoices(true);
      setSyncMessage(null);

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai'}/api/voices/elevenlabs/sync?user_id=${userId}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to sync voices');
      }

      const data = await response.json();

      if (data.success) {
        setSyncMessage({
          type: 'success',
          text: `Successfully synced ${data.total} voices from ElevenLabs`
        });
        // Refresh the voices list to show the synced voices
        await fetchVoices({
          provider: selectedProvider !== 'all' ? selectedProvider : undefined,
          gender: selectedGender !== 'all' ? selectedGender : undefined,
          accent: selectedAccent !== 'all' ? selectedAccent : undefined,
        });
      }
    } catch (err) {
      console.error('Error syncing ElevenLabs voices:', err);
      setSyncMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to sync voices. Please check your ElevenLabs API key in Settings.'
      });
    } finally {
      setIsSyncingVoices(false);
      // Clear message after 5 seconds
      setTimeout(() => setSyncMessage(null), 5000);
    }
  };

  // Apply filters
  useEffect(() => {
    fetchVoices({
      provider: selectedProvider !== 'all' ? selectedProvider : undefined,
      gender: selectedGender !== 'all' ? selectedGender : undefined,
      accent: selectedAccent !== 'all' ? selectedAccent : undefined,
    });
  }, [selectedProvider, selectedGender, selectedAccent]);

  // Get filtered voices
  const filteredVoices = voices.filter(voice => {
    if (showOnlySaved && !isVoiceSaved(voice.id, voice.provider)) {
      return false;
    }
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        voice.name.toLowerCase().includes(query) ||
        voice.description?.toLowerCase().includes(query) ||
        voice.provider.toLowerCase().includes(query) ||
        voice.accent.toLowerCase().includes(query)
      );
    }
    return true;
  });

  // Get unique accents for filter
  const uniqueAccents = Array.from(new Set(voices.map(v => v.accent)));

  // Navigation
  const navigationItems = NAV_ITEMS;

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
    localStorage.removeItem('isAdmin');
    router.push('/login');
  };

  const toggleTheme = () => {
    const newTheme = !isDarkMode;
    setIsDarkMode(newTheme);
    localStorage.setItem('theme', newTheme ? 'dark' : 'light');
  };

  // User info for TopBar (mirror dashboard logic)
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
    if (candidates.length === 0) return 'User';
    const primary = candidates[0];
    if (primary.includes('@')) {
      return primary.split('@')[0];
    }
    return primary.split(' ')[0];
  }, [user]);

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

        {/* Page Content */}
        <main className="p-6">
          <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className={`text-4xl font-bold mb-2 ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                Voice Lab
              </h1>
              <p className={isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}>
                Explore and test voices from all TTS providers. Find the perfect voice for your AI agents.
              </p>
            </div>
            <button
              onClick={handleSyncElevenLabsVoices}
              disabled={isSyncingVoices}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium transition-all ${
                isSyncingVoices
                  ? 'bg-blue-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 shadow-sm hover:shadow-md'
              } text-white`}
            >
              {isSyncingVoices ? (
                <>
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Syncing...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Sync ElevenLabs Voices
                </>
              )}
            </button>
          </div>

          {/* Sync Message */}
          {syncMessage && (
            <div className={`mt-4 p-4 rounded-lg ${
              syncMessage.type === 'success'
                ? 'bg-primary/10 border border-primary/20 text-primary'
                : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-400'
            }`}>
              <div className="flex items-center gap-2">
                {syncMessage.type === 'success' ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                )}
                <span className="text-sm font-medium">{syncMessage.text}</span>
              </div>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className={`rounded-xl shadow-sm p-6 mb-6 ${isDarkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-100'}`}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            {/* Provider Filter */}
            <div>
              <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                Provider
              </label>
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value)}
                className={`w-full px-4 py-2 rounded-lg border focus:ring-2 focus:ring-primary focus:border-primary transition-colors ${
                  isDarkMode
                    ? 'bg-gray-700 border-gray-600 text-white'
                    : 'bg-white border-gray-300 text-neutral-dark'
                }`}
              >
                <option value="all">All Providers</option>
                <option value="cartesia">Cartesia (Ultra-Fast)</option>
                <option value="elevenlabs">ElevenLabs (High Quality)</option>
                <option value="openai">OpenAI (Balanced)</option>
                <option value="sarvam">Sarvam (Indian Languages)</option>
              </select>
            </div>

            {/* Gender Filter */}
            <div>
              <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                Gender
              </label>
              <select
                value={selectedGender}
                onChange={(e) => setSelectedGender(e.target.value)}
                className={`w-full px-4 py-2 rounded-lg border focus:ring-2 focus:ring-primary focus:border-primary transition-colors ${
                  isDarkMode
                    ? 'bg-gray-700 border-gray-600 text-white'
                    : 'bg-white border-gray-300 text-neutral-dark'
                }`}
              >
                <option value="all">All Genders</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="neutral">Neutral</option>
              </select>
            </div>

            {/* Accent Filter */}
            <div>
              <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                Accent
              </label>
              <select
                value={selectedAccent}
                onChange={(e) => setSelectedAccent(e.target.value)}
                className={`w-full px-4 py-2 rounded-lg border focus:ring-2 focus:ring-primary focus:border-primary transition-colors ${
                  isDarkMode
                    ? 'bg-gray-700 border-gray-600 text-white'
                    : 'bg-white border-gray-300 text-neutral-dark'
                }`}
              >
                <option value="all">All Accents</option>
                {uniqueAccents.map(accent => (
                  <option key={accent} value={accent}>{accent}</option>
                ))}
              </select>
            </div>

            {/* Search */}
            <div>
              <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                Search
              </label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search voices..."
                className={`w-full px-4 py-2 rounded-lg border focus:ring-2 focus:ring-primary focus:border-primary transition-colors ${
                  isDarkMode
                    ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                    : 'bg-white border-gray-300 text-neutral-dark placeholder-gray-400'
                }`}
              />
            </div>
          </div>

          {/* Show Only Saved Toggle */}
          <div className="flex items-center">
            <input
              type="checkbox"
              id="showOnlySaved"
              checked={showOnlySaved}
              onChange={(e) => setShowOnlySaved(e.target.checked)}
              className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
            />
            <label htmlFor="showOnlySaved" className={`ml-2 text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
              Show only saved voices ({savedVoices.length})
            </label>
          </div>
        </div>

        {/* Results Count */}
        <div className="mb-4">
          <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
            Showing {filteredVoices.length} of {voices.length} voices
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
            <p className="text-red-800 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex justify-center items-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
          </div>
        )}

        {/* Voices Grid */}
        {!loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredVoices.map((voice) => {
              const isSaved = isVoiceSaved(voice.id, voice.provider);
              const isPlaying = currentlyPlaying === voice.id;
                const colors = providerColors[voice.provider] || defaultProviderColors;

              return (
                <div
                  key={`${voice.provider}-${voice.id}`}
                  className={`flex flex-col h-[280px] rounded-xl shadow-sm border-2 p-5 hover:shadow-md transition-all duration-200 ${
                    isDarkMode
                      ? isSaved
                        ? 'bg-gray-800 border-primary'
                        : 'bg-gray-800 border-gray-700 hover:border-gray-600'
                      : isSaved
                      ? 'bg-white border-primary'
                      : 'bg-white border-gray-200 hover:border-gray-300'
                  }`}
                >
                  {/* Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className={`text-base font-semibold truncate ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`} title={voice.name}>
                          {voice.name}
                        </h3>
                        <span className="text-base flex-shrink-0">{genderIcons[voice.gender]}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
                          {voice.provider.charAt(0).toUpperCase() + voice.provider.slice(1)}
                        </span>
                        <span className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                          {voice.accent}
                        </span>
                      </div>
                    </div>

                    {/* Save Button */}
                    <button
                      onClick={() => isSaved ? handleRemoveVoice(voice) : handleSaveVoice(voice)}
                      className={`p-1.5 rounded-lg transition-colors flex-shrink-0 ${
                        isSaved
                          ? 'text-primary bg-primary/10 hover:bg-primary/20'
                          : isDarkMode
                          ? 'text-gray-400 hover:text-primary hover:bg-primary/10'
                          : 'text-gray-400 hover:text-primary hover:bg-primary/10'
                      }`}
                      title={isSaved ? 'Remove from saved' : 'Save voice'}
                    >
                      {isSaved ? (
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                        </svg>
                      )}
                    </button>
                  </div>

                  {/* Description - Fixed height area */}
                  <div className="flex-1 min-h-0 mb-3">
                    {voice.description ? (
                      <p className={`text-sm line-clamp-2 ${isDarkMode ? 'text-gray-300' : 'text-neutral-mid'}`} title={voice.description}>
                        {voice.description}
                      </p>
                    ) : (
                      <p className={`text-sm ${isDarkMode ? 'text-gray-500' : 'text-gray-400'}`}>
                        {voice.provider.charAt(0).toUpperCase() + voice.provider.slice(1)} voice
                      </p>
                    )}
                  </div>

                  {/* Metadata - Fixed height */}
                  <div className="flex flex-wrap gap-1.5 mb-3 h-[26px] overflow-hidden">
                    {voice.age_group && (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs ${
                        isDarkMode ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-neutral-dark'
                      }`}>
                        {voice.age_group}
                      </span>
                    )}
                    {voice.use_case && (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs ${
                        isDarkMode ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-neutral-dark'
                      }`}>
                        {voice.use_case}
                      </span>
                    )}
                  </div>

                  {/* Play Button - Always at bottom */}
                  <button
                    onClick={() => handlePlayVoice(voice)}
                    disabled={isPlaying}
                    className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium transition-all ${
                      isPlaying
                        ? isDarkMode
                          ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                          : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'bg-primary text-white hover:bg-primary/90 shadow-sm'
                    }`}
                  >
                    {isPlaying ? (
                      <>
                        <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Playing...
                      </>
                    ) : (
                      <>
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" />
                        </svg>
                        Play Demo
                      </>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Empty State */}
        {!loading && filteredVoices.length === 0 && (
          <div className="text-center py-20">
            <svg
              className={`mx-auto h-12 w-12 ${isDarkMode ? 'text-gray-600' : 'text-gray-400'}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
            <h3 className={`mt-2 text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
              No voices found
            </h3>
            <p className={`mt-1 text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
              Try adjusting your filters or search query.
            </p>
          </div>
        )}
          </div>
        </main>
      </div>
    </div>
  );
}
