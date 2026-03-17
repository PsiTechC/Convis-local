'use client';

import { useState, useEffect, useCallback, ChangeEvent } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

const COUNTRIES = [
  { code: 'US', name: 'United States' },
  { code: 'CA', name: 'Canada' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'AU', name: 'Australia' },
  { code: 'IN', name: 'India' },
  { code: 'SG', name: 'Singapore' },
  { code: 'ZA', name: 'South Africa' },
];

const TIMEZONES = [
  { value: 'America/New_York', label: 'Eastern Time (ET)' },
  { value: 'America/Chicago', label: 'Central Time (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
  { value: 'America/Toronto', label: 'Toronto' },
  { value: 'Europe/London', label: 'London' },
  { value: 'Asia/Kolkata', label: 'India' },
  { value: 'Australia/Sydney', label: 'Sydney' },
  { value: 'Asia/Singapore', label: 'Singapore' },
  { value: 'Africa/Johannesburg', label: 'South Africa' },
];

const DEFAULT_TIMEZONE_BY_COUNTRY: Record<string, string> = {
  US: 'America/New_York',
  CA: 'America/Toronto',
  GB: 'Europe/London',
  AU: 'Australia/Sydney',
  IN: 'Asia/Kolkata',
  SG: 'Asia/Singapore',
  ZA: 'Africa/Johannesburg',
};

const WEEK_DAYS = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
];

const CSV_REQUIRED_HEADERS = ['firstName', 'contact_number'] as const;
const CSV_EXPECTED_ORDER = ['firstName', 'lastName', 'contact_number', 'timezone'] as const;
const MAX_CSV_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB

const normalizeHeader = (value: string) => value.replace(/^"+|"+$/g, '').trim().toLowerCase();

const parseCsvRow = (line: string): string[] => {
  const cells: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];

    if (char === '"') {
      const nextChar = line[i + 1];
      if (inQuotes && nextChar === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      cells.push(current);
      current = '';
    } else {
      current += char;
    }
  }

  cells.push(current);
  return cells.map((cell) => cell.trim().replace(/^"+|"+$/g, ''));
};

interface CreateCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  isDarkMode: boolean;
  userId: string;
  mode?: 'create' | 'edit';
  campaignId?: string;
  initialCampaign?: ExistingCampaign | null;
  initialStep?: 1 | 2 | 3;
}

interface AIAgent {
  id: string;
  name: string;
  description?: string;
}

interface PhoneNumber {
  _id?: string;
  phone_number: string;
  friendly_name?: string;
}

interface CalendarAccount {
  id: string;
  provider: string;
  email: string;
  created_at?: string;
  updated_at?: string;
}

interface CampaignDatabaseConfigForm {
  enabled: boolean;
  type: string;
  host: string;
  port: string;
  database: string;
  username: string;
  password: string;
  table_name: string;
  search_columns: string;
}

interface CampaignFormData {
  name: string;
  country: string;
  assistant_id: string;
  caller_id: string;
  timezone: string;
  start_time: string;
  end_time: string;
  working_days: number[];
  start_date: string;
  end_date: string;
  max_attempts: number;
  retry_delays: string;
  calendar_enabled: boolean;
  calendar_account_id: string;
  database_config: CampaignDatabaseConfigForm;
}

interface ExistingCampaign {
  id?: string;
  name: string;
  country: string;
  assistant_id?: string | null;
  caller_id?: string;
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
  start_at?: string | null;
  stop_at?: string | null;
  calendar_enabled?: boolean;
  calendar_account_id?: string | null;
  system_prompt_override?: string | null;
  database_config?: {
    enabled?: boolean;
    type?: string;
    host?: string;
    port?: string;
    database?: string;
    username?: string;
    password?: string;
    table_name?: string;
    search_columns?: string[];
  } | null;
}

const createDefaultFormState = (): CampaignFormData => ({
  name: '',
  country: 'US',
  assistant_id: '',
  caller_id: '',
  timezone: 'America/New_York',
  start_time: '09:00',
  end_time: '17:00',
  working_days: [0, 1, 2, 3, 4],
  start_date: '',
  end_date: '',
  max_attempts: 3,
  retry_delays: '15,60,1440',
  calendar_enabled: false,
  calendar_account_id: '',
  database_config: {
    enabled: false,
    type: 'postgresql',
    host: '',
    port: '5432',
    database: '',
    username: '',
    password: '',
    table_name: '',
    search_columns: '',
  },
});

const mapCampaignToFormData = (campaign: ExistingCampaign): CampaignFormData => {
  const workingWindow = campaign.working_window || { timezone: 'America/New_York', start: '09:00', end: '17:00', days: [0, 1, 2, 3, 4] };
  const retryPolicy = campaign.retry_policy || { max_attempts: 3, retry_after_minutes: [15, 60, 1440] };
  const databaseConfig = campaign.database_config;

  const startDate = campaign.start_at ? new Date(campaign.start_at).toISOString().slice(0, 10) : '';
  const endDate = campaign.stop_at ? new Date(campaign.stop_at).toISOString().slice(0, 10) : '';

  return {
    name: campaign.name || '',
    country: campaign.country || 'US',
    assistant_id: campaign.assistant_id || '',
    caller_id: campaign.caller_id || '',
    timezone: workingWindow.timezone || 'America/New_York',
    start_time: workingWindow.start || '09:00',
    end_time: workingWindow.end || '17:00',
    working_days: workingWindow.days && workingWindow.days.length > 0 ? [...workingWindow.days] : [0, 1, 2, 3, 4],
    start_date: startDate,
    end_date: endDate,
    max_attempts: retryPolicy.max_attempts || 3,
    retry_delays: (retryPolicy.retry_after_minutes || []).join(',') || '15,60,1440',
    calendar_enabled: !!campaign.calendar_enabled,
    calendar_account_id: campaign.calendar_account_id || '',
    database_config: {
      enabled: !!databaseConfig?.enabled,
      type: databaseConfig?.type || 'postgresql',
      host: databaseConfig?.host || '',
      port: databaseConfig?.port || '5432',
      database: databaseConfig?.database || '',
      username: databaseConfig?.username || '',
      password: databaseConfig?.password || '',
      table_name: databaseConfig?.table_name || '',
      search_columns: (databaseConfig?.search_columns || []).join(','),
    },
  };
};

export default function CreateCampaignModal({
  isOpen,
  onClose,
  onSuccess,
  isDarkMode,
  userId,
  mode = 'create',
  campaignId,
  initialCampaign = null,
  initialStep = 1,
}: CreateCampaignModalProps) {
  const isEditMode = mode === 'edit';
  const [step, setStep] = useState<number>(initialStep);
  const [isLoading, setIsLoading] = useState(false);
  const [aiAgents, setAiAgents] = useState<AIAgent[]>([]);
  const [phoneNumbers, setPhoneNumbers] = useState<PhoneNumber[]>([]);
  const [calendarAccounts, setCalendarAccounts] = useState<CalendarAccount[]>([]);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [leadBatchName, setLeadBatchName] = useState<string>('');
  const [isTimezoneManuallySet, setIsTimezoneManuallySet] = useState(false);

  const [formData, setFormData] = useState<CampaignFormData>(
    isEditMode && initialCampaign ? mapCampaignToFormData(initialCampaign) : createDefaultFormState()
  );

  const [errors, setErrors] = useState<Record<string, string>>({});

  const timezones = TIMEZONES;
  const countries = COUNTRIES;
  const weekDays = WEEK_DAYS;

  const fetchAIAgents = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/ai-assistants/user/${userId}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : undefined,
      });
      if (response.ok) {
        const data = await response.json();
        setAiAgents(data.assistants || []);
      } else {
        console.error('Failed to fetch AI agents:', response.status, await response.text());
      }
    } catch (error) {
      console.error('Error fetching AI agents:', error);
    }
  }, [userId]);

  const fetchPhoneNumbers = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/phone-numbers/user/${userId}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : undefined,
      });
      if (response.ok) {
        const data = await response.json();
        setPhoneNumbers(data.phone_numbers || []);
      }
    } catch (error) {
      console.error('Error fetching phone numbers:', error);
    }
  }, [userId]);

  const fetchCalendarAccounts = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/calendar/accounts/${userId}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : undefined,
      });
      if (response.ok) {
        const data = await response.json();
        setCalendarAccounts(data.accounts || []);
      }
    } catch (error) {
      console.error('Error fetching calendar accounts:', error);
    }
  }, [userId]);

  useEffect(() => {
    if (isOpen) {
      fetchAIAgents();
      fetchPhoneNumbers();
      fetchCalendarAccounts();
    }
  }, [isOpen, fetchAIAgents, fetchPhoneNumbers, fetchCalendarAccounts]);

  useEffect(() => {
    if (!isOpen) return;
    if (isEditMode) {
      if (initialCampaign) {
        setFormData(mapCampaignToFormData(initialCampaign));
        setIsTimezoneManuallySet(true);
      }
    } else {
      setFormData(createDefaultFormState());
      setIsTimezoneManuallySet(false);
    }
    setStep(initialStep);
    setCsvFile(null);
    setLeadBatchName('');
    setErrors({});
  }, [isOpen, isEditMode, initialCampaign, initialStep]);

  useEffect(() => {
    if (isTimezoneManuallySet) return;
    const defaultTimezone = DEFAULT_TIMEZONE_BY_COUNTRY[formData.country];
    if (defaultTimezone && formData.timezone !== defaultTimezone) {
      setFormData(prev => ({ ...prev, timezone: defaultTimezone }));
    }
  }, [formData.country, formData.timezone, isTimezoneManuallySet]);

  const handleInputChange = <K extends keyof CampaignFormData>(field: K, value: CampaignFormData[K]) => {
    if (field === 'country') {
      setIsTimezoneManuallySet(false);
    }
    if (field === 'timezone') {
      setIsTimezoneManuallySet(true);
    }

    setFormData(prev => ({ ...prev, [field]: value }));
    setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const handleDbConfigChange = (field: keyof CampaignDatabaseConfigForm, value: string | boolean) => {
    setFormData(prev => ({
      ...prev,
      database_config: {
        ...prev.database_config,
        [field]: value,
      },
    }));
    setErrors(prev => ({ ...prev, [`db_${field}`]: '' }));
  };

  const toggleWorkingDay = (day: number) => {
    setFormData(prev => ({
      ...prev,
      working_days: prev.working_days.includes(day)
        ? prev.working_days.filter(d => d !== day)
        : [...prev.working_days, day].sort()
    }));
  };

  const validateStep = (currentStep: number): boolean => {
    const newErrors: Record<string, string> = {};

    if (currentStep === 1) {
      if (!formData.name.trim()) newErrors.name = 'Campaign name is required';
      if (!formData.assistant_id) newErrors.assistant_id = 'Please select an AI agent';
      if (!formData.caller_id) newErrors.caller_id = 'Please select a phone number';
      if (!formData.country) newErrors.country = 'Please select a country';
    }

    if (currentStep === 2) {
      if (!formData.timezone) newErrors.timezone = 'Please select a timezone';
      if (!formData.start_time) newErrors.start_time = 'Start time is required';
      if (!formData.end_time) newErrors.end_time = 'End time is required';
      if (formData.working_days.length === 0) newErrors.working_days = 'Select at least one day';
      if (formData.start_date && formData.end_date) {
        if (new Date(formData.end_date) < new Date(formData.start_date)) {
          newErrors.end_date = 'End date must be after start date';
        }
      }
      if (formData.calendar_enabled && !formData.calendar_account_id) {
        newErrors.calendar_account_id = 'Please select a calendar account';
      }
      if (formData.database_config.enabled) {
        if (!formData.database_config.host.trim()) newErrors.db_host = 'Database host is required';
        if (!formData.database_config.database.trim()) newErrors.db_database = 'Database name is required';
        if (!formData.database_config.table_name.trim()) newErrors.db_table_name = 'Table name is required';
      }
    }

    if (currentStep === 3) {
      // CSV is required when creating new campaign OR when user is on step 3 (upload leads step)
      // Only skip validation if editing campaign and starting from step 1 or 2 (not on upload step)
      if (!csvFile && (!isEditMode || initialStep === 3)) {
        newErrors.csvFile = 'Please upload a CSV file with leads';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (validateStep(step)) {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    setStep(step - 1);
  };

  const handleSubmit = async () => {
    if (!validateStep(step)) return;

    setIsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const authHeaders: Record<string, string> = token ? { 'Authorization': `Bearer ${token}` } : {};

      const retryAfterMinutes = formData.retry_delays
        .split(',')
        .map((value) => parseInt(value.trim(), 10))
        .filter((value) => !Number.isNaN(value) && value >= 0);

      const databaseConfigPayload = formData.database_config.enabled
        ? {
            enabled: true,
            type: formData.database_config.type,
            host: formData.database_config.host,
            port: formData.database_config.port,
            database: formData.database_config.database,
            username: formData.database_config.username,
            password: formData.database_config.password,
            table_name: formData.database_config.table_name,
            search_columns: formData.database_config.search_columns
              .split(',')
              .map((col) => col.trim())
              .filter((col) => col.length > 0),
          }
        : null;

      const startAtIso = formData.start_date ? new Date(formData.start_date).toISOString() : null;
      const stopAtIso = formData.end_date ? new Date(formData.end_date).toISOString() : null;

      const basePayload = {
        name: formData.name,
        country: formData.country,
        caller_id: formData.caller_id,
        assistant_id: formData.assistant_id,
        working_window: {
          timezone: formData.timezone,
          start: formData.start_time,
          end: formData.end_time,
          days: formData.working_days,
        },
        retry_policy: {
          max_attempts: formData.max_attempts,
          retry_after_minutes: retryAfterMinutes.length ? retryAfterMinutes : [15, 60, 1440],
        },
        pacing: {
          calls_per_minute: 1,
          max_concurrent: 1,
        },
        start_at: startAtIso,
        stop_at: stopAtIso,
        calendar_enabled: formData.calendar_enabled,
        calendar_account_id: formData.calendar_enabled && formData.calendar_account_id ? formData.calendar_account_id : null,
        database_config: databaseConfigPayload,
      };

      const isCreate = !isEditMode;

      const requestUrl = isCreate
        ? `${API_URL}/api/campaigns/`
        : `${API_URL}/api/campaigns/${campaignId}`;

      if (!isCreate && !campaignId) {
        throw new Error('Missing campaign ID for update');
      }

      const requestPayload = isCreate
        ? { user_id: userId, ...basePayload }
        : basePayload;

      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...authHeaders,
      };

      const response = await fetch(requestUrl, {
        method: isCreate ? 'POST' : 'PUT',
        headers,
        body: JSON.stringify(requestPayload),
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorData: Record<string, unknown> = {};
        try {
          errorData = JSON.parse(errorText);
        } catch (parseError) {
          console.error('Could not parse error response as JSON', parseError);
        }

        const detail = typeof errorData.detail === 'string' ? errorData.detail : undefined;
        const message = typeof errorData.message === 'string' ? errorData.message : undefined;
        throw new Error(detail || message || `Failed to ${isCreate ? 'create' : 'update'} campaign (${response.status})`);
      }

      const responseData = await response.json();
      const resolvedCampaignId = isCreate ? (responseData.id || responseData._id) : campaignId;

      if (!resolvedCampaignId) {
        throw new Error('Unable to resolve campaign identifier');
      }

      if (csvFile) {
        const formDataUpload = new FormData();
        formDataUpload.append('file', csvFile);
        if (leadBatchName.trim()) {
          formDataUpload.append('batch_name', leadBatchName.trim());
        }

        const uploadResponse = await fetch(
          `${API_URL}/api/campaigns/${resolvedCampaignId}/leads/upload`,
          {
            method: 'POST',
            headers: authHeaders,
            body: formDataUpload,
          }
        );

        if (!uploadResponse.ok) {
          const uploadError = await uploadResponse.text();
          throw new Error(uploadError || 'Failed to upload leads');
        }
      }

      onSuccess();
      resetForm();
      onClose();

      if (isCreate) {
        alert(csvFile ? 'Campaign created and leads uploaded successfully.' : 'Campaign created successfully.');
      } else {
        alert(csvFile ? 'Campaign updated and new leads uploaded successfully.' : 'Campaign updated successfully.');
      }
    } catch (error: unknown) {
      console.error('Error saving campaign:', error);
      const message = error instanceof Error ? error.message : 'Failed to save campaign. Please try again.';
      alert(message);
    } finally {
      setIsLoading(false);
    }
  };

  const resetForm = () => {
    if (isEditMode && initialCampaign) {
      setFormData(mapCampaignToFormData(initialCampaign));
      setStep(initialStep);
      setIsTimezoneManuallySet(true);
    } else {
      setFormData(createDefaultFormState());
      setStep(1);
      setIsTimezoneManuallySet(false);
    }
    setCsvFile(null);
    setErrors({});
    setLeadBatchName('');
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.csv')) {
      setErrors((prev) => ({ ...prev, csvFile: 'Please upload a .csv file' }));
      setCsvFile(null);
      event.target.value = '';
      return;
    }

    if (file.size > MAX_CSV_FILE_SIZE_BYTES) {
      setErrors((prev) => ({ ...prev, csvFile: 'CSV file size must be under 10MB' }));
      setCsvFile(null);
      event.target.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onerror = () => {
      setErrors((prev) => ({ ...prev, csvFile: 'Could not read the selected file. Please try again.' }));
      setCsvFile(null);
      event.target.value = '';
    };

    reader.onload = () => {
      const text = typeof reader.result === 'string' ? reader.result : '';
      const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);

      if (lines.length === 0) {
        setErrors((prev) => ({ ...prev, csvFile: 'The selected CSV appears to be empty.' }));
        setCsvFile(null);
        event.target.value = '';
        return;
      }

      const headerRow = parseCsvRow(lines[0]);
      const normalizedHeaders = headerRow.map((header) => normalizeHeader(header));
      const headerSet = new Set(normalizedHeaders);

      const missingHeaders = CSV_REQUIRED_HEADERS.filter(
        (header) => !headerSet.has(header.toLowerCase()),
      );

      if (missingHeaders.length > 0) {
        setErrors((prev) => ({
          ...prev,
          csvFile: `Missing required column${missingHeaders.length > 1 ? 's' : ''}: ${missingHeaders.join(', ')}`,
        }));
        setCsvFile(null);
        event.target.value = '';
        return;
      }

      const orderIndices = CSV_EXPECTED_ORDER
        .filter((header) => headerSet.has(header.toLowerCase()))
        .map((header) => normalizedHeaders.indexOf(header.toLowerCase()));

      const isOrderValid = orderIndices.every((idx, index) => index === 0 || idx > orderIndices[index - 1]);

      if (!isOrderValid) {
        setErrors((prev) => ({
          ...prev,
          csvFile: 'Please keep the columns in the order: firstName, lastName (optional), contact_number, timezone (optional).',
        }));
        setCsvFile(null);
        event.target.value = '';
        return;
      }

      const firstNameIndex = normalizedHeaders.indexOf('firstname');
      const contactIndex = normalizedHeaders.indexOf('contact_number');

      const rowsWithMissingRequired = lines.slice(1).reduce<number[]>((acc, line, idx) => {
        if (acc.length >= 5) {
          return acc;
        }
        if (!line.trim()) {
          return acc;
        }
        const cells = parseCsvRow(line);
        const firstNameValue = (cells[firstNameIndex] || '').trim();
        const contactValue = (cells[contactIndex] || '').trim();

        if (!firstNameValue || !contactValue) {
          acc.push(idx + 2); // account for header row
        }

        return acc;
      }, []);

      if (rowsWithMissingRequired.length > 0) {
        setErrors((prev) => ({
          ...prev,
          csvFile: `Some rows are missing required values for firstName/contact_number (e.g. row${rowsWithMissingRequired.length > 1 ? 's' : ''} ${rowsWithMissingRequired.join(', ')}).`,
        }));
        setCsvFile(null);
        event.target.value = '';
        return;
      }

      setCsvFile(file);
      setErrors((prev) => ({ ...prev, csvFile: '' }));
      event.target.value = '';
    };

    reader.readAsText(file);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className={`${isDarkMode ? 'bg-gray-800' : 'bg-white'} rounded-2xl w-full max-w-2xl my-8`}>
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-dark'}`}>
              Create New Campaign
            </h2>
            <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
              Step {step} of 3
            </p>
          </div>
          <button
            onClick={onClose}
            className={`p-2 rounded-lg ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`}
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress Bar */}
        <div className="px-6 pt-4">
          <div className="flex items-center justify-between mb-2">
            <span className={`text-sm font-medium ${step >= 1 ? 'text-primary' : isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
              Basic Info
            </span>
            <span className={`text-sm font-medium ${step >= 2 ? 'text-primary' : isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
              Schedule
            </span>
            <span className={`text-sm font-medium ${step >= 3 ? 'text-primary' : isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
              Upload Leads
            </span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className="bg-primary h-2 rounded-full transition-all duration-300"
              style={{ width: `${(step / 3) * 100}%` }}
            ></div>
          </div>
        </div>

        {/* Form Content */}
        <div className="p-6">
          {/* Step 1: Basic Information */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Campaign Name *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => handleInputChange('name', e.target.value)}
                  placeholder="e.g., Q1 Sales Outreach"
                  className={`w-full px-4 py-3 rounded-lg border ${
                    errors.name ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                  } ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                />
                {errors.name && <p className="text-red-500 text-sm mt-1">{errors.name}</p>}
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Target Country *
                </label>
                <select
                  value={formData.country}
                  onChange={(e) => handleInputChange('country', e.target.value)}
                  className={`w-full px-4 py-3 rounded-lg border ${
                    errors.country ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                  } ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                >
                  <option value="">Select Country</option>
                  {countries.map(country => (
                    <option key={country.code} value={country.code}>{country.name}</option>
                  ))}
                </select>
                {errors.country && <p className="text-red-500 text-sm mt-1">{errors.country}</p>}
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  AI Agent *
                </label>
                <select
                  value={formData.assistant_id}
                  onChange={(e) => handleInputChange('assistant_id', e.target.value)}
                  className={`w-full px-4 py-3 rounded-lg border ${
                    errors.assistant_id ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                  } ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                >
                  <option value="">Select AI Agent</option>
                  {aiAgents.map(agent => (
                    <option key={agent.id} value={agent.id}>{agent.name}</option>
                  ))}
                </select>
                {errors.assistant_id && <p className="text-red-500 text-sm mt-1">{errors.assistant_id}</p>}
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Caller Phone Number *
                </label>
                <select
                  value={formData.caller_id}
                  onChange={(e) => handleInputChange('caller_id', e.target.value)}
                  className={`w-full px-4 py-3 rounded-lg border ${
                    errors.caller_id ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                  } ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                >
                  <option value="">Select Phone Number</option>
                  {phoneNumbers.map((phone, idx) => {
                    const optionKey = phone._id ?? `${phone.phone_number}-${idx}`;
                    return (
                      <option key={optionKey} value={phone.phone_number}>
                        {phone.friendly_name || phone.phone_number}
                      </option>
                    );
                  })}
                </select>
                {errors.caller_id && <p className="text-red-500 text-sm mt-1">{errors.caller_id}</p>}
              </div>
            </div>
          )}

          {/* Step 2: Schedule Configuration */}
          {step === 2 && (
            <div className="space-y-4">
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Timezone *
                </label>
                <select
                  value={formData.timezone}
                  onChange={(e) => handleInputChange('timezone', e.target.value)}
                  className={`w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                >
                  {timezones.map(tz => (
                    <option key={tz.value} value={tz.value}>{tz.label}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    Start Time *
                  </label>
                  <input
                    type="time"
                    value={formData.start_time}
                    onChange={(e) => handleInputChange('start_time', e.target.value)}
                    className={`w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                  />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    End Time *
                  </label>
                  <input
                    type="time"
                    value={formData.end_time}
                    onChange={(e) => handleInputChange('end_time', e.target.value)}
                    className={`w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                  />
                </div>
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Working Days *
                </label>
                <div className="flex gap-2">
                  {weekDays.map(day => (
                    <button
                      key={day.value}
                      type="button"
                      onClick={() => toggleWorkingDay(day.value)}
                      className={`flex-1 py-2 px-3 rounded-lg font-medium transition-colors ${
                        formData.working_days.includes(day.value)
                          ? 'bg-primary text-white'
                          : isDarkMode ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {day.label}
                    </button>
                  ))}
                </div>
                {errors.working_days && <p className="text-red-500 text-sm mt-1">{errors.working_days}</p>}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    Campaign Start Date (Optional)
                  </label>
                  <input
                    type="date"
                    value={formData.start_date}
                    onChange={(e) => handleInputChange('start_date', e.target.value)}
                    className={`w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                  />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                    Campaign End Date (Optional)
                  </label>
                  <input
                    type="date"
                    value={formData.end_date}
                    onChange={(e) => handleInputChange('end_date', e.target.value)}
                    className={`w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                  />
                  {errors.end_date && <p className="text-red-500 text-sm mt-1">{errors.end_date}</p>}
                </div>
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Retry Settings
                </label>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={`block text-xs mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Max Attempts
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={formData.max_attempts}
                      onChange={(e) => handleInputChange('max_attempts', parseInt(e.target.value))}
                      className={`w-full px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'}`}
                    />
                  </div>
                  <div>
                    <label className={`block text-xs mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Retry Delays (minutes)
                    </label>
                    <input
                      type="text"
                      value={formData.retry_delays}
                      onChange={(e) => handleInputChange('retry_delays', e.target.value)}
                      placeholder="15,60,1440"
                      className={`w-full px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'}`}
                    />
                  </div>
                </div>
                <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  Comma-separated values in minutes (e.g., 15,60,1440 = 15min, 1hr, 1day)
                </p>
              </div>

              <div className={`${isDarkMode ? 'bg-gray-700/40 border-gray-600' : 'bg-gray-50 border-gray-200'} border rounded-lg p-4`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.calendar_enabled}
                        onChange={(e) => handleInputChange('calendar_enabled', e.target.checked)}
                        className="w-5 h-5 text-primary rounded focus:ring-2 focus:ring-primary"
                      />
                      <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                        Enable calendar booking (auto-book appointments from conversations)
                      </span>
                    </label>
                    <p className={`text-xs mt-1 ml-7 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      The bot will automatically save appointments to your connected calendar during calls.
                    </p>
                  </div>
                </div>

                {/* Calendar Account Selector */}
                {formData.calendar_enabled && (
                  <div className="mt-4 ml-7">
                    {calendarAccounts.length > 0 ? (
                      <div>
                        <label className={`block text-xs font-medium mb-2 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Select Calendar for Booking *
                        </label>
                        <select
                          value={formData.calendar_account_id}
                          onChange={(e) => handleInputChange('calendar_account_id', e.target.value)}
                          className={`w-full px-4 py-3 rounded-lg border ${
                            errors.calendar_account_id ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          } ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                        >
                          <option value="">Select a calendar account</option>
                          {calendarAccounts.map((account) => (
                            <option key={account.id} value={account.id}>
                              {account.provider === 'google' ? '📅 Google' : '📆 Microsoft'} - {account.email}
                            </option>
                          ))}
                        </select>
                        {errors.calendar_account_id && (
                          <p className="text-red-500 text-xs mt-1">{errors.calendar_account_id}</p>
                        )}
                        <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Appointments will be saved to this calendar account when detected during calls.
                        </p>
                      </div>
                    ) : (
                      <div className={`flex items-start gap-2 p-3 rounded-lg ${isDarkMode ? 'bg-yellow-900/30 border border-yellow-700' : 'bg-yellow-50 border border-yellow-200'}`}>
                        <svg className="w-5 h-5 flex-shrink-0 text-yellow-500 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <div className="flex-1">
                          <p className={`text-xs font-medium ${isDarkMode ? 'text-yellow-300' : 'text-yellow-800'}`}>
                            No calendar connected
                          </p>
                          <p className={`text-xs mt-1 ${isDarkMode ? 'text-yellow-400' : 'text-yellow-700'}`}>
                            Please connect a calendar from the{' '}
                            <a href="/connect-calendar" target="_blank" className="underline font-medium">
                              Calendar Settings
                            </a>
                            {' '}page to enable appointment booking.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className={`${isDarkMode ? 'bg-gray-700/40 border-gray-600' : 'bg-gray-50 border-gray-200'} border rounded-lg p-4`}>
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className={`text-sm font-semibold ${isDarkMode ? 'text-gray-200' : 'text-gray-800'}`}>
                      Database Lookup
                    </h4>
                    <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      Automatically fetch caller context from your database before each call.
                    </p>
                  </div>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.database_config.enabled}
                      onChange={(e) => handleDbConfigChange('enabled', e.target.checked)}
                      className="w-5 h-5 text-primary rounded focus:ring-2 focus:ring-primary"
                    />
                    <span className={`${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Enable</span>
                  </label>
                </div>

                {formData.database_config.enabled && (
                  <div className="mt-4 space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Database Type
                        </label>
                        <select
                          value={formData.database_config.type}
                          onChange={(e) => handleDbConfigChange('type', e.target.value)}
                          className={`w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                        >
                          <option value="postgresql">PostgreSQL</option>
                          <option value="mysql">MySQL</option>
                          <option value="mssql">SQL Server</option>
                        </select>
                      </div>
                      <div>
                        <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Hostname
                        </label>
                        <input
                          type="text"
                          value={formData.database_config.host}
                          onChange={(e) => handleDbConfigChange('host', e.target.value)}
                          placeholder="db.company.com"
                          className={`w-full px-3 py-2 rounded-lg border ${
                            errors.db_host ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          } ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                        />
                        {errors.db_host && <p className="text-red-500 text-xs mt-1">{errors.db_host}</p>}
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Port
                        </label>
                        <input
                          type="text"
                          value={formData.database_config.port}
                          onChange={(e) => handleDbConfigChange('port', e.target.value)}
                          className={`w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                        />
                      </div>
                      <div>
                        <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Database Name
                        </label>
                        <input
                          type="text"
                          value={formData.database_config.database}
                          onChange={(e) => handleDbConfigChange('database', e.target.value)}
                          className={`w-full px-3 py-2 rounded-lg border ${
                            errors.db_database ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          } ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                        />
                        {errors.db_database && <p className="text-red-500 text-xs mt-1">{errors.db_database}</p>}
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Username
                        </label>
                        <input
                          type="text"
                          value={formData.database_config.username}
                          onChange={(e) => handleDbConfigChange('username', e.target.value)}
                          className={`w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                        />
                      </div>
                      <div>
                        <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          Password
                        </label>
                        <input
                          type="password"
                          value={formData.database_config.password}
                          onChange={(e) => handleDbConfigChange('password', e.target.value)}
                          className={`w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                        />
                      </div>
                    </div>
                    <div>
                      <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                        Table Name
                      </label>
                      <input
                        type="text"
                        value={formData.database_config.table_name}
                        onChange={(e) => handleDbConfigChange('table_name', e.target.value)}
                        className={`w-full px-3 py-2 rounded-lg border ${
                          errors.db_table_name ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                        } ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                      />
                      {errors.db_table_name && <p className="text-red-500 text-xs mt-1">{errors.db_table_name}</p>}
                    </div>
                    <div>
                      <label className={`block text-xs font-medium mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                        Search Columns (comma separated)
                      </label>
                      <input
                        type="text"
                        value={formData.database_config.search_columns}
                        onChange={(e) => handleDbConfigChange('search_columns', e.target.value)}
                        placeholder="phone,email,account_id"
                        className={`w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-800 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Step 3: Upload Leads */}
          {step === 3 && (
            <div className="space-y-6">
              <div className={`${isDarkMode ? 'bg-gray-800/80 border-gray-700' : 'bg-neutral-50 border-neutral-200'} border rounded-2xl p-6 space-y-4`}>
                <div className="space-y-1">
                  <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-neutral-dark'}`}>Upload CSV</h3>
                  <p className={`${isDarkMode ? 'text-gray-400' : 'text-neutral-600'} text-sm`}>
                    Format your CSV exactly like the sample.
                  </p>
                </div>
                {isEditMode && (
                  <p className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-neutral-500'}`}>
                    Uploading a new CSV is optional. Leave this step blank if you only need to update the campaign settings.
                  </p>
                )}
                <ul className={`list-disc pl-5 space-y-2 text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-700'}`}>
                  <li>
                    <span className="font-semibold">Headers (exact names):</span>{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">firstName</code>,{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">lastName</code> (optional),{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">contact_number</code>,{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">timezone</code> (optional).
                  </li>
                  <li>
                    <span className="font-semibold">Order matters:</span> keep columns in the order above. Each row must include
                    values for <code className="font-mono bg-primary/10 px-1 rounded">firstName</code> and{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">contact_number</code>.
                  </li>
                  <li>
                    <span className="font-semibold">Phone format:</span> Prefer E.164 (e.g. <code className="font-mono bg-primary/10 px-1 rounded">+14155550123</code>).
                    We also accept 10-digit mobile numbers such as <code className="font-mono bg-primary/10 px-1 rounded">9876543210</code> or{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">+919876543210</code>.
                  </li>
                  <li>
                    <span className="font-semibold">Timezone:</span> Use an IANA name like{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">Asia/Kolkata</code> or{' '}
                    <code className="font-mono bg-primary/10 px-1 rounded">America/New_York</code>. If blank, we use the campaign
                    timezone (which defaults to <code className="font-mono bg-primary/10 px-1 rounded">Asia/Kolkata</code> unless you pick another during setup).
                  </li>
                  <li>
                    Maximum file size: 10MB.
                  </li>
                </ul>
                <a
                  href="/samples/leads-upload-sample.csv"
                  download
                  className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V4" />
                  </svg>
                  Download sample CSV file
                </a>
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Batch Name
                </label>
                <input
                  type="text"
                  value={leadBatchName}
                  onChange={(event) => setLeadBatchName(event.target.value)}
                  placeholder="e.g. Summer Sales Campaign"
                  className={`w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-white text-dark'} focus:ring-2 focus:ring-primary focus:border-transparent`}
                />
                <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-neutral-500'}`}>
                  Optional label to help identify this group of leads later.
                </p>
              </div>

              <div className="space-y-2">
                <label className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  Upload CSV File *
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleFileChange}
                  className={`block w-full text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-700'} file:mr-4 file:px-4 file:py-2.5 file:rounded-lg file:border-0 file:bg-primary file:text-white hover:file:bg-primary/90 cursor-pointer`}
                />
                {csvFile && (
                  <p className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-neutral-600'}`}>
                    Selected file: <span className="font-medium">{csvFile.name}</span>{' '}
                    <span className="text-xs">
                      ({(csvFile.size / 1024).toFixed(2)} KB)
                    </span>
                  </p>
                )}
                {csvFile && (
                  <button
                    type="button"
                    onClick={() => setCsvFile(null)}
                    className="text-sm font-medium text-primary hover:underline"
                  >
                    Remove file
                  </button>
                )}
                <p className={`text-xs ${isDarkMode ? 'text-gray-500' : 'text-neutral-500'}`}>
                  Only .csv files are supported. Maximum size 10MB.
                </p>
                {errors.csvFile && <p className="text-red-500 text-sm">{errors.csvFile}</p>}
              </div>
            </div>
          )}
        </div>

        {/* Footer Buttons */}
        <div className={`flex items-center justify-between p-6 border-t ${isDarkMode ? 'border-gray-700' : 'border-gray-200'}`}>
          <button
            onClick={step === 1 ? onClose : handleBack}
            disabled={isLoading}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              isDarkMode
                ? 'bg-gray-700 text-white hover:bg-gray-600'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {step === 1 ? 'Cancel' : 'Back'}
          </button>

          <div className="flex gap-2">
            {step < 3 ? (
              <button
                onClick={handleNext}
                className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium"
              >
                Next
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={isLoading}
                className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    {csvFile ? 'Uploading...' : isEditMode ? 'Saving...' : 'Creating...'}
                  </>
                ) : (
                  isEditMode ? (csvFile ? 'Save & Upload' : 'Save Changes') : 'Create Campaign'
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
