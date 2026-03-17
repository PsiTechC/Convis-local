'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Image from 'next/image';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import { NAV_ITEMS, NavigationItem } from '../components/Navigation';
import { TopBar } from '../components/TopBar';

interface User {
  id?: string;
  _id?: string;
  clientId?: string;
  email: string;
  companyName?: string;
  phoneNumber?: string;
  name?: string;
  fullName?: string;
  full_name?: string;
  firstName?: string;
  username?: string;
}

function getUserInitials(name?: string, email?: string): string {
  if (name?.trim()) {
    const parts = name.trim().split(/\s+/).slice(0, 2);
    const initials = parts.map((part) => part[0]?.toUpperCase()).join('');
    if (initials) {
      return initials;
    }
  }
  if (email?.trim()) {
    return email.trim()[0]?.toUpperCase() || 'U';
  }
  return 'U';
}

export default function SettingsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'profile' | 'password' | 'integrations'>('profile');
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  // Profile form data
  const [profileData, setProfileData] = useState({
    companyName: '',
    email: '',
    phoneNumber: '',
  });

  // Password form data
  const [passwordData, setPasswordData] = useState({
    newPassword: '',
    confirmPassword: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');

    if (!storedToken) {
      router.push('/login');
      return;
    }

    setToken(storedToken);

    if (userStr) {
      const userData = JSON.parse(userStr);
      setUser(userData);
      setProfileData({
        companyName: userData.companyName || '',
        email: userData.email || '',
        phoneNumber: userData.phoneNumber || '',
      });
    }

    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
      setIsDarkMode(true);
    }
  }, [router]);

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
    if (navItem.href) {
      router.push(navItem.href);
    }
  };

  const navigationItems = useMemo(() => NAV_ITEMS, []);
  const userInitial = useMemo(() => getUserInitials(user?.companyName || user?.fullName || user?.name, user?.email), [user]);
  const userGreeting = useMemo(() => {
    const candidates = [
      user?.firstName,
      user?.fullName,
      user?.name,
      user?.username,
      user?.email,
      user?.companyName,
    ].filter((value) => typeof value === 'string' && value.trim().length > 0) as string[];

    if (candidates.length === 0) return undefined;
    const preferred = candidates[0];
    if (preferred.includes('@')) {
      return preferred.split('@')[0];
    }
    return preferred.split(' ')[0];
  }, [user]);


  const userInitials = getUserInitials(profileData.companyName, profileData.email);
  const companyDisplayName = profileData.companyName?.trim() || 'Your company name';
  const emailDisplay = profileData.email || 'Add email address';
  const phoneDisplay = profileData.phoneNumber || 'Add phone number';

  const handleProfileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setProfileData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setPasswordData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const validateProfileForm = () => {
    const newErrors: Record<string, string> = {};

    if (!profileData.companyName.trim()) {
      newErrors.companyName = 'Company name is required';
    }

    if (!profileData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(profileData.email)) {
      newErrors.email = 'Email is invalid';
    }

    if (!profileData.phoneNumber.trim()) {
      newErrors.phoneNumber = 'Phone number is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const validatePasswordForm = () => {
    const newErrors: Record<string, string> = {};

    if (!passwordData.newPassword) {
      newErrors.newPassword = 'New password is required';
    } else if (passwordData.newPassword.length < 6) {
      newErrors.newPassword = 'Password must be at least 6 characters';
    }

    if (!passwordData.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (passwordData.newPassword !== passwordData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMessage('');
    setErrors({});

    if (!validateProfileForm()) {
      return;
    }

    setIsLoading(true);

    try {
      const token = localStorage.getItem('token');
      const userId = user?.id || user?._id || user?.clientId;

      const response = await fetch(`${API_URL}/api/users/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          companyName: profileData.companyName,
          email: profileData.email,
          phoneNumber: profileData.phoneNumber,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update profile');
      }

      const _updatedUser = await response.json();

      // Update local storage
      const updatedUserData = { ...user, ...profileData };
      localStorage.setItem('user', JSON.stringify(updatedUserData));
      setUser(updatedUserData);

      setSuccessMessage('Profile updated successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error) {
      if (error instanceof Error) {
        setErrors({ submit: error.message });
      } else {
        setErrors({ submit: 'Failed to update profile. Please try again.' });
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMessage('');
    setErrors({});

    if (!validatePasswordForm()) {
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/forgot_password/reset-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: user?.email,
          newPassword: passwordData.newPassword,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update password');
      }

      setSuccessMessage('Password changed successfully!');
      setPasswordData({ newPassword: '', confirmPassword: '' });
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error) {
      if (error instanceof Error) {
        setErrors({ submit: error.message });
      } else {
        setErrors({ submit: 'Failed to change password. Please try again.' });
      }
    } finally {
      setIsLoading(false);
    }
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
                    className={`w-full flex items-center gap-3 ${isSidebarCollapsed ? 'px-3 justify-center' : 'px-4'} py-3 rounded-xl transition-all duration-200 group ${
                      item.name === 'Settings' || isCurrentPageInSubItems
                        ? `${isDarkMode ? 'bg-gray-700 text-white' : 'bg-primary/10 text-primary'} font-medium`
                        : `${isDarkMode ? 'text-gray-400 hover:bg-gray-700 hover:text-white' : 'text-neutral-mid hover:bg-neutral-light hover:text-primary'}`
                    }`}
                  >
                    <svg className="w-6 h-6 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      {item.icon}
                    </svg>
                    {!isSidebarCollapsed && (
                      <>
                        <span className="whitespace-nowrap flex-1 text-left">{item.name}</span>
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

          {/* Logout Button */}
          <div className="p-4 border-t border-neutral-mid/10">
            <button
              onClick={handleLogout}
              className={`w-full flex items-center ${isSidebarCollapsed ? 'justify-center' : 'justify-start'} ${isSidebarCollapsed ? 'px-3' : 'px-4'} py-3 rounded-xl transition-all duration-200 ${isDarkMode ? 'text-red-400 hover:bg-red-500/10' : 'text-red-600 hover:bg-red-50'}`}
            >
              <svg className={`w-6 h-6 flex-shrink-0 ${isSidebarCollapsed ? '' : 'mr-3'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              {!isSidebarCollapsed && <span>Logout</span>}
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className={`${isSidebarCollapsed ? 'lg:ml-20' : 'lg:ml-20'} transition-all duration-300`}>
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
        <main className="px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-6xl space-y-6">
            <header>
              <h1 className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>Settings</h1>
              <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} mt-1`}>Update your workspace preferences, billing details, and integrations.</p>
            </header>

            <section className={`overflow-hidden rounded-3xl border shadow-xl ${isDarkMode ? 'bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 border-gray-700/70' : 'bg-gradient-to-r from-primary/10 via-white to-primary/5 border-primary/10'}`}>
              <div className="grid items-center gap-8 p-6 sm:p-8 lg:p-10 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="space-y-4">
                  <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wide ${isDarkMode ? 'bg-primary/20 text-primary/80' : 'bg-primary/10 text-primary'}`}>
                    Account Snapshot
                  </span>
                  <h2 className={`text-3xl font-bold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                    Customize your Convis experience
                  </h2>
                  <p className={`${isDarkMode ? 'text-gray-300' : 'text-neutral-mid'} max-w-xl`}>
                    Keep your workspace information, preferences, and security details current. All updates sync instantly across your team.
                  </p>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className={`rounded-2xl border px-4 py-3 backdrop-blur ${isDarkMode ? 'border-gray-700/70 bg-gray-900/60 text-gray-200' : 'border-white/70 bg-white/80 text-neutral-dark shadow-sm'}`}>
                      <p className="text-xs uppercase tracking-wide opacity-70">Email</p>
                      <p className="font-semibold truncate">{emailDisplay}</p>
                    </div>
                    <div className={`rounded-2xl border px-4 py-3 backdrop-blur ${isDarkMode ? 'border-gray-700/70 bg-gray-900/60 text-gray-200' : 'border-white/70 bg-white/80 text-neutral-dark shadow-sm'}`}>
                      <p className="text-xs uppercase tracking-wide opacity-70">Phone</p>
                      <p className="font-semibold truncate">{phoneDisplay}</p>
                    </div>
                  </div>
                </div>
                <div className="relative h-48 sm:h-52 lg:h-60">
                  <div className={`absolute inset-0 rounded-[28px] ${isDarkMode ? 'bg-primary/15' : 'bg-white/70'} backdrop-blur-sm`} />
                  <Image
                    src="/window.svg"
                    alt="Settings illustration"
                    fill
                    priority
                    className="object-contain p-6"
                  />
                </div>
              </div>
            </section>

            {successMessage && (
              <div className={`border rounded-2xl p-4 ${isDarkMode ? 'bg-green-900/40 border-green-700' : 'bg-green-50 border-green-200'}`}>
                <div className="flex items-center gap-2">
                  <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  <p className="text-sm font-medium">{successMessage}</p>
                </div>
              </div>
            )}

            {errors.submit && (
              <div className={`border rounded-2xl p-4 ${isDarkMode ? 'bg-red-900/40 border-red-700' : 'bg-red-50 border-red-200'}`}>
                <div className="flex items-center gap-2">
                  <svg className="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                  <p className="text-sm font-medium">{errors.submit}</p>
                </div>
              </div>
            )}

            <div className={`${isDarkMode ? 'bg-gray-800/90 border-gray-700' : 'bg-white border-neutral-mid/10'} border rounded-3xl shadow-xl overflow-hidden`}>
              <div className="grid gap-0 lg:grid-cols-[320px_1fr]">
                <aside className={`p-6 sm:p-8 space-y-6 ${isDarkMode ? 'bg-gray-900/40 border-b border-gray-700/70 lg:border-b-0 lg:border-r' : 'bg-gradient-to-b from-primary/5 via-white to-white border-b border-neutral-mid/10 lg:border-b-0 lg:border-r'}`}>
                  <div className="flex flex-col items-center gap-5 text-center lg:items-start lg:text-left">
                    <div className={`w-24 h-24 rounded-3xl flex items-center justify-center text-2xl font-semibold ${isDarkMode ? 'bg-primary/20 text-primary/80 border border-primary/40' : 'bg-primary/10 text-primary border border-primary/20'}`}>
                      {userInitials}
                    </div>
                    <div className="space-y-1">
                      <h3 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>
                        {companyDisplayName}
                      </h3>
                      <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>{emailDisplay}</p>
                    </div>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <h4 className={`text-xs font-semibold uppercase tracking-wide ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                        Account Details
                      </h4>
                      <ul className="mt-3 space-y-3">
                        <li className={`flex items-center gap-3 text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                          <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${isDarkMode ? 'bg-gray-800 text-primary' : 'bg-primary/10 text-primary'}`}>
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l9 6 9-6M5 5h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z" />
                            </svg>
                          </span>
                          <span className="truncate">{emailDisplay}</span>
                        </li>
                        <li className={`flex items-center gap-3 text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'}`}>
                          <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${isDarkMode ? 'bg-gray-800 text-primary' : 'bg-primary/10 text-primary'}`}>
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2 5a2 2 0 012-2h1.28a1 1 0 01.948.684l1.284 3.853a1 1 0 01-.502 1.21l-1.607.804a11.042 11.042 0 006.236 6.236l.804-1.607a1 1 0 011.21-.502l3.853 1.284a1 1 0 01.684.948V20a2 2 0 01-2 2h-1C7.82 22 2 16.18 2 9V7a2 2 0 012-2z" />
                            </svg>
                          </span>
                          <span className="truncate">{phoneDisplay}</span>
                        </li>
                      </ul>
                    </div>
                    <div className={`${isDarkMode ? 'border border-gray-700/80 bg-gray-900/50' : 'border border-primary/20 bg-primary/10'} rounded-2xl p-4`}>
                      <p className={`text-xs leading-relaxed ${isDarkMode ? 'text-gray-300' : 'text-primary/90'}`}>
                        Pro tip: Keep your contact details accurate so notifications and billing updates always reach you.
                      </p>
                    </div>
                  </div>
                </aside>
                <div className="flex flex-col">
                  <div className={`flex flex-col sm:flex-row border-b ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'}`}>
                    <button
                      onClick={() => setActiveTab('profile')}
                      className={`flex-1 px-6 py-4 text-sm font-medium transition-colors ${activeTab === 'profile'
                        ? `${isDarkMode ? 'text-primary bg-gray-800 border-b-2 border-primary' : 'text-primary bg-primary/5 border-b-2 border-primary'}`
                        : `${isDarkMode ? 'text-gray-400 hover:text-white hover:bg-gray-800/80' : 'text-neutral-mid hover:text-neutral-dark hover:bg-neutral-light/60'}`}`}
                    >
                      Profile Information
                    </button>
                    <button
                      onClick={() => setActiveTab('password')}
                      className={`flex-1 px-6 py-4 text-sm font-medium transition-colors ${activeTab === 'password'
                        ? `${isDarkMode ? 'text-primary bg-gray-800 border-b-2 border-primary' : 'text-primary bg-primary/5 border-b-2 border-primary'}`
                        : `${isDarkMode ? 'text-gray-400 hover:text-white hover:bg-gray-800/80' : 'text-neutral-mid hover:text-neutral-dark hover:bg-neutral-light/60'}`}`}
                    >
                      Change Password
                    </button>
                    <button
                      onClick={() => router.push('/settings/integrations')}
                      className={`flex-1 px-6 py-4 text-sm font-medium transition-colors ${activeTab === 'integrations'
                        ? `${isDarkMode ? 'text-primary bg-gray-800 border-b-2 border-primary' : 'text-primary bg-primary/5 border-b-2 border-primary'}`
                        : `${isDarkMode ? 'text-gray-400 hover:text-white hover:bg-gray-800/80' : 'text-neutral-mid hover:text-neutral-dark hover:bg-neutral-light/60'}`}`}
                    >
                      🔗 Integrations
                    </button>
                  </div>
                  <div className="p-6 sm:p-8">
                    {activeTab === 'profile' && (
                      <form onSubmit={handleProfileSubmit} className="space-y-6">
                        <div>
                          <label htmlFor="companyName" className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'} mb-2`}>
                            Company Name
                          </label>
                          <input
                            type="text"
                            id="companyName"
                            name="companyName"
                            value={profileData.companyName}
                            onChange={handleProfileChange}
                            className={`w-full px-4 py-3 rounded-xl border ${errors.companyName
                              ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                              : `${isDarkMode ? 'border-gray-600 bg-gray-700 text-white' : 'border-neutral-mid/20 bg-white'} focus:border-primary focus:ring-2 focus:ring-primary/10`
                            } focus:outline-none transition-all duration-200`}
                            placeholder="Your company name"
                          />
                          {errors.companyName && (
                            <p className="mt-1.5 text-xs text-red-600">{errors.companyName}</p>
                          )}
                        </div>

                        <div>
                          <label htmlFor="email" className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'} mb-2`}>
                            Email Address
                          </label>
                          <input
                            type="email"
                            id="email"
                            name="email"
                            value={profileData.email}
                            onChange={handleProfileChange}
                            className={`w-full px-4 py-3 rounded-xl border ${errors.email
                              ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                              : `${isDarkMode ? 'border-gray-600 bg-gray-700 text-white' : 'border-neutral-mid/20 bg-white'} focus:border-primary focus:ring-2 focus:ring-primary/10`
                            } focus:outline-none transition-all duration-200`}
                            placeholder="your@email.com"
                          />
                          {errors.email && (
                            <p className="mt-1.5 text-xs text-red-600">{errors.email}</p>
                          )}
                        </div>

                        <div>
                          <label htmlFor="phoneNumber" className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'} mb-2`}>
                            Phone Number
                          </label>
                          <input
                            type="tel"
                            id="phoneNumber"
                            name="phoneNumber"
                            value={profileData.phoneNumber}
                            onChange={handleProfileChange}
                            className={`w-full px-4 py-3 rounded-xl border ${errors.phoneNumber
                              ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                              : `${isDarkMode ? 'border-gray-600 bg-gray-700 text-white' : 'border-neutral-mid/20 bg-white'} focus:border-primary focus:ring-2 focus:ring-primary/10`
                            } focus:outline-none transition-all duration-200`}
                            placeholder="+1 (555) 000-0000"
                          />
                          {errors.phoneNumber && (
                            <p className="mt-1.5 text-xs text-red-600">{errors.phoneNumber}</p>
                          )}
                        </div>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="w-full bg-gradient-to-r from-primary to-primary/90 text-white py-3.5 px-6 rounded-xl font-semibold hover:shadow-xl hover:shadow-primary/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isLoading ? (
                            <span className="flex items-center justify-center gap-2">
                              <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                              Updating...
                            </span>
                          ) : (
                            'Update Profile'
                          )}
                        </button>
                      </form>
                    )}

                    {activeTab === 'password' && (
                      <form onSubmit={handlePasswordSubmit} className="space-y-6">
                        <div>
                          <label htmlFor="newPassword" className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'} mb-2`}>
                            New Password
                          </label>
                          <div className="relative">
                            <input
                              type={showNewPassword ? 'text' : 'password'}
                              id="newPassword"
                              name="newPassword"
                              value={passwordData.newPassword}
                              onChange={handlePasswordChange}
                              className={`w-full px-4 py-3 rounded-xl border ${errors.newPassword
                                ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                                : `${isDarkMode ? 'border-gray-600 bg-gray-700 text-white' : 'border-neutral-mid/20 bg-white'} focus:border-primary focus:ring-2 focus:ring-primary/10`
                              } focus:outline-none transition-all duration-200 pr-11`}
                              placeholder="Enter new password"
                            />
                            <button
                              type="button"
                              onClick={() => setShowNewPassword(!showNewPassword)}
                              className={`absolute right-3 top-1/2 -translate-y-1/2 ${isDarkMode ? 'text-gray-400 hover:text-white' : 'text-neutral-mid hover:text-primary'} transition-colors p-1.5 rounded-lg hover:bg-primary/5`}
                            >
                              {showNewPassword ? (
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                                </svg>
                              ) : (
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                              )}
                            </button>
                          </div>
                          {errors.newPassword && (
                            <p className="mt-1.5 text-xs text-red-600">{errors.newPassword}</p>
                          )}
                        </div>

                        <div>
                          <label htmlFor="confirmPassword" className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-neutral-dark'} mb-2`}>
                            Confirm New Password
                          </label>
                          <div className="relative">
                            <input
                              type={showConfirmPassword ? 'text' : 'password'}
                              id="confirmPassword"
                              name="confirmPassword"
                              value={passwordData.confirmPassword}
                              onChange={handlePasswordChange}
                              className={`w-full px-4 py-3 rounded-xl border ${errors.confirmPassword
                                ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                                : `${isDarkMode ? 'border-gray-600 bg-gray-700 text-white' : 'border-neutral-mid/20 bg-white'} focus:border-primary focus:ring-2 focus:ring-primary/10`
                              } focus:outline-none transition-all duration-200 pr-11`}
                              placeholder="Confirm new password"
                            />
                            <button
                              type="button"
                              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                              className={`absolute right-3 top-1/2 -translate-y-1/2 ${isDarkMode ? 'text-gray-400 hover:text-white' : 'text-neutral-mid hover:text-primary'} transition-colors p-1.5 rounded-lg hover:bg-primary/5`}
                            >
                              {showConfirmPassword ? (
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                                </svg>
                              ) : (
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                              )}
                            </button>
                          </div>
                          {errors.confirmPassword && (
                            <p className="mt-1.5 text-xs text-red-600">{errors.confirmPassword}</p>
                          )}
                        </div>

                        <div className={`p-4 rounded-xl ${isDarkMode ? 'bg-gray-700/50' : 'bg-blue-50'} border ${isDarkMode ? 'border-gray-600' : 'border-blue-100'}`}>
                          <p className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-blue-800'}`}>
                            <strong>Note:</strong> Your password must be at least 6 characters long.
                          </p>
                        </div>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="w-full bg-gradient-to-r from-primary to-primary/90 text-white py-3.5 px-6 rounded-xl font-semibold hover:shadow-xl hover:shadow-primary/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isLoading ? (
                            <span className="flex items-center justify-center gap-2">
                              <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                              Changing Password...
                            </span>
                          ) : (
                            'Change Password'
                          )}
                        </button>
                      </form>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
