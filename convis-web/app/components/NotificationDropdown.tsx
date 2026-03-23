'use client';

import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Debug: Log API URL on component load
if (typeof window !== 'undefined') {
  console.log('[NotificationDropdown] API_BASE_URL:', API_BASE_URL);
}

interface Notification {
  id: string;
  type: string;
  priority: string;
  title: string;
  message: string;
  related_id?: string;
  related_type?: string;
  action_label?: string;
  action_url?: string;
  is_read: boolean;
  read_at?: string;
  created_at: string;
}

interface NotificationDropdownProps {
  isDarkMode: boolean;
  token: string;
}

export function NotificationDropdown({ isDarkMode, token }: NotificationDropdownProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

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

  // Fetch unread count on mount and periodically
  useEffect(() => {
    if (!token) return;

    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000); // Every 30 seconds
    return () => clearInterval(interval);
  }, [token]);

  // Fetch notifications when dropdown is opened
  useEffect(() => {
    if (showDropdown) {
      fetchNotifications();
    }
  }, [showDropdown, showUnreadOnly]);

  const fetchUnreadCount = async () => {
    if (!token) {
      console.log('[NotificationDropdown] Skipping fetch - no token');
      return;
    }

    try {
      console.log('[NotificationDropdown] Fetching unread count from:', `${API_BASE_URL}/api/notifications/unread-count`);
      const response = await axios.get(
        `${API_BASE_URL}/api/notifications/unread-count`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      console.log('[NotificationDropdown] Unread count response:', response.data);
      setUnreadCount(response.data.unread_count);
    } catch (error: any) {
      // More detailed error logging
      console.error('[NotificationDropdown] Fetch unread count error:', error);
      console.error('[NotificationDropdown] Error details:', {
        message: error?.message,
        code: error?.code,
        status: error?.response?.status,
        responseData: error?.response?.data,
        url: `${API_BASE_URL}/api/notifications/unread-count`,
        tokenPresent: !!token,
        tokenLength: token?.length
      });

      // Silently fail for network errors or auth issues
      if (error?.response?.status === 401) {
        console.warn('[NotificationDropdown] Authentication failed - token may be invalid or expired');
        // Don't show unread count badge if auth fails
        setUnreadCount(0);
      } else if (error?.code === 'ERR_NETWORK' || error?.message?.includes('Network')) {
        console.warn('[NotificationDropdown] Cannot connect to notifications API - check if backend is running');
      }
    }
  };

  const fetchNotifications = async () => {
    if (!token) return;

    setLoading(true);
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/notifications`,
        {
          params: {
            unread_only: showUnreadOnly,
            limit: 20
          },
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      setNotifications(response.data.notifications);
      setUnreadCount(response.data.unread_count);
    } catch (error: any) {
      // Handle errors gracefully
      if (error.response?.status === 401) {
        console.warn('Notification authentication failed');
      } else if (error.code === 'ERR_NETWORK') {
        console.warn('Cannot connect to notifications API');
      } else {
        console.error('Failed to fetch notifications:', error);
      }
    } finally {
      setLoading(false);
    }
  };

  const markAsRead = async (notificationId: string) => {
    try {
      await axios.put(
        `${API_BASE_URL}/api/notifications/${notificationId}/read`,
        {},
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      // Update local state
      setNotifications(prev =>
        prev.map(n =>
          n.id === notificationId ? { ...n, is_read: true, read_at: new Date().toISOString() } : n
        )
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (error) {
      console.error('Failed to mark notification as read:', error);
    }
  };

  const markAllAsRead = async () => {
    try {
      await axios.put(
        `${API_BASE_URL}/api/notifications/mark-all-read`,
        {},
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      // Update local state
      setNotifications(prev =>
        prev.map(n => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      setUnreadCount(0);
    } catch (error) {
      console.error('Failed to mark all as read:', error);
    }
  };

  const deleteNotification = async (notificationId: string) => {
    try {
      await axios.delete(
        `${API_BASE_URL}/api/notifications/${notificationId}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      // Update local state
      const notification = notifications.find(n => n.id === notificationId);
      if (notification && !notification.is_read) {
        setUnreadCount(prev => Math.max(0, prev - 1));
      }
      setNotifications(prev => prev.filter(n => n.id !== notificationId));
    } catch (error) {
      console.error('Failed to delete notification:', error);
    }
  };

  const handleNotificationClick = (notification: Notification) => {
    if (!notification.is_read) {
      markAsRead(notification.id);
    }

    if (notification.action_url) {
      window.location.href = notification.action_url;
    }
  };

  const _getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent': return 'text-red-600';
      case 'high': return 'text-orange-600';
      case 'medium': return 'text-yellow-600';
      case 'low': return 'text-blue-600';
      default: return 'text-gray-600';
    }
  };

  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case 'urgent': return '🚨';
      case 'high': return '⚠️';
      case 'medium': return 'ℹ️';
      case 'low': return '📌';
      default: return '📢';
    }
  };

  const formatTimeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className={`p-2 rounded-xl ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-neutral-light'} transition-colors relative`}
      >
        <svg className={`w-5 h-5 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white text-xs font-bold">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {showDropdown && (
        <div className={`absolute right-0 mt-2 w-96 max-h-[32rem] rounded-xl shadow-lg ${isDarkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'} z-50 flex flex-col`}>
          {/* Header */}
          <div className={`p-4 border-b ${isDarkMode ? 'border-gray-700' : 'border-gray-200'} flex items-center justify-between`}>
            <div>
              <h3 className={`text-lg font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Notifications
              </h3>
              {unreadCount > 0 && (
                <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  {unreadCount} unread
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowUnreadOnly(!showUnreadOnly)}
                className={`text-xs px-2 py-1 rounded ${
                  showUnreadOnly
                    ? 'bg-primary text-white'
                    : isDarkMode
                    ? 'bg-gray-700 text-gray-300'
                    : 'bg-gray-100 text-gray-700'
                }`}
              >
                {showUnreadOnly ? 'All' : 'Unread'}
              </button>
              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  className={`text-xs px-2 py-1 rounded ${isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                >
                  Mark all read
                </button>
              )}
            </div>
          </div>

          {/* Notifications List */}
          <div className="overflow-y-auto flex-1">
            {loading ? (
              <div className="p-8 text-center">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
              </div>
            ) : notifications.length === 0 ? (
              <div className="p-8 text-center">
                <svg className={`w-16 h-16 mx-auto ${isDarkMode ? 'text-gray-600' : 'text-gray-300'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <p className={`mt-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  {showUnreadOnly ? 'No unread notifications' : 'No notifications'}
                </p>
              </div>
            ) : (
              <div className="divide-y divide-gray-200 dark:divide-gray-700">
                {notifications.map(notification => (
                  <div
                    key={notification.id}
                    className={`p-4 hover:bg-opacity-50 transition-colors cursor-pointer ${
                      !notification.is_read
                        ? isDarkMode
                          ? 'bg-gray-700/50'
                          : 'bg-blue-50'
                        : ''
                    } ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="text-2xl flex-shrink-0">
                        {getPriorityIcon(notification.priority)}
                      </div>
                      <div className="flex-1 min-w-0" onClick={() => handleNotificationClick(notification)}>
                        <div className="flex items-start justify-between gap-2">
                          <h4 className={`font-semibold text-sm ${isDarkMode ? 'text-white' : 'text-gray-900'} ${!notification.is_read ? 'font-bold' : ''}`}>
                            {notification.title}
                          </h4>
                          {!notification.is_read && (
                            <span className="w-2 h-2 bg-primary rounded-full flex-shrink-0 mt-1.5"></span>
                          )}
                        </div>
                        <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-600'} line-clamp-2`}>
                          {notification.message}
                        </p>
                        <div className="flex items-center justify-between mt-2">
                          <span className={`text-xs ${isDarkMode ? 'text-gray-500' : 'text-gray-500'}`}>
                            {formatTimeAgo(notification.created_at)}
                          </span>
                          {notification.action_label && (
                            <span className="text-xs text-primary font-medium">
                              {notification.action_label} →
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteNotification(notification.id);
                        }}
                        className={`p-1 rounded hover:bg-opacity-50 ${isDarkMode ? 'hover:bg-gray-600' : 'hover:bg-gray-200'}`}
                      >
                        <svg className={`w-4 h-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className={`p-3 border-t ${isDarkMode ? 'border-gray-700' : 'border-gray-200'} text-center`}>
              <a
                href="/notifications"
                className={`text-sm font-medium ${isDarkMode ? 'text-primary hover:text-primary-dark' : 'text-primary hover:text-primary-dark'}`}
              >
                View all notifications
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
