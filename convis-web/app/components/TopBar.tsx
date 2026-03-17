'use client';

import { ReactNode, useState, useRef, useEffect } from 'react';
import { NotificationDropdown } from './NotificationDropdown';

interface TopBarProps {
  isDarkMode: boolean;
  toggleTheme?: () => void;
  onToggleTheme?: () => void;
  onLogout?: () => void;
  userInitial?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  user?: any;
  isSidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
  userLabel?: string;
  onToggleMobileMenu?: () => void;
  searchPlaceholder?: string;
  showSearch?: boolean;
  collapseSearchOnMobile?: boolean;
  leftContent?: ReactNode;
  rightContentBefore?: ReactNode;
  rightContentAfter?: ReactNode;
  showNotifications?: boolean;
  currency?: 'USD' | 'INR';
  onCurrencyToggle?: () => void;
  token?: string;
}

export function TopBar({
  isDarkMode,
  toggleTheme,
  onToggleTheme,
  onLogout,
  userInitial,
  user,
  isSidebarCollapsed: _isSidebarCollapsed,
  onToggleSidebar: _onToggleSidebar,
  userLabel,
  onToggleMobileMenu,
  searchPlaceholder = 'Search for article, video or document',
  showSearch = true,
  collapseSearchOnMobile = false,
  leftContent,
  rightContentBefore,
  rightContentAfter,
  showNotifications = true,
  currency = 'USD',
  onCurrencyToggle,
  token,
}: TopBarProps) {
  // State for dropdown and confirmation
  const [showDropdown, setShowDropdown] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Support both toggleTheme and onToggleTheme prop names
  const handleToggleTheme = toggleTheme || onToggleTheme || (() => {});

  // Derive userInitial from user if not provided
  const displayInitial = userInitial || (user?.email ? user.email.charAt(0).toUpperCase() : 'U');
  const displayLabel = userLabel || user?.name || user?.email?.split('@')[0];

  const searchWrapperClasses = collapseSearchOnMobile
    ? 'hidden sm:block flex-1 max-w-xl'
    : 'flex-1 max-w-xl';

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogoutClick = () => {
    setShowDropdown(false);
    setShowLogoutConfirm(true);
  };

  const confirmLogout = () => {
    setShowLogoutConfirm(false);
    onLogout?.();
  };

  return (
    <header className={`${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-neutral-mid/10'} border-b sticky top-0 z-30`}>
      <div className="flex items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {onToggleMobileMenu && (
            <button
              onClick={onToggleMobileMenu}
              className="lg:hidden p-2 rounded-lg hover:bg-neutral-light"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          )}

          {leftContent && (
            <div className="shrink-0">{leftContent}</div>
          )}

          {showSearch && (
            <div className={searchWrapperClasses}>
              <div className="relative">
                <input
                  type="text"
                  placeholder={searchPlaceholder}
                  className={`w-full pl-10 pr-4 py-2.5 rounded-xl ${isDarkMode ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-neutral-light border-neutral-mid/20 text-neutral-dark'} border focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all`}
                />
                <svg className={`w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {rightContentBefore}

          {onCurrencyToggle && (
            <button
              onClick={onCurrencyToggle}
              title={`Switch to ${currency === 'USD' ? 'INR' : 'USD'}`}
              className={`px-3 py-2 rounded-xl ${isDarkMode ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' : 'bg-neutral-light hover:bg-neutral-mid/20 text-neutral-dark'} transition-all font-semibold text-sm flex items-center gap-1.5`}
            >
              <span className="text-xs font-bold">{currency === 'USD' ? '$' : '₹'}</span>
              <span>{currency}</span>
            </button>
          )}

          <button
            onClick={handleToggleTheme}
            className={`p-2 rounded-xl ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-neutral-light'} transition-colors`}
          >
            {isDarkMode ? (
              <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-neutral-mid" fill="currentColor" viewBox="0 0 20 20">
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
            )}
          </button>

          {showNotifications && token && (
            <NotificationDropdown isDarkMode={isDarkMode} token={token} />
          )}

          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className={`flex items-center gap-2 p-2 rounded-xl ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-neutral-light'} transition-colors`}
            >
              {displayLabel && (
                <span className={`${isDarkMode ? 'text-gray-300' : 'text-dark/70'} text-sm font-medium hidden sm:block`}>
                  Hi, {displayLabel}
                </span>
              )}
              <div className="w-8 h-8 bg-gradient-to-br from-primary to-primary/80 rounded-full flex items-center justify-center">
                <span className="text-xs font-bold text-white">
                  {displayInitial}
                </span>
              </div>
              <svg
                className={`w-4 h-4 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'} transition-transform ${showDropdown ? 'rotate-180' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Dropdown Menu */}
            {showDropdown && (
              <div className={`absolute right-0 mt-2 w-48 rounded-xl shadow-lg ${isDarkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'} py-1 z-50`}>
                <button
                  onClick={handleLogoutClick}
                  className={`w-full px-4 py-2 text-left text-sm ${isDarkMode ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-700 hover:bg-gray-50'} transition-colors flex items-center gap-2`}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  Logout
                </button>
              </div>
            )}
          </div>

          {rightContentAfter}
        </div>
      </div>

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className={`max-w-sm w-full rounded-xl ${isDarkMode ? 'bg-gray-800' : 'bg-white'} p-6 shadow-2xl`}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h3 className={`text-lg font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Confirm Logout
              </h3>
            </div>
            <p className={`${isDarkMode ? 'text-gray-300' : 'text-gray-600'} mb-6`}>
              Are you sure you want to logout? You will need to login again to access your account.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowLogoutConfirm(false)}
                className={`flex-1 px-4 py-2 rounded-lg border transition-colors ${
                  isDarkMode
                    ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                Cancel
              </button>
              <button
                onClick={confirmLogout}
                className="flex-1 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white transition-colors font-medium"
              >
                Yes, Logout
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
