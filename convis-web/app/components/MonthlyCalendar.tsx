'use client';

import { useMemo, useState, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

interface CalendarEvent {
  id: string;
  title: string;
  start?: string | null;
  end?: string | null;
  provider: string;
  location?: string | null;
  meeting_link?: string | null;
  description?: string | null;
  // Call summary fields (for Convis-booked events)
  call_sid?: string | null;
  call_summary?: string | null;
  transcript?: string | null;
  recording_url?: string | null;
  call_duration?: number | null;
}

interface AppointmentDetails {
  call_sid: string;
  call_summary: string;
  transcript: string;
  recording_url: string;
  call_duration: number;
  title: string;
  start: string;
  end: string;
  provider: string;
}

interface MonthlyCalendarProps {
  events: CalendarEvent[];
  isDarkMode: boolean;
  onDateClick?: (date: Date) => void;
  onMonthChange?: (year: number, month: number) => void;
}

const DAYS_OF_WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export function MonthlyCalendar({ events, isDarkMode, onDateClick, onMonthChange }: MonthlyCalendarProps) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [appointmentDetails, setAppointmentDetails] = useState<AppointmentDetails | null>(null);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);

  const { year, month } = useMemo(() => ({
    year: currentDate.getFullYear(),
    month: currentDate.getMonth(),
  }), [currentDate]);

  const calendarDays = useMemo(() => {
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDayOfWeek = firstDay.getDay();

    const days: (Date | null)[] = [];

    // Add empty cells for days before the first day of the month
    for (let i = 0; i < startingDayOfWeek; i++) {
      days.push(null);
    }

    // Add actual days
    for (let day = 1; day <= daysInMonth; day++) {
      days.push(new Date(year, month, day));
    }

    return days;
  }, [year, month]);

  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();

    events.forEach((event) => {
      if (!event.start) return;

      try {
        const eventDate = new Date(event.start);
        const dateKey = `${eventDate.getFullYear()}-${eventDate.getMonth()}-${eventDate.getDate()}`;

        if (!map.has(dateKey)) {
          map.set(dateKey, []);
        }
        map.get(dateKey)!.push(event);
      } catch {
        console.error('Invalid event date:', event.start);
      }
    });

    return map;
  }, [events]);

  const getEventsForDate = (date: Date | null): CalendarEvent[] => {
    if (!date) return [];
    const dateKey = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
    return eventsByDate.get(dateKey) || [];
  };

  const isToday = (date: Date | null): boolean => {
    if (!date) return false;
    const today = new Date();
    return (
      date.getDate() === today.getDate() &&
      date.getMonth() === today.getMonth() &&
      date.getFullYear() === today.getFullYear()
    );
  };

  const goToPreviousMonth = () => {
    const newDate = new Date(year, month - 1, 1);
    setCurrentDate(newDate);
    onMonthChange?.(newDate.getFullYear(), newDate.getMonth());
  };

  const goToNextMonth = () => {
    const newDate = new Date(year, month + 1, 1);
    setCurrentDate(newDate);
    onMonthChange?.(newDate.getFullYear(), newDate.getMonth());
  };

  const goToToday = () => {
    const newDate = new Date();
    setCurrentDate(newDate);
    onMonthChange?.(newDate.getFullYear(), newDate.getMonth());
  };

  const handleEventClick = useCallback(async (event: CalendarEvent, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent date click from firing
    setSelectedEvent(event);
    setAppointmentDetails(null);

    // Try to fetch appointment details by event ID
    try {
      setIsLoadingDetails(true);
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/calendar/appointment-details/${event.id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (response.ok) {
        const data = await response.json();
        // API returns the appointment details directly (not wrapped in .appointment)
        if (data && (data.call_summary || data.call_sid || data.transcript)) {
          setAppointmentDetails({
            call_sid: data.call_sid,
            call_summary: data.call_summary,
            transcript: data.transcript,
            recording_url: data.recording_url,
            call_duration: data.call_duration,
            title: data.title || event.title,
            start: data.start_time || event.start || '',
            end: data.end_time || event.end || '',
            provider: data.provider || event.provider,
          });
        }
      }
    } catch (error) {
      console.error('Error fetching appointment details:', error);
    } finally {
      setIsLoadingDetails(false);
    }
  }, []);

  const closeEventModal = () => {
    setSelectedEvent(null);
    setAppointmentDetails(null);
  };

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  return (
    <div className="w-full">
      {/* Calendar Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-dark'}`}>
          {MONTHS[month]} {year}
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={goToToday}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              isDarkMode
                ? 'bg-gray-700 text-white hover:bg-gray-600'
                : 'bg-neutral-light text-dark hover:bg-neutral-mid/20'
            }`}
          >
            Today
          </button>
          <button
            onClick={goToPreviousMonth}
            className={`p-2 rounded-lg transition-colors ${
              isDarkMode
                ? 'text-gray-400 hover:bg-gray-700 hover:text-white'
                : 'text-neutral-mid hover:bg-neutral-light'
            }`}
            aria-label="Previous month"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            onClick={goToNextMonth}
            className={`p-2 rounded-lg transition-colors ${
              isDarkMode
                ? 'text-gray-400 hover:bg-gray-700 hover:text-white'
                : 'text-neutral-mid hover:bg-neutral-light'
            }`}
            aria-label="Next month"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>

      {/* Days of Week Header */}
      <div className="grid grid-cols-7 gap-2 mb-2">
        {DAYS_OF_WEEK.map((day) => (
          <div
            key={day}
            className={`text-center text-sm font-semibold py-2 ${
              isDarkMode ? 'text-gray-400' : 'text-neutral-mid'
            }`}
          >
            {day}
          </div>
        ))}
      </div>

      {/* Calendar Grid */}
      <div className="grid grid-cols-7 gap-2">
        {calendarDays.map((date, index) => {
          const dayEvents = getEventsForDate(date);
          const isCurrentDay = isToday(date);

          return (
            <div
              key={index}
              onClick={() => date && onDateClick?.(date)}
              className={`
                min-h-[140px] rounded-lg border p-2 transition-all cursor-pointer flex flex-col
                ${date ? 'hover:shadow-md' : ''}
                ${
                  isDarkMode
                    ? date
                      ? 'bg-gray-800/50 border-gray-700 hover:bg-gray-800'
                      : 'bg-gray-900/20 border-gray-800'
                    : date
                      ? 'bg-white border-neutral-mid/10 hover:bg-neutral-light'
                      : 'bg-neutral-light/30 border-neutral-mid/5'
                }
                ${isCurrentDay ? (isDarkMode ? 'ring-2 ring-primary' : 'ring-2 ring-primary') : ''}
              `}
            >
              {date && (
                <>
                  <div className="flex items-center justify-between mb-1 flex-shrink-0">
                    <span
                      className={`
                        text-sm font-semibold
                        ${isCurrentDay ? 'text-primary' : isDarkMode ? 'text-white' : 'text-dark'}
                      `}
                    >
                      {date.getDate()}
                    </span>
                  </div>

                  <div className="space-y-1 overflow-y-auto flex-1">
                    {dayEvents.map((event) => {
                      const eventTime = event.start ? new Date(event.start).toLocaleTimeString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true,
                      }) : '';

                      return (
                        <div
                          key={event.id}
                          onClick={(e) => handleEventClick(event, e)}
                          className={`
                            text-[11px] px-2 py-1 rounded-md cursor-pointer hover:opacity-80 transition-opacity
                            ${event.provider === 'google'
                              ? isDarkMode
                                ? 'bg-red-900/40 text-red-100 border-l-2 border-red-500'
                                : 'bg-red-100 text-red-800 border-l-2 border-red-500'
                              : isDarkMode
                                ? 'bg-blue-900/40 text-blue-100 border-l-2 border-blue-500'
                                : 'bg-blue-100 text-blue-800 border-l-2 border-blue-500'
                            }
                          `}
                          title={`${eventTime} - ${event.title} (Click for details)`}
                        >
                          <div className="font-medium truncate leading-tight">{event.title}</div>
                          {eventTime && (
                            <div className={`text-[10px] mt-0.5 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                              {eventTime}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Event Details Modal */}
      {selectedEvent && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={closeEventModal}
        >
          <div
            className={`max-w-2xl w-full max-h-[90vh] overflow-y-auto rounded-2xl shadow-xl ${
              isDarkMode ? 'bg-gray-800' : 'bg-white'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className={`p-6 border-b ${isDarkMode ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className={`text-xl font-bold ${isDarkMode ? 'text-white' : 'text-dark'}`}>
                    {selectedEvent.title || '(No title)'}
                  </h3>
                  <div className={`flex items-center gap-2 mt-2 text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    <span className={`px-2 py-1 rounded-full text-xs font-semibold ${
                      selectedEvent.provider === 'google'
                        ? 'bg-red-500 text-white'
                        : 'bg-blue-500 text-white'
                    }`}>
                      {selectedEvent.provider === 'google' ? 'Google' : 'Microsoft'}
                    </span>
                    {selectedEvent.start && (
                      <span>
                        {new Date(selectedEvent.start).toLocaleDateString('en-US', {
                          weekday: 'long',
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                        })}
                      </span>
                    )}
                  </div>
                  {selectedEvent.start && (
                    <p className={`mt-1 text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>
                      {new Date(selectedEvent.start).toLocaleTimeString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true,
                      })}
                      {selectedEvent.end && (
                        <> - {new Date(selectedEvent.end).toLocaleTimeString('en-US', {
                          hour: 'numeric',
                          minute: '2-digit',
                          hour12: true,
                        })}</>
                      )}
                    </p>
                  )}
                </div>
                <button
                  onClick={closeEventModal}
                  className={`p-2 rounded-lg transition-colors ${
                    isDarkMode ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-600'
                  }`}
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-6">
              {/* Location */}
              {selectedEvent.location && (
                <div>
                  <h4 className={`text-sm font-semibold mb-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    Location
                  </h4>
                  <p className={`${isDarkMode ? 'text-white' : 'text-dark'}`}>{selectedEvent.location}</p>
                </div>
              )}

              {/* Meeting Link */}
              {selectedEvent.meeting_link && (
                <div>
                  <h4 className={`text-sm font-semibold mb-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    Meeting Link
                  </h4>
                  <a
                    href={selectedEvent.meeting_link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline break-all"
                  >
                    Join Meeting
                  </a>
                </div>
              )}

              {/* Loading State */}
              {isLoadingDetails && (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                  <span className={`ml-3 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                    Loading call details...
                  </span>
                </div>
              )}

              {/* Call Summary Section (if this is a Convis-booked appointment) */}
              {appointmentDetails && (
                <div className={`rounded-xl p-4 ${isDarkMode ? 'bg-gray-900/50' : 'bg-neutral-light'}`}>
                  <h4 className={`text-lg font-semibold mb-4 flex items-center gap-2 ${isDarkMode ? 'text-white' : 'text-dark'}`}>
                    <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                    </svg>
                    Call Summary
                  </h4>

                  {/* Call Duration */}
                  {appointmentDetails.call_duration && (
                    <div className="mb-4">
                      <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                        Duration: {formatDuration(appointmentDetails.call_duration)}
                      </span>
                    </div>
                  )}

                  {/* Summary */}
                  {appointmentDetails.call_summary && (
                    <div className="mb-4">
                      <h5 className={`text-sm font-semibold mb-2 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                        Summary
                      </h5>
                      <p className={`text-sm leading-relaxed ${isDarkMode ? 'text-gray-200' : 'text-gray-700'}`}>
                        {appointmentDetails.call_summary}
                      </p>
                    </div>
                  )}

                  {/* Transcript */}
                  {appointmentDetails.transcript && (
                    <div className="mb-4">
                      <h5 className={`text-sm font-semibold mb-2 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                        Conversation Transcript
                      </h5>
                      <div className={`text-sm leading-relaxed max-h-48 overflow-y-auto p-3 rounded-lg ${
                        isDarkMode ? 'bg-gray-800 text-gray-300' : 'bg-white text-gray-600'
                      }`}>
                        {appointmentDetails.transcript.split('\n').map((line, idx) => (
                          <p key={idx} className="mb-1">{line}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Recording Link */}
                  {appointmentDetails.recording_url && (
                    <div>
                      <h5 className={`text-sm font-semibold mb-2 ${isDarkMode ? 'text-gray-400' : 'text-neutral-mid'}`}>
                        Recording
                      </h5>
                      <a
                        href={appointmentDetails.recording_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Listen to Recording
                      </a>
                    </div>
                  )}

                  {/* View Full Call Log Link */}
                  {appointmentDetails.call_sid && (
                    <div className="mt-4 pt-4 border-t border-gray-700">
                      <a
                        href={`/call-logs?call_sid=${appointmentDetails.call_sid}`}
                        className={`text-sm text-primary hover:underline`}
                      >
                        View Full Call Log →
                      </a>
                    </div>
                  )}
                </div>
              )}

              {/* No call details message */}
              {!isLoadingDetails && !appointmentDetails && (
                <div className={`text-center py-4 ${isDarkMode ? 'text-gray-500' : 'text-neutral-mid'}`}>
                  <p className="text-sm">This event doesn&apos;t have associated call details.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
