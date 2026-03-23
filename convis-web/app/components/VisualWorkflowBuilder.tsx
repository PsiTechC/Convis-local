'use client';

import { useState } from 'react';

interface Step {
  id: string;
  type: 'trigger' | 'filter' | 'action';
  name: string;
  icon: string;
  config: any;
  position: number;
}

interface VisualWorkflowBuilderProps {
  isDarkMode: boolean;
  onSave: (steps: Step[]) => void;
  onChange?: (steps: Step[]) => void;
  initialSteps?: Step[];
}

export function VisualWorkflowBuilder({ isDarkMode, onSave: _onSave, onChange, initialSteps }: VisualWorkflowBuilderProps) {
  const [steps, setSteps] = useState<Step[]>(
    initialSteps && initialSteps.length > 0
      ? initialSteps
      : [
          {
            id: 'trigger-1',
            type: 'trigger',
            name: 'When this happens...',
            icon: '⚡',
            config: {},
            position: 0
          }
        ]
  );
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [showStepMenu, setShowStepMenu] = useState(false);
  const [insertPosition, setInsertPosition] = useState<number>(0);

  // Helper function to update steps and notify parent
  const updateSteps = (newSteps: Step[]) => {
    setSteps(newSteps);
    if (onChange) {
      onChange(newSteps);
    }
  };

  const availableActions = [
    { type: 'filter', name: 'Filter', icon: '🔍', description: 'Only continue if conditions match', category: 'Logic' },
    { type: 'action', name: 'Branch', icon: '🔀', description: 'If-else conditional logic', category: 'Logic' },
    { type: 'action', name: 'Loop', icon: '🔁', description: 'Iterate over array items', category: 'Logic' },
    { type: 'action', name: 'Delay', icon: '⏱️', description: 'Wait before continuing workflow', category: 'Logic' },
    { type: 'action', name: 'Send Email', icon: '📧', description: 'Send an email via SMTP', category: 'Communication' },
    { type: 'action', name: 'Create Jira Ticket', icon: '🎫', description: 'Create a new Jira issue', category: 'Project Management' },
    { type: 'action', name: 'Update Jira Ticket', icon: '✏️', description: 'Update existing Jira issue', category: 'Project Management' },
    { type: 'action', name: 'Create HubSpot Contact', icon: '👤', description: 'Add contact to HubSpot', category: 'CRM' },
    { type: 'action', name: 'Update HubSpot Contact', icon: '✏️', description: 'Update HubSpot contact', category: 'CRM' },
    { type: 'action', name: 'Create HubSpot Note', icon: '📝', description: 'Add note to HubSpot contact', category: 'CRM' },
    { type: 'action', name: 'Send Slack Message', icon: '💬', description: 'Send message to Slack channel', category: 'Communication' },
    { type: 'action', name: 'Call Webhook', icon: '🔗', description: 'Make HTTP request to external URL', category: 'Integration' },
    { type: 'action', name: 'Update Database', icon: '💾', description: 'Update database record', category: 'Data' },
  ];

  const availableTriggers = [
    { name: 'Call Completed', icon: '📞', event: 'call_completed', description: 'When a call ends successfully' },
    { name: 'Call Failed', icon: '❌', event: 'call_failed', description: 'When a call fails to connect' },
    { name: 'Call No Answer', icon: '📵', event: 'call_no_answer', description: 'When recipient doesn\'t answer' },
    { name: 'Call Busy', icon: '📴', event: 'call_busy', description: 'When line is busy' },
    { name: 'Call Voicemail', icon: '📬', event: 'call_voicemail', description: 'When voicemail is reached' },
    { name: 'Campaign Completed', icon: '📊', event: 'campaign_completed', description: 'When a campaign finishes' },
  ];

  const handleAddStep = (position: number) => {
    setInsertPosition(position);
    setShowStepMenu(true);
  };

  const handleSelectAction = (action: any) => {
    const newStep: Step = {
      id: `${action.type}-${Date.now()}`,
      type: action.type as 'filter' | 'action',
      name: action.name,
      icon: action.icon,
      config: {},
      position: insertPosition
    };

    const updatedSteps = [...steps];
    updatedSteps.splice(insertPosition, 0, newStep);
    // Update positions
    updatedSteps.forEach((step, index) => {
      step.position = index;
    });

    updateSteps(updatedSteps);
    setShowStepMenu(false);
    setSelectedStep(newStep.id);
  };

  const handleSelectTrigger = (trigger: any) => {
    const updatedSteps = [...steps];
    updatedSteps[0] = {
      ...updatedSteps[0],
      name: trigger.name,
      icon: trigger.icon,
      config: { trigger_event: trigger.event }
    };
    updateSteps(updatedSteps);
    setSelectedStep(updatedSteps[0].id);
  };

  const handleDeleteStep = (stepId: string) => {
    const updatedSteps = steps.filter(s => s.id !== stepId);
    updatedSteps.forEach((step, index) => {
      step.position = index;
    });
    updateSteps(updatedSteps);
    setSelectedStep(null);
  };

  const handleUpdateStepConfig = (stepId: string, configKey: string, value: any) => {
    const updatedSteps = steps.map(step => {
      if (step.id === stepId) {
        return {
          ...step,
          config: {
            ...step.config,
            [configKey]: value
          }
        };
      }
      return step;
    });
    updateSteps(updatedSteps);
  };

  const getStepDescription = (step: Step): string => {
    if (step.type === 'trigger') {
      const trigger = availableTriggers.find(t => t.event === step.config.trigger_event);
      return trigger?.description || 'Set up your trigger event';
    }

    // Generate smart descriptions based on config
    switch (step.name) {
      case 'Send Email':
        return step.config.to_email
          ? `Send to ${step.config.to_email}${step.config.subject ? ': ' + step.config.subject : ''}`
          : 'Click to configure email settings';

      case 'Create Jira Ticket':
        return step.config.project_key
          ? `Create ticket in ${step.config.project_key}${step.config.summary ? ': ' + step.config.summary : ''}`
          : 'Click to configure Jira ticket';

      case 'Update Jira Ticket':
        return step.config.project_key
          ? `Update ticket in ${step.config.project_key}`
          : 'Click to configure Jira update';

      case 'Create HubSpot Contact':
        return step.config.email
          ? `Create contact: ${step.config.email}`
          : 'Click to configure HubSpot contact';

      case 'Update HubSpot Contact':
        return step.config.email
          ? `Update contact: ${step.config.email}`
          : 'Click to configure HubSpot update';

      case 'Create HubSpot Note':
        return step.config.contact_email
          ? `Add note for ${step.config.contact_email}`
          : 'Click to configure HubSpot note';

      case 'Send Slack Message':
        return step.config.channel
          ? `Send to ${step.config.channel}`
          : 'Click to configure Slack message';

      case 'Call Webhook':
        return step.config.webhook_url
          ? `${step.config.method || 'POST'} ${step.config.webhook_url}`
          : 'Click to configure webhook';

      case 'Update Database':
        return step.config.collection
          ? `Update ${step.config.collection} collection`
          : 'Click to configure database update';

      case 'Filter':
        return step.config.field
          ? `Only continue if ${step.config.field} ${step.config.operator || 'equals'} ${step.config.value || '...'}`
          : 'Click to configure filter conditions';

      case 'Delay':
        if (step.config.delay_seconds) {
          const seconds = step.config.delay_seconds;
          if (seconds < 60) return `Wait ${seconds} seconds`;
          if (seconds < 3600) return `Wait ${Math.floor(seconds / 60)} minutes`;
          if (seconds < 86400) return `Wait ${Math.floor(seconds / 3600)} hours`;
          return `Wait ${Math.floor(seconds / 86400)} days`;
        }
        return 'Click to configure delay duration';

      default:
        return 'Click to configure';
    }
  };

  const renderActionConfiguration = () => {
    const currentStep = steps.find(s => s.id === selectedStep);
    if (!currentStep) return null;

    const inputClass = `w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary ${
      isDarkMode
        ? 'bg-gray-600 border-gray-500 text-white placeholder-gray-400'
        : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
    }`;

    const labelClass = `block text-sm font-medium mb-1 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`;

    switch (currentStep.name) {
      case 'Send Email':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>To Email *</label>
              <input
                type="email"
                placeholder="recipient@example.com"
                value={currentStep.config.to_email || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'to_email', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Subject *</label>
              <input
                type="text"
                placeholder="Email subject"
                value={currentStep.config.subject || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'subject', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Body *</label>
              <textarea
                placeholder="Email content"
                rows={5}
                value={currentStep.config.body || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'body', e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        );

      case 'Create Jira Ticket':
      case 'Update Jira Ticket':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Project Key *</label>
              <input
                type="text"
                placeholder="e.g., PROJ"
                value={currentStep.config.project_key || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'project_key', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Summary *</label>
              <input
                type="text"
                placeholder="Brief description"
                value={currentStep.config.summary || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'summary', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Description</label>
              <textarea
                placeholder="Detailed description"
                rows={4}
                value={currentStep.config.description || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'description', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Issue Type</label>
              <select
                value={currentStep.config.issue_type || 'Task'}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'issue_type', e.target.value)}
                className={inputClass}
              >
                <option value="Task">Task</option>
                <option value="Bug">Bug</option>
                <option value="Story">Story</option>
                <option value="Epic">Epic</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Priority</label>
              <select
                value={currentStep.config.priority || 'Medium'}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'priority', e.target.value)}
                className={inputClass}
              >
                <option value="Highest">Highest</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
                <option value="Lowest">Lowest</option>
              </select>
            </div>
          </div>
        );

      case 'Create HubSpot Contact':
      case 'Update HubSpot Contact':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Email *</label>
              <input
                type="email"
                placeholder="contact@example.com"
                value={currentStep.config.email || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'email', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>First Name</label>
              <input
                type="text"
                placeholder="John"
                value={currentStep.config.first_name || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'first_name', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Last Name</label>
              <input
                type="text"
                placeholder="Doe"
                value={currentStep.config.last_name || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'last_name', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Phone</label>
              <input
                type="tel"
                placeholder="+1234567890"
                value={currentStep.config.phone || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'phone', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Company</label>
              <input
                type="text"
                placeholder="Company Name"
                value={currentStep.config.company || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'company', e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        );

      case 'Create HubSpot Note':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Contact Email *</label>
              <input
                type="email"
                placeholder="contact@example.com"
                value={currentStep.config.contact_email || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'contact_email', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Note Content *</label>
              <textarea
                placeholder="Add your note here..."
                rows={5}
                value={currentStep.config.note_content || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'note_content', e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        );

      case 'Send Slack Message':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Channel *</label>
              <input
                type="text"
                placeholder="#general"
                value={currentStep.config.channel || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'channel', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Message *</label>
              <textarea
                placeholder="Your message..."
                rows={5}
                value={currentStep.config.message || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'message', e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        );

      case 'Call Webhook':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Webhook URL *</label>
              <input
                type="url"
                placeholder="https://example.com/webhook"
                value={currentStep.config.webhook_url || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'webhook_url', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>HTTP Method</label>
              <select
                value={currentStep.config.method || 'POST'}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'method', e.target.value)}
                className={inputClass}
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="PATCH">PATCH</option>
                <option value="DELETE">DELETE</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Headers (JSON)</label>
              <textarea
                placeholder='{"Content-Type": "application/json"}'
                rows={3}
                value={currentStep.config.headers || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'headers', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Body (JSON)</label>
              <textarea
                placeholder='{"key": "value"}'
                rows={4}
                value={currentStep.config.body || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'body', e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        );

      case 'Update Database':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Collection/Table *</label>
              <input
                type="text"
                placeholder="e.g., contacts"
                value={currentStep.config.collection || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'collection', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Filter Query (JSON) *</label>
              <textarea
                placeholder='{"_id": "12345"}'
                rows={3}
                value={currentStep.config.filter || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'filter', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Update Data (JSON) *</label>
              <textarea
                placeholder='{"status": "completed"}'
                rows={4}
                value={currentStep.config.update_data || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'update_data', e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        );

      case 'Filter':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Field to Check *</label>
              <input
                type="text"
                placeholder="e.g., call_duration"
                value={currentStep.config.field || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'field', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Condition *</label>
              <select
                value={currentStep.config.operator || 'equals'}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'operator', e.target.value)}
                className={inputClass}
              >
                <option value="equals">Equals</option>
                <option value="not_equals">Not Equals</option>
                <option value="greater_than">Greater Than</option>
                <option value="less_than">Less Than</option>
                <option value="contains">Contains</option>
                <option value="not_contains">Does Not Contain</option>
                <option value="starts_with">Starts With</option>
                <option value="ends_with">Ends With</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Value *</label>
              <input
                type="text"
                placeholder="Value to compare"
                value={currentStep.config.value || ''}
                onChange={(e) => handleUpdateStepConfig(currentStep.id, 'value', e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        );

      case 'Delay':
        return (
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Delay Duration *</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min="1"
                  placeholder="Enter amount"
                  value={currentStep.config.delay_amount || ''}
                  onChange={(e) => {
                    const amount = parseInt(e.target.value) || 1;
                    const unit = currentStep.config.delay_unit || 'minutes';
                    let seconds = amount;
                    if (unit === 'minutes') seconds = amount * 60;
                    else if (unit === 'hours') seconds = amount * 3600;
                    else if (unit === 'days') seconds = amount * 86400;
                    handleUpdateStepConfig(currentStep.id, 'delay_amount', amount);
                    handleUpdateStepConfig(currentStep.id, 'delay_seconds', seconds);
                  }}
                  className={`flex-1 ${inputClass}`}
                />
                <select
                  value={currentStep.config.delay_unit || 'minutes'}
                  onChange={(e) => {
                    const unit = e.target.value;
                    const amount = currentStep.config.delay_amount || 1;
                    let seconds = amount;
                    if (unit === 'minutes') seconds = amount * 60;
                    else if (unit === 'hours') seconds = amount * 3600;
                    else if (unit === 'days') seconds = amount * 86400;
                    handleUpdateStepConfig(currentStep.id, 'delay_unit', unit);
                    handleUpdateStepConfig(currentStep.id, 'delay_seconds', seconds);
                  }}
                  className={`w-32 ${inputClass}`}
                >
                  <option value="seconds">Seconds</option>
                  <option value="minutes">Minutes</option>
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                </select>
              </div>
              <p className={`text-xs mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                Workflow will pause for the specified duration before continuing to the next action
              </p>
            </div>
            <div className={`p-3 rounded-lg ${isDarkMode ? 'bg-blue-900/20 border border-blue-800' : 'bg-blue-50 border border-blue-200'}`}>
              <p className={`text-sm ${isDarkMode ? 'text-blue-300' : 'text-blue-700'}`}>
                <strong>Note:</strong> Delayed actions are processed by background workers. Make sure the Celery worker is running.
              </p>
            </div>
          </div>
        );

      default:
        return (
          <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-gray-700' : 'bg-gray-50'}`}>
            <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
              Configuration options for {currentStep.name} will be available soon.
            </p>
          </div>
        );
    }
  };

  return (
    <div className="flex h-full">
      {/* Main Canvas */}
      <div className={`flex-1 ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'} overflow-auto`}>
        <div className="max-w-2xl mx-auto py-12 px-4">
          {/* Steps */}
          <div className="space-y-4">
            {steps.map((step, index) => (
              <div key={step.id}>
                {/* Step Card */}
                <div
                  onClick={() => setSelectedStep(step.id)}
                  className={`relative rounded-xl border-2 transition-all cursor-pointer ${
                    selectedStep === step.id
                      ? isDarkMode
                        ? 'border-purple-500 bg-gray-800'
                        : 'border-purple-500 bg-white shadow-lg'
                      : isDarkMode
                      ? 'border-gray-700 bg-gray-800 hover:border-gray-600'
                      : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-md'
                  }`}
                >
                  {/* Step Number Badge */}
                  <div className={`absolute -left-3 -top-3 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                    step.type === 'trigger'
                      ? 'bg-orange-500 text-white'
                      : step.type === 'filter'
                      ? 'bg-blue-500 text-white'
                      : 'bg-purple-500 text-white'
                  }`}>
                    {index + 1}
                  </div>

                  <div className="p-6">
                    <div className="flex items-start gap-4">
                      {/* Icon */}
                      <div className={`text-4xl flex-shrink-0`}>
                        {step.icon}
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className={`text-xs font-semibold uppercase tracking-wider mb-2 ${
                          step.type === 'trigger'
                            ? 'text-orange-500'
                            : step.type === 'filter'
                            ? 'text-blue-500'
                            : 'text-purple-500'
                        }`}>
                          {step.type === 'trigger' ? 'Trigger' : step.type === 'filter' ? 'Filter' : 'Action'}
                        </div>
                        <h3 className={`text-lg font-semibold mb-1 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                          {step.name}
                        </h3>
                        <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                          {getStepDescription(step)}
                        </p>
                      </div>

                      {/* Delete Button */}
                      {step.type !== 'trigger' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteStep(step.id);
                          }}
                          className={`p-2 rounded-lg transition-colors ${
                            isDarkMode
                              ? 'text-gray-400 hover:text-red-400 hover:bg-gray-700'
                              : 'text-gray-400 hover:text-red-500 hover:bg-gray-100'
                          }`}
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Connector Line */}
                {index < steps.length - 1 && (
                  <div className="flex justify-center py-2">
                    <div className={`w-0.5 h-8 ${isDarkMode ? 'bg-gray-700' : 'bg-gray-300'}`}></div>
                  </div>
                )}

                {/* Add Step Button */}
                <div className="flex justify-center py-4">
                  <button
                    onClick={() => handleAddStep(index + 1)}
                    className={`group flex items-center gap-2 px-4 py-2 rounded-full border-2 border-dashed transition-all ${
                      isDarkMode
                        ? 'border-gray-700 text-gray-400 hover:border-purple-500 hover:text-purple-400 hover:bg-gray-800'
                        : 'border-gray-300 text-gray-500 hover:border-purple-500 hover:text-purple-600 hover:bg-purple-50'
                    }`}
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span className="text-sm font-medium">Add Step</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Sidebar - Step Configuration */}
      {selectedStep && (
        <div className={`w-96 border-l ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} overflow-auto`}>
          <div className="p-6">
            {steps.find(s => s.id === selectedStep)?.type === 'trigger' ? (
              <>
                <h2 className={`text-xl font-bold mb-4 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Choose Trigger Event
                </h2>
                <p className={`text-sm mb-6 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  Select the event that will start this workflow
                </p>
                <div className="space-y-2">
                  {availableTriggers.map((trigger) => (
                    <button
                      key={trigger.event}
                      onClick={() => handleSelectTrigger(trigger)}
                      className={`w-full text-left p-4 rounded-lg border transition-all ${
                        steps[0].config.trigger_event === trigger.event
                          ? isDarkMode
                            ? 'border-purple-500 bg-purple-900/20'
                            : 'border-purple-500 bg-purple-50'
                          : isDarkMode
                          ? 'border-gray-700 hover:border-gray-600 hover:bg-gray-700'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{trigger.icon}</span>
                        <span className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                          {trigger.name}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <h2 className={`text-xl font-bold mb-4 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Configure Step
                </h2>
                <p className={`text-sm mb-6 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  Set up this action step
                </p>
                {renderActionConfiguration()}
              </>
            )}
          </div>
        </div>
      )}

      {/* Step Selection Menu Modal */}
      {showStepMenu && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className={`max-w-2xl w-full rounded-xl ${isDarkMode ? 'bg-gray-800' : 'bg-white'} max-h-[80vh] overflow-auto`}>
            <div className={`sticky top-0 p-6 border-b ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                    Choose an Action
                  </h2>
                  <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                    Select what should happen at this step
                  </p>
                </div>
                <button
                  onClick={() => setShowStepMenu(false)}
                  className={`p-2 rounded-lg ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
                >
                  <svg className={`w-6 h-6 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="p-6 space-y-3">
              {availableActions.map((action) => (
                <button
                  key={`${action.type}-${action.name}`}
                  onClick={() => handleSelectAction(action)}
                  className={`w-full text-left p-4 rounded-xl border-2 transition-all ${
                    isDarkMode
                      ? 'border-gray-700 hover:border-purple-500 hover:bg-gray-700'
                      : 'border-gray-200 hover:border-purple-500 hover:bg-purple-50'
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className="text-3xl flex-shrink-0">{action.icon}</div>
                    <div className="flex-1">
                      <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                        {action.name}
                      </h3>
                      <p className={`text-sm mt-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                        {action.description}
                      </p>
                    </div>
                    <svg className={`w-5 h-5 flex-shrink-0 ${isDarkMode ? 'text-gray-600' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
