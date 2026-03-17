'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface UserWorkflow {
  id: string;
  name: string;
  description?: string;
  active: boolean;
  trigger_type: string;
  template_id: string;
  config: Record<string, any>;
  created_at: string;
  updated_at: string;
  execution_count: number;
  last_execution?: {
    status: string;
    finished_at: string;
  };
}

interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  category: string;
  fields: TemplateField[];
}

interface TemplateField {
  name: string;
  label: string;
  type: 'text' | 'email' | 'url' | 'select' | 'checkbox' | 'textarea';
  placeholder?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
  defaultValue?: string | boolean;
}

// Inline SVG Icons
const ArrowLeftIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
  </svg>
);

const PlusIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
  </svg>
);

const EditIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
  </svg>
);

const PlayIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
  </svg>
);

const PauseIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const XIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const MailIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>
);

const CalendarIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
  </svg>
);

const SlackIcon = () => (
  <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
    <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.124 2.521a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.52 2.521h-2.522V8.834zm-1.268 0a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zm-2.523 10.124a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.52v-2.522h2.52zm0-1.268a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/>
  </svg>
);

const DatabaseIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
  </svg>
);

const WebhookIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
  </svg>
);

const CheckCircleIcon = ({ className = "w-5 h-5 text-green-500" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const XCircleIcon = ({ className = "w-5 h-5 text-red-500" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ClockIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const LoaderIcon = ({ className = "w-6 h-6 animate-spin" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
  </svg>
);

const EmptyIcon = () => (
  <svg className="w-16 h-16 text-gray-300 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
  </svg>
);

// Workflow templates with configuration fields
const workflowTemplates: WorkflowTemplate[] = [
  {
    id: 'send-email-after-call',
    name: 'Send Email After Call',
    description: 'Automatically send a follow-up email after each completed call',
    icon: <MailIcon />,
    category: 'Communication',
    fields: [
      { name: 'to_email', label: 'Recipient Email', type: 'email', placeholder: 'customer@example.com or leave empty to use customer email', required: false },
      { name: 'subject', label: 'Email Subject', type: 'text', placeholder: 'Thank you for your call', required: true, defaultValue: 'Thank you for speaking with us' },
      { name: 'include_summary', label: 'Include Call Summary', type: 'checkbox', defaultValue: true },
      { name: 'include_transcript', label: 'Include Transcript', type: 'checkbox', defaultValue: false },
    ],
  },
  {
    id: 'slack-notification',
    name: 'Slack Notification',
    description: 'Send call summaries and alerts to your Slack channel',
    icon: <SlackIcon />,
    category: 'Notifications',
    fields: [
      { name: 'webhook_url', label: 'Slack Webhook URL', type: 'url', placeholder: 'https://hooks.slack.com/services/...', required: true },
      { name: 'channel', label: 'Channel (optional)', type: 'text', placeholder: '#calls' },
      { name: 'include_sentiment', label: 'Include Sentiment', type: 'checkbox', defaultValue: true },
      { name: 'only_negative', label: 'Only Notify on Negative Sentiment', type: 'checkbox', defaultValue: false },
    ],
  },
  {
    id: 'update-crm',
    name: 'Update CRM',
    description: 'Sync call data to HubSpot, Salesforce, or other CRMs',
    icon: <DatabaseIcon />,
    category: 'CRM',
    fields: [
      { name: 'crm_provider', label: 'CRM Provider', type: 'select', required: true, options: [
        { value: 'hubspot', label: 'HubSpot' },
        { value: 'salesforce', label: 'Salesforce' },
        { value: 'pipedrive', label: 'Pipedrive' },
        { value: 'zoho', label: 'Zoho CRM' },
      ]},
      { name: 'api_key', label: 'API Key', type: 'text', placeholder: 'Your CRM API key', required: true },
      { name: 'create_contact', label: 'Create Contact if Not Exists', type: 'checkbox', defaultValue: true },
      { name: 'log_activity', label: 'Log Call as Activity', type: 'checkbox', defaultValue: true },
    ],
  },
  {
    id: 'create-calendar-event',
    name: 'Create Calendar Event',
    description: 'Book follow-up appointments automatically',
    icon: <CalendarIcon />,
    category: 'Scheduling',
    fields: [
      { name: 'calendar_provider', label: 'Calendar Provider', type: 'select', required: true, options: [
        { value: 'google', label: 'Google Calendar' },
        { value: 'outlook', label: 'Microsoft Outlook' },
      ]},
      { name: 'duration_minutes', label: 'Event Duration (minutes)', type: 'text', placeholder: '30', defaultValue: '30' },
      { name: 'title_prefix', label: 'Event Title Prefix', type: 'text', placeholder: 'Follow-up:', defaultValue: 'Follow-up call with' },
    ],
  },
  {
    id: 'custom-webhook',
    name: 'Custom Webhook',
    description: 'Send call data to any external API or service',
    icon: <WebhookIcon />,
    category: 'Integration',
    fields: [
      { name: 'webhook_url', label: 'Webhook URL', type: 'url', placeholder: 'https://your-api.com/webhook', required: true },
      { name: 'method', label: 'HTTP Method', type: 'select', required: true, options: [
        { value: 'POST', label: 'POST' },
        { value: 'PUT', label: 'PUT' },
      ], defaultValue: 'POST' },
      { name: 'custom_headers', label: 'Custom Headers (JSON)', type: 'textarea', placeholder: '{"Authorization": "Bearer xxx"}' },
    ],
  },
];

export default function UserWorkflowsPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(true);
  const [workflows, setWorkflows] = useState<UserWorkflow[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowTemplate | null>(null);
  const [editingWorkflow, setEditingWorkflow] = useState<UserWorkflow | null>(null);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [workflowName, setWorkflowName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Fetch user's workflows
  const fetchUserWorkflows = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/n8n/user-workflows`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setWorkflows(data.workflows || []);
      } else {
        setWorkflows([]);
      }
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
      setWorkflows([]);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      setIsLoading(true);
      await fetchUserWorkflows();
      setIsLoading(false);
    };
    init();
  }, [fetchUserWorkflows]);

  const openCreateModal = (template: WorkflowTemplate) => {
    setSelectedTemplate(template);
    setWorkflowName(template.name);
    // Initialize form data with defaults
    const defaults: Record<string, any> = {};
    template.fields.forEach(field => {
      if (field.defaultValue !== undefined) {
        defaults[field.name] = field.defaultValue;
      }
    });
    setFormData(defaults);
    setError('');
    setShowCreateModal(true);
  };

  const openEditModal = (workflow: UserWorkflow) => {
    setEditingWorkflow(workflow);
    const template = workflowTemplates.find(t => t.id === workflow.template_id);
    if (template) {
      setSelectedTemplate(template);
      setWorkflowName(workflow.name);
      setFormData(workflow.config || {});
      setError('');
      setShowEditModal(true);
    }
  };

  const closeModal = () => {
    setShowCreateModal(false);
    setShowEditModal(false);
    setSelectedTemplate(null);
    setEditingWorkflow(null);
    setFormData({});
    setWorkflowName('');
    setError('');
  };

  const handleFieldChange = (fieldName: string, value: any) => {
    setFormData(prev => ({ ...prev, [fieldName]: value }));
  };

  const validateForm = (): boolean => {
    if (!selectedTemplate) return false;

    for (const field of selectedTemplate.fields) {
      if (field.required && !formData[field.name]) {
        setError(`${field.label} is required`);
        return false;
      }
    }

    if (!workflowName.trim()) {
      setError('Workflow name is required');
      return false;
    }

    return true;
  };

  const createWorkflow = async () => {
    if (!validateForm() || !selectedTemplate) return;

    setIsSubmitting(true);
    setError('');

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/n8n/user-workflows/create-from-template`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          template_id: selectedTemplate.id,
          name: workflowName,
          config: formData,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setWorkflows(prev => [data.workflow, ...prev]);
        closeModal();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to create workflow');
      }
    } catch (error) {
      console.error('Failed to create workflow:', error);
      setError('Failed to create workflow. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const updateWorkflow = async () => {
    if (!validateForm() || !editingWorkflow) return;

    setIsSubmitting(true);
    setError('');

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/n8n/user-workflows/${editingWorkflow.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: workflowName,
          config: formData,
        }),
      });

      if (response.ok) {
        await fetchUserWorkflows();
        closeModal();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to update workflow');
      }
    } catch (error) {
      console.error('Failed to update workflow:', error);
      setError('Failed to update workflow. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleWorkflow = async (workflowId: string, currentActive: boolean) => {
    try {
      const token = localStorage.getItem('token');
      const endpoint = currentActive ? 'deactivate' : 'activate';
      const response = await fetch(`${API_URL}/api/n8n/user-workflows/${workflowId}/${endpoint}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        setWorkflows(prev =>
          prev.map(w =>
            w.id === workflowId ? { ...w, active: !currentActive } : w
          )
        );
      }
    } catch (error) {
      console.error('Failed to toggle workflow:', error);
    }
  };

  const deleteWorkflow = async (workflowId: string) => {
    if (!confirm('Are you sure you want to delete this automation?')) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/n8n/user-workflows/${workflowId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        setWorkflows(prev => prev.filter(w => w.id !== workflowId));
      }
    } catch (error) {
      console.error('Failed to delete workflow:', error);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const getTemplateIcon = (templateId: string) => {
    const template = workflowTemplates.find(t => t.id === templateId);
    return template?.icon || <WebhookIcon />;
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-900">
        <LoaderIcon />
        <p className="mt-4 text-gray-600 dark:text-gray-400">Loading automations...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/workflows')}
              className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
            >
              <ArrowLeftIcon />
              <span className="hidden sm:inline">Back</span>
            </button>

            <div className="h-6 w-px bg-gray-300 dark:bg-gray-600" />

            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              My Automations
            </h1>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* Empty State - Show Templates */}
        {workflows.length === 0 && (
          <div className="mb-8">
            <div className="text-center mb-8">
              <EmptyIcon className="mx-auto mb-4" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Create Your First Automation
              </h2>
              <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                Choose a template to automatically perform actions after each call completes.
              </p>
            </div>
          </div>
        )}

        {/* Templates Section */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {workflows.length > 0 ? 'Add New Automation' : 'Available Templates'}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workflowTemplates.map((template) => (
              <button
                key={template.id}
                onClick={() => openCreateModal(template)}
                className="text-left bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 hover:shadow-md transition-all"
              >
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg">
                    {template.icon}
                  </div>
                  <div className="flex-1">
                    <h4 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                      {template.name}
                      <PlusIcon className="w-4 h-4 text-gray-400" />
                    </h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      {template.description}
                    </p>
                    <span className="inline-block mt-2 text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
                      {template.category}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Active Workflows List */}
        {workflows.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Your Automations
            </h3>
            <div className="space-y-4">
              {workflows.map((workflow) => (
                <div
                  key={workflow.id}
                  className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-4">
                      <div className={`p-2.5 rounded-lg ${workflow.active ? 'bg-green-100 dark:bg-green-900/30 text-green-600' : 'bg-gray-100 dark:bg-gray-700 text-gray-500'}`}>
                        {getTemplateIcon(workflow.template_id)}
                      </div>
                      <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                          {workflow.name}
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            workflow.active
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                          }`}>
                            {workflow.active ? 'Active' : 'Paused'}
                          </span>
                        </h4>
                        {workflow.description && (
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            {workflow.description}
                          </p>
                        )}
                        <div className="flex items-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
                          <span className="flex items-center gap-1">
                            <ClockIcon />
                            Created {formatDate(workflow.created_at)}
                          </span>
                          {workflow.execution_count > 0 && (
                            <span>{workflow.execution_count} runs</span>
                          )}
                          {workflow.last_execution && (
                            <span className="flex items-center gap-1">
                              {workflow.last_execution.status === 'success' ? (
                                <CheckCircleIcon className="w-3.5 h-3.5" />
                              ) : (
                                <XCircleIcon className="w-3.5 h-3.5" />
                              )}
                              Last: {formatDate(workflow.last_execution.finished_at)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => openEditModal(workflow)}
                        className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                        title="Edit"
                      >
                        <EditIcon />
                      </button>
                      <button
                        onClick={() => toggleWorkflow(workflow.id, workflow.active)}
                        className={`p-2 rounded-lg transition-colors ${
                          workflow.active
                            ? 'text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/20'
                            : 'text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20'
                        }`}
                        title={workflow.active ? 'Pause' : 'Activate'}
                      >
                        {workflow.active ? <PauseIcon /> : <PlayIcon />}
                      </button>
                      <button
                        onClick={() => deleteWorkflow(workflow.id)}
                        className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title="Delete"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Info Section */}
        <div className="mt-8 bg-blue-50 dark:bg-blue-900/20 rounded-xl p-5 border border-blue-100 dark:border-blue-900/30">
          <h4 className="font-medium text-blue-800 dark:text-blue-300 mb-2">
            How Automations Work
          </h4>
          <ul className="text-sm text-blue-700 dark:text-blue-400 space-y-1">
            <li>• Automations run automatically when a call completes</li>
            <li>• Each automation receives call data: transcript, summary, sentiment, customer info</li>
            <li>• You can have multiple automations - they all run for each call</li>
            <li>• Pause automations anytime without deleting them</li>
          </ul>
        </div>
      </main>

      {/* Create/Edit Modal */}
      {(showCreateModal || showEditModal) && selectedTemplate && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <div className="fixed inset-0 bg-black/50" onClick={closeModal} />

            <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-lg w-full p-6">
              {/* Modal Header */}
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg">
                    {selectedTemplate.icon}
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {showEditModal ? 'Edit' : 'Create'} {selectedTemplate.name}
                    </h2>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {selectedTemplate.description}
                    </p>
                  </div>
                </div>
                <button
                  onClick={closeModal}
                  className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  <XIcon />
                </button>
              </div>

              {/* Error Message */}
              {error && (
                <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 rounded-lg text-red-600 dark:text-red-400 text-sm">
                  {error}
                </div>
              )}

              {/* Form */}
              <div className="space-y-4">
                {/* Workflow Name */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Automation Name
                  </label>
                  <input
                    type="text"
                    value={workflowName}
                    onChange={(e) => setWorkflowName(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="My Automation"
                  />
                </div>

                {/* Template Fields */}
                {selectedTemplate.fields.map((field) => (
                  <div key={field.name}>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {field.label}
                      {field.required && <span className="text-red-500 ml-1">*</span>}
                    </label>

                    {field.type === 'text' || field.type === 'email' || field.type === 'url' ? (
                      <input
                        type={field.type}
                        value={formData[field.name] || ''}
                        onChange={(e) => handleFieldChange(field.name, e.target.value)}
                        placeholder={field.placeholder}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    ) : field.type === 'select' ? (
                      <select
                        value={formData[field.name] || ''}
                        onChange={(e) => handleFieldChange(field.name, e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      >
                        <option value="">Select...</option>
                        {field.options?.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    ) : field.type === 'checkbox' ? (
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData[field.name] || false}
                          onChange={(e) => handleFieldChange(field.name, e.target.checked)}
                          className="w-4 h-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                        />
                        <span className="text-sm text-gray-600 dark:text-gray-400">Enable</span>
                      </label>
                    ) : field.type === 'textarea' ? (
                      <textarea
                        value={formData[field.name] || ''}
                        onChange={(e) => handleFieldChange(field.name, e.target.value)}
                        placeholder={field.placeholder}
                        rows={3}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    ) : null}
                  </div>
                ))}
              </div>

              {/* Modal Footer */}
              <div className="flex items-center justify-end gap-3 mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={closeModal}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={showEditModal ? updateWorkflow : createWorkflow}
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg transition-colors flex items-center gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <LoaderIcon className="w-4 h-4" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <span>{showEditModal ? 'Save Changes' : 'Create Automation'}</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
