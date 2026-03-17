'use client';

import { useState, useEffect, useCallback } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import TextAlign from '@tiptap/extension-text-align';
import { TextStyle } from '@tiptap/extension-text-style';
import Color from '@tiptap/extension-color';
import Placeholder from '@tiptap/extension-placeholder';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

interface SmtpConfig {
  enabled: boolean;
  sender_email: string;
  sender_name: string;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  use_tls: boolean;
  use_ssl: boolean;
}

interface EmailTemplate {
  enabled: boolean;
  logo_url?: string;
  subject_template: string;
  body_html: string;
  body_text: string;
}

interface EmailAttachment {
  filename: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  uploaded_at: string;
}

interface EmailSettingsSectionProps {
  assistantId: string;
  token?: string; // Optional - will fetch from localStorage if not provided
  isDarkMode?: boolean; // Optional - for dark mode support
}

const TEMPLATE_VARIABLES = [
  { key: 'customer_name', label: 'Customer Name' },
  { key: 'customer_email', label: 'Customer Email' },
  { key: 'customer_phone', label: 'Customer Phone' },
  { key: 'appointment_date', label: 'Appointment Date' },
  { key: 'appointment_time', label: 'Appointment Time' },
  { key: 'appointment_duration', label: 'Duration (minutes)' },
  { key: 'appointment_title', label: 'Appointment Title' },
  { key: 'meeting_link', label: 'Meeting Link' },
  { key: 'location', label: 'Location' },
  { key: 'company_name', label: 'Company Name' },
  { key: 'agent_name', label: 'Agent Name' },
  { key: 'sender_name', label: 'Sender Name' },
  { key: 'timezone', label: 'Timezone' },
];

// Common SMTP presets
const SMTP_PRESETS = [
  { name: 'Gmail', host: 'smtp.gmail.com', port: 587, use_tls: true, use_ssl: false },
  { name: 'Outlook/Office 365', host: 'smtp.office365.com', port: 587, use_tls: true, use_ssl: false },
  { name: 'Yahoo', host: 'smtp.mail.yahoo.com', port: 587, use_tls: true, use_ssl: false },
  { name: 'SendGrid', host: 'smtp.sendgrid.net', port: 587, use_tls: true, use_ssl: false },
  { name: 'Mailgun', host: 'smtp.mailgun.org', port: 587, use_tls: true, use_ssl: false },
  { name: 'AWS SES', host: 'email-smtp.us-east-1.amazonaws.com', port: 587, use_tls: true, use_ssl: false },
  { name: 'Custom', host: '', port: 587, use_tls: true, use_ssl: false },
];

export default function EmailSettingsSection({ assistantId, token: propToken, isDarkMode = false }: EmailSettingsSectionProps) {
  // Toolbar button component
  const ToolbarButton = ({
    onClick,
    isActive,
    children,
    title
  }: {
    onClick: () => void;
    isActive?: boolean;
    children: React.ReactNode;
    title?: string;
  }) => (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`p-2 rounded transition-colors ${
        isActive
          ? 'bg-primary/20 text-primary'
          : isDarkMode
            ? 'text-gray-300 hover:bg-gray-600'
            : 'text-gray-600 hover:bg-gray-200'
      }`}
    >
      {children}
    </button>
  );
  const [isLoading, setIsLoading] = useState(true);

  // Get token from props or localStorage
  const getToken = useCallback(() => {
    return propToken || (typeof window !== 'undefined' ? localStorage.getItem('token') : null) || '';
  }, [propToken]);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Email enabled state
  const [emailEnabled, setEmailEnabled] = useState(false);

  // SMTP Config
  const [smtpConfig, setSmtpConfig] = useState<SmtpConfig>({
    enabled: false,
    sender_email: '',
    sender_name: '',
    smtp_host: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    use_tls: true,
    use_ssl: false,
  });

  // Email Template
  const [emailTemplate, setEmailTemplate] = useState<EmailTemplate>({
    enabled: false,
    logo_url: '',
    subject_template: 'Your Appointment Confirmation - {{appointment_date}}',
    body_html: '',
    body_text: '',
  });

  // Attachments
  const [attachments, setAttachments] = useState<EmailAttachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  // Active tab
  const [activeTab, setActiveTab] = useState<'smtp' | 'template' | 'attachments' | 'logs'>('smtp');

  // TipTap Editor
  const editor = useEditor({
    immediatelyRender: false, // Fix SSR hydration mismatch
    extensions: [
      StarterKit,
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          class: 'text-primary underline',
        },
      }),
      Image,
      TextAlign.configure({
        types: ['heading', 'paragraph'],
      }),
      TextStyle,
      Color,
      Placeholder.configure({
        placeholder: 'Write your email content here...',
      }),
    ],
    content: emailTemplate.body_html,
    onUpdate: ({ editor }) => {
      setEmailTemplate(prev => ({
        ...prev,
        body_html: editor.getHTML(),
        body_text: editor.getText(),
      }));
    },
  });

  // Update editor content when template changes
  useEffect(() => {
    if (editor && emailTemplate.body_html && editor.getHTML() !== emailTemplate.body_html) {
      editor.commands.setContent(emailTemplate.body_html);
    }
  }, [editor, emailTemplate.body_html]);

  // Fetch email settings
  const fetchEmailSettings = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await fetch(`${API_URL}/api/ai-assistants/${assistantId}/email-settings`, {
        headers: {
          Authorization: `Bearer ${getToken()}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setEmailEnabled(data.email_enabled || false);
        if (data.smtp_config) {
          setSmtpConfig(prev => ({ ...prev, ...data.smtp_config }));
        }
        if (data.email_template) {
          setEmailTemplate(prev => ({ ...prev, ...data.email_template }));
          if (editor && data.email_template.body_html) {
            editor.commands.setContent(data.email_template.body_html);
          }
        }
        if (data.attachments) {
          setAttachments(data.attachments);
        }
      }
    } catch (error) {
      console.error('Error fetching email settings:', error);
    } finally {
      setIsLoading(false);
    }
  }, [assistantId, getToken, editor]);

  useEffect(() => {
    if (assistantId && getToken()) {
      fetchEmailSettings();
    }
  }, [assistantId, getToken, fetchEmailSettings]);

  // Save settings
  const saveSettings = async () => {
    try {
      setIsSaving(true);
      setMessage(null);

      // Automatically enable SMTP if required fields are filled
      const smtpEnabled = !!(smtpConfig.smtp_host && smtpConfig.smtp_username && smtpConfig.smtp_password);
      const configToSave = {
        ...smtpConfig,
        enabled: smtpEnabled
      };

      const response = await fetch(`${API_URL}/api/ai-assistants/${assistantId}/email-settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          email_enabled: emailEnabled,
          smtp_config: configToSave,
          email_template: emailTemplate,
        }),
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Email settings saved successfully!' });
      } else {
        const data = await response.json();
        setMessage({ type: 'error', text: data.detail || 'Failed to save settings' });
      }
    } catch (_error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setIsSaving(false);
    }
  };

  // Test SMTP
  const testSmtpConnection = async () => {
    if (!testEmail) {
      setMessage({ type: 'error', text: 'Please enter a test email address' });
      return;
    }

    try {
      setIsTesting(true);
      setMessage(null);

      const response = await fetch(`${API_URL}/api/ai-assistants/${assistantId}/email-settings/test-smtp`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          ...smtpConfig,
          test_recipient: testEmail,
        }),
      });

      const data = await response.json();
      if (data.success) {
        setMessage({ type: 'success', text: data.message });
      } else {
        setMessage({ type: 'error', text: data.message || 'SMTP test failed' });
      }
    } catch (_error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setIsTesting(false);
    }
  };

  // Send test email with template
  const sendTestEmail = async () => {
    if (!testEmail) {
      setMessage({ type: 'error', text: 'Please enter a test email address' });
      return;
    }

    try {
      setIsTesting(true);
      setMessage(null);

      // Save settings first
      await saveSettings();

      const response = await fetch(`${API_URL}/api/ai-assistants/${assistantId}/email-settings/send-test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          test_recipient: testEmail,
        }),
      });

      const data = await response.json();
      if (data.success) {
        setMessage({ type: 'success', text: data.message });
      } else {
        setMessage({ type: 'error', text: data.message || 'Failed to send test email' });
      }
    } catch (_error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setIsTesting(false);
    }
  };

  // Upload attachment
  const uploadAttachment = async (file: File) => {
    try {
      setIsUploading(true);
      setMessage(null);

      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_URL}/api/ai-assistants/${assistantId}/email-attachments/upload`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${getToken()}`,
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        setAttachments(prev => [...prev, data.attachment]);
        setMessage({ type: 'success', text: 'Attachment uploaded successfully!' });
      } else {
        const data = await response.json();
        setMessage({ type: 'error', text: data.detail || 'Failed to upload attachment' });
      }
    } catch (_error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setIsUploading(false);
    }
  };

  // Delete attachment
  const deleteAttachment = async (filename: string) => {
    try {
      const response = await fetch(`${API_URL}/api/ai-assistants/${assistantId}/email-attachments/${filename}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${getToken()}`,
        },
      });

      if (response.ok) {
        setAttachments(prev => prev.filter(a => a.filename !== filename));
        setMessage({ type: 'success', text: 'Attachment deleted successfully!' });
      }
    } catch (_error) {
      setMessage({ type: 'error', text: 'Failed to delete attachment' });
    }
  };

  // Insert variable into editor
  const insertVariable = (variableKey: string) => {
    if (editor) {
      editor.chain().focus().insertContent(`{{${variableKey}}}`).run();
    }
  };

  // Apply SMTP preset
  const applyPreset = (preset: typeof SMTP_PRESETS[0]) => {
    setSmtpConfig(prev => ({
      ...prev,
      smtp_host: preset.host,
      smtp_port: preset.port,
      use_tls: preset.use_tls,
      use_ssl: preset.use_ssl,
    }));
  };

  // Format file size
  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>Email Settings</h3>
          <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>Configure email confirmations for appointments</p>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <span className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>Enable Email Confirmations</span>
          <div className="relative">
            <input
              type="checkbox"
              checked={emailEnabled}
              onChange={(e) => setEmailEnabled(e.target.checked)}
              className="sr-only"
            />
            <div className={`w-11 h-6 rounded-full transition-colors ${emailEnabled ? 'bg-primary' : (isDarkMode ? 'bg-gray-600' : 'bg-gray-300')}`}>
              <div className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${emailEnabled ? 'translate-x-5' : ''}`}></div>
            </div>
          </div>
        </label>
      </div>

      {/* Message */}
      {message && (
        <div className={`p-4 rounded-lg ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-4">
          {[
            { id: 'smtp', label: 'SMTP Settings' },
            { id: 'template', label: 'Email Template' },
            { id: 'attachments', label: 'Attachments' },
            { id: 'logs', label: 'Email Logs' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as typeof activeTab)}
              className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* SMTP Settings Tab */}
      {activeTab === 'smtp' && (
        <div className="space-y-6">
          {/* SMTP Presets */}
          <div>
            <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Quick Setup</label>
            <div className="flex flex-wrap gap-2">
              {SMTP_PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  onClick={() => applyPreset(preset)}
                  className={`px-3 py-1.5 text-sm border rounded-lg transition-colors ${
                    isDarkMode
                      ? 'border-gray-600 text-gray-300 hover:bg-gray-600'
                      : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {preset.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Sender Email</label>
              <input
                type="email"
                value={smtpConfig.sender_email}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, sender_email: e.target.value }))}
                placeholder="noreply@yourcompany.com"
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
            </div>
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Sender Name</label>
              <input
                type="text"
                value={smtpConfig.sender_name}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, sender_name: e.target.value }))}
                placeholder="Your Company Name"
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
            </div>
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>SMTP Host</label>
              <input
                type="text"
                value={smtpConfig.smtp_host}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, smtp_host: e.target.value }))}
                placeholder="smtp.gmail.com"
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
            </div>
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>SMTP Port</label>
              <input
                type="number"
                value={smtpConfig.smtp_port}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, smtp_port: parseInt(e.target.value) || 587 }))}
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
            </div>
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>SMTP Username</label>
              <input
                type="text"
                value={smtpConfig.smtp_username}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, smtp_username: e.target.value }))}
                placeholder="your-email@gmail.com"
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
            </div>
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>SMTP Password</label>
              <input
                type="password"
                value={smtpConfig.smtp_password}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, smtp_password: e.target.value }))}
                placeholder="••••••••"
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
              <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>For Gmail, use an App Password</p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={smtpConfig.use_tls}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, use_tls: e.target.checked, use_ssl: false }))}
                className="rounded border-gray-300 text-primary focus:ring-primary"
              />
              <span className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Use TLS (STARTTLS)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={smtpConfig.use_ssl}
                onChange={(e) => setSmtpConfig(prev => ({ ...prev, use_ssl: e.target.checked, use_tls: false }))}
                className="rounded border-gray-300 text-primary focus:ring-primary"
              />
              <span className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Use SSL</span>
            </label>
          </div>

          {/* Test SMTP */}
          <div className={`border-t pt-4 ${isDarkMode ? 'border-gray-600' : ''}`}>
            <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Test SMTP Connection</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="Enter email to receive test"
                className={`flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
              <button
                onClick={testSmtpConnection}
                disabled={isTesting}
                className={`px-4 py-2 rounded-lg transition-colors disabled:opacity-50 ${
                  isDarkMode
                    ? 'bg-gray-700 text-gray-200 hover:bg-gray-600'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {isTesting ? 'Testing...' : 'Test Connection'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Email Template Tab */}
      {activeTab === 'template' && (
        <div className="space-y-6">
          {/* Subject */}
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Email Subject</label>
            <input
              type="text"
              value={emailTemplate.subject_template}
              onChange={(e) => setEmailTemplate(prev => ({ ...prev, subject_template: e.target.value }))}
              placeholder="Your Appointment Confirmation - {{appointment_date}}"
              className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                isDarkMode
                  ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
                  : 'bg-white border-gray-300 text-gray-900'
              }`}
            />
          </div>

          {/* Variable Picker */}
          <div>
            <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Insert Variable</label>
            <div className="flex flex-wrap gap-2">
              {TEMPLATE_VARIABLES.map((variable) => (
                <button
                  key={variable.key}
                  onClick={() => insertVariable(variable.key)}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    isDarkMode
                      ? 'bg-gray-700 text-gray-200 hover:bg-gray-600'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  title={`Insert {{${variable.key}}}`}
                >
                  {variable.label}
                </button>
              ))}
            </div>
          </div>

          {/* Rich Text Editor Toolbar */}
          {editor && (
            <div className={`border rounded-lg ${isDarkMode ? 'border-gray-600' : 'border-gray-300'}`}>
              <div className={`flex flex-wrap items-center gap-1 p-2 border-b ${
                isDarkMode
                  ? 'border-gray-600 bg-gray-700'
                  : 'border-gray-200 bg-gray-50'
              }`}>
                <ToolbarButton
                  onClick={() => editor.chain().focus().toggleBold().run()}
                  isActive={editor.isActive('bold')}
                  title="Bold"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 4h8a4 4 0 014 4 4 4 0 01-4 4H6z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 12h9a4 4 0 014 4 4 4 0 01-4 4H6z" />
                  </svg>
                </ToolbarButton>
                <ToolbarButton
                  onClick={() => editor.chain().focus().toggleItalic().run()}
                  isActive={editor.isActive('italic')}
                  title="Italic"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 4h4m-2 0v16m-4 0h8" transform="skewX(-10)" />
                  </svg>
                </ToolbarButton>
                <ToolbarButton
                  onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                  isActive={editor.isActive('heading', { level: 2 })}
                  title="Heading"
                >
                  <span className="font-bold text-sm">H</span>
                </ToolbarButton>
                <div className={`w-px h-6 mx-1 ${isDarkMode ? 'bg-gray-600' : 'bg-gray-300'}`}></div>
                <ToolbarButton
                  onClick={() => editor.chain().focus().setTextAlign('left').run()}
                  isActive={editor.isActive({ textAlign: 'left' })}
                  title="Align Left"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h10M4 18h16" />
                  </svg>
                </ToolbarButton>
                <ToolbarButton
                  onClick={() => editor.chain().focus().setTextAlign('center').run()}
                  isActive={editor.isActive({ textAlign: 'center' })}
                  title="Align Center"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M7 12h10M4 18h16" />
                  </svg>
                </ToolbarButton>
                <div className={`w-px h-6 mx-1 ${isDarkMode ? 'bg-gray-600' : 'bg-gray-300'}`}></div>
                <ToolbarButton
                  onClick={() => editor.chain().focus().toggleBulletList().run()}
                  isActive={editor.isActive('bulletList')}
                  title="Bullet List"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </ToolbarButton>
                <ToolbarButton
                  onClick={() => {
                    const url = prompt('Enter URL:');
                    if (url) {
                      editor.chain().focus().setLink({ href: url }).run();
                    }
                  }}
                  isActive={editor.isActive('link')}
                  title="Add Link"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                </ToolbarButton>
              </div>
              <EditorContent
                editor={editor}
                className={`prose max-w-none p-4 min-h-[300px] focus:outline-none ${
                  isDarkMode
                    ? 'prose-invert bg-gray-600 text-white'
                    : 'bg-white text-gray-900'
                }`}
              />
            </div>
          )}

          {/* Send Test Email */}
          <div className={`border-t pt-4 ${isDarkMode ? 'border-gray-600' : ''}`}>
            <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Preview & Test</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="Enter email to receive test"
                className={`flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
                  isDarkMode
                    ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              />
              <button
                onClick={sendTestEmail}
                disabled={isTesting}
                className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {isTesting ? 'Sending...' : 'Send Test Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Attachments Tab */}
      {activeTab === 'attachments' && (
        <div className="space-y-6">
          <div>
            <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
              Email Attachments ({attachments.length}/10)
            </label>
            <p className={`text-sm mb-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
              These files will be attached to every appointment confirmation email.
            </p>

            {/* Upload Area */}
            <div className={`border-2 border-dashed rounded-lg p-6 text-center ${
              isDarkMode ? 'border-gray-600' : 'border-gray-300'
            }`}>
              <input
                type="file"
                id="attachment-upload"
                className="hidden"
                accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.png,.jpg,.jpeg,.gif"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadAttachment(file);
                  e.target.value = '';
                }}
                disabled={isUploading || attachments.length >= 10}
              />
              <label
                htmlFor="attachment-upload"
                className={`cursor-pointer ${attachments.length >= 10 ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <svg className={`mx-auto h-12 w-12 ${isDarkMode ? 'text-gray-500' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className={`mt-2 text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>
                  {isUploading ? 'Uploading...' : 'Click to upload or drag and drop'}
                </p>
                <p className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>PDF, DOCX, XLSX, PPTX, TXT, Images (max 25MB each)</p>
              </label>
            </div>

            {/* Attachment List */}
            {attachments.length > 0 && (
              <ul className="mt-4 space-y-2">
                {attachments.map((attachment) => (
                  <li key={attachment.filename} className={`flex items-center justify-between p-3 rounded-lg ${
                    isDarkMode ? 'bg-gray-700' : 'bg-gray-50'
                  }`}>
                    <div className="flex items-center gap-3">
                      <svg className={`w-8 h-8 ${isDarkMode ? 'text-gray-500' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                      <div>
                        <p className={`text-sm font-medium ${isDarkMode ? 'text-gray-200' : 'text-gray-700'}`}>{attachment.original_filename}</p>
                        <p className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>{formatFileSize(attachment.file_size)}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => deleteAttachment(attachment.filename)}
                      className="p-1 text-red-500 hover:bg-red-50 rounded"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && (
        <div className="space-y-4">
          <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
            Email sending history will appear here once you start sending appointment confirmations.
          </p>
          {/* TODO: Implement email logs list */}
          <div className={`text-center py-8 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
            <svg className={`mx-auto h-12 w-12 ${isDarkMode ? 'text-gray-600' : 'text-gray-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
            </svg>
            <p className="mt-2">No emails sent yet</p>
          </div>
        </div>
      )}

      {/* Save Button */}
      <div className={`flex justify-end pt-4 border-t ${isDarkMode ? 'border-gray-600' : ''}`}>
        <button
          onClick={saveSettings}
          disabled={isSaving}
          className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {isSaving ? 'Saving...' : 'Save Email Settings'}
        </button>
      </div>
    </div>
  );
}
