'use client';

import { useState, useEffect } from 'react';
import { Node } from 'reactflow';

interface NodeConfigPanelProps {
  selectedNode: Node | null;
  onUpdateNode: (nodeId: string, data: any) => void;
  onClose: () => void;
}

export function NodeConfigPanel({
  selectedNode,
  onUpdateNode,
  onClose,
}: NodeConfigPanelProps) {
  const [config, setConfig] = useState<Record<string, any>>({});

  useEffect(() => {
    if (selectedNode) {
      setConfig(selectedNode.data.config || {});
    }
  }, [selectedNode]);

  if (!selectedNode) return null;

  const handleChange = (key: string, value: any) => {
    const newConfig = { ...config, [key]: value };
    setConfig(newConfig);
    onUpdateNode(selectedNode.id, { ...selectedNode.data, config: newConfig });
  };

  const inputClass =
    'w-full px-3 py-2 text-sm rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent';
  const labelClass = 'block text-sm font-medium text-gray-300 mb-1';
  const helpClass = 'text-xs text-gray-500 mt-1';

  // ==================== TRIGGER CONFIGS ====================
  const renderTriggerConfig = () => {
    const triggerType = selectedNode.data.triggerType;

    return (
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Trigger Type</label>
          <p className="text-sm text-gray-400 capitalize">
            {triggerType?.replace(/_/g, ' ')}
          </p>
        </div>

        {triggerType === 'webhook' && (
          <>
            <div>
              <label className={labelClass}>Webhook Path</label>
              <input
                type="text"
                value={config.webhook_path || ''}
                onChange={(e) => handleChange('webhook_path', e.target.value)}
                placeholder="/my-webhook"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>HTTP Method</label>
              <select
                value={config.method || 'POST'}
                onChange={(e) => handleChange('method', e.target.value)}
                className={inputClass}
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Authentication</label>
              <select
                value={config.auth_type || 'none'}
                onChange={(e) => handleChange('auth_type', e.target.value)}
                className={inputClass}
              >
                <option value="none">None</option>
                <option value="header">Header Token</option>
                <option value="basic">Basic Auth</option>
              </select>
            </div>
          </>
        )}

        {triggerType === 'schedule' && (
          <>
            <div>
              <label className={labelClass}>Schedule Type</label>
              <select
                value={config.schedule_type || 'cron'}
                onChange={(e) => handleChange('schedule_type', e.target.value)}
                className={inputClass}
              >
                <option value="cron">Cron Expression</option>
                <option value="interval">Interval</option>
              </select>
            </div>
            {config.schedule_type === 'interval' ? (
              <div className="flex gap-2">
                <input
                  type="number"
                  min="1"
                  value={config.interval_value || ''}
                  onChange={(e) => handleChange('interval_value', e.target.value)}
                  placeholder="5"
                  className={`flex-1 ${inputClass}`}
                />
                <select
                  value={config.interval_unit || 'minutes'}
                  onChange={(e) => handleChange('interval_unit', e.target.value)}
                  className={`w-28 ${inputClass}`}
                >
                  <option value="seconds">Seconds</option>
                  <option value="minutes">Minutes</option>
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                </select>
              </div>
            ) : (
              <div>
                <label className={labelClass}>Cron Expression</label>
                <input
                  type="text"
                  value={config.cron || ''}
                  onChange={(e) => handleChange('cron', e.target.value)}
                  placeholder="0 * * * *"
                  className={inputClass}
                />
                <p className={helpClass}>
                  e.g., "0 9 * * *" for daily at 9 AM, "*/5 * * * *" for every 5 min
                </p>
              </div>
            )}
            <div>
              <label className={labelClass}>Timezone</label>
              <select
                value={config.timezone || 'UTC'}
                onChange={(e) => handleChange('timezone', e.target.value)}
                className={inputClass}
              >
                <option value="UTC">UTC</option>
                <option value="America/New_York">Eastern Time</option>
                <option value="America/Los_Angeles">Pacific Time</option>
                <option value="Europe/London">London</option>
                <option value="Asia/Tokyo">Tokyo</option>
              </select>
            </div>
          </>
        )}

        {(triggerType === 'call_completed' || triggerType === 'call_failed') && (
          <div>
            <label className={labelClass}>Filter by Campaign (optional)</label>
            <input
              type="text"
              value={config.campaign_id || ''}
              onChange={(e) => handleChange('campaign_id', e.target.value)}
              placeholder="Campaign ID to filter"
              className={inputClass}
            />
          </div>
        )}
      </div>
    );
  };

  // ==================== CONDITION CONFIGS ====================
  const renderConditionConfig = () => {
    const conditionType = selectedNode.data.conditionType;

    return (
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Condition Type</label>
          <p className="text-sm text-gray-400 capitalize">
            {conditionType?.replace(/_/g, ' ')}
          </p>
        </div>

        {(conditionType === 'if' || conditionType === 'filter' || conditionType === 'validation') && (
          <>
            <div>
              <label className={labelClass}>Field to Check *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="e.g., sentiment, call_duration, data.email"
                className={inputClass}
              />
              <p className={helpClass}>Use dot notation for nested fields</p>
            </div>
            <div>
              <label className={labelClass}>Operator *</label>
              <select
                value={config.operator || 'equals'}
                onChange={(e) => handleChange('operator', e.target.value)}
                className={inputClass}
              >
                <option value="equals">Equals</option>
                <option value="not_equals">Not Equals</option>
                <option value="greater_than">Greater Than</option>
                <option value="greater_than_or_equals">Greater Than or Equals</option>
                <option value="less_than">Less Than</option>
                <option value="less_than_or_equals">Less Than or Equals</option>
                <option value="contains">Contains</option>
                <option value="not_contains">Does Not Contain</option>
                <option value="starts_with">Starts With</option>
                <option value="ends_with">Ends With</option>
                <option value="regex">Matches Regex</option>
                <option value="is_empty">Is Empty</option>
                <option value="is_not_empty">Is Not Empty</option>
                <option value="is_true">Is True</option>
                <option value="is_false">Is False</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Value</label>
              <input
                type="text"
                value={config.value || ''}
                onChange={(e) => handleChange('value', e.target.value)}
                placeholder="Value to compare"
                className={inputClass}
              />
            </div>
          </>
        )}

        {conditionType === 'switch' && (
          <>
            <div>
              <label className={labelClass}>Field to Switch On *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="e.g., status, type"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Cases (one per line)</label>
              <textarea
                value={config.cases_text || ''}
                onChange={(e) => {
                  handleChange('cases_text', e.target.value);
                  const cases = e.target.value.split('\n').filter(c => c.trim()).map(c => ({ value: c.trim() }));
                  handleChange('cases', cases);
                }}
                placeholder="success&#10;failed&#10;pending"
                rows={4}
                className={inputClass}
              />
              <p className={helpClass}>Each case creates an output handle</p>
            </div>
          </>
        )}

        {conditionType === 'dedup' && (
          <>
            <div>
              <label className={labelClass}>Dedup Key Field *</label>
              <input
                type="text"
                value={config.dedup_key || ''}
                onChange={(e) => handleChange('dedup_key', e.target.value)}
                placeholder="e.g., email, id"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Time Window (hours)</label>
              <input
                type="number"
                min="1"
                value={config.time_window_hours || ''}
                onChange={(e) => handleChange('time_window_hours', e.target.value)}
                placeholder="24"
                className={inputClass}
              />
              <p className={helpClass}>Check duplicates within this time window</p>
            </div>
          </>
        )}

        {conditionType === 'regex' && (
          <>
            <div>
              <label className={labelClass}>Field *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="Field to match"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Regex Pattern *</label>
              <input
                type="text"
                value={config.pattern || ''}
                onChange={(e) => handleChange('pattern', e.target.value)}
                placeholder="^[a-zA-Z0-9]+$"
                className={inputClass}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="case_insensitive"
                checked={config.case_insensitive || false}
                onChange={(e) => handleChange('case_insensitive', e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-purple-500"
              />
              <label htmlFor="case_insensitive" className="text-sm text-gray-300">
                Case insensitive
              </label>
            </div>
          </>
        )}
      </div>
    );
  };

  // ==================== CODE/DATA CONFIGS ====================
  const renderCodeConfig = () => {
    const codeType = selectedNode.data.codeType;

    return (
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Node Type</label>
          <p className="text-sm text-gray-400 capitalize">
            {codeType?.replace(/_/g, ' ')}
          </p>
        </div>

        {codeType === 'custom' && (
          <>
            <div>
              <label className={labelClass}>JavaScript Code *</label>
              <textarea
                value={config.code || ''}
                onChange={(e) => handleChange('code', e.target.value)}
                placeholder="// Access input data via 'input' variable&#10;// Return data to pass to next node&#10;return { ...input, processed: true };"
                rows={12}
                className={`${inputClass} font-mono text-xs`}
              />
            </div>
            <div>
              <label className={labelClass}>Output Variable Name</label>
              <input
                type="text"
                value={config.output_variable || ''}
                onChange={(e) => handleChange('output_variable', e.target.value)}
                placeholder="result"
                className={inputClass}
              />
            </div>
          </>
        )}

        {codeType === 'set' && (
          <>
            <div>
              <label className={labelClass}>Field to Set *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="e.g., status, data.processed"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Value *</label>
              <input
                type="text"
                value={config.value || ''}
                onChange={(e) => handleChange('value', e.target.value)}
                placeholder="Value or {{field}} for dynamic"
                className={inputClass}
              />
            </div>
          </>
        )}

        {codeType === 'extract_fields' && (
          <div>
            <label className={labelClass}>Fields to Extract (comma-separated) *</label>
            <input
              type="text"
              value={config.fields || ''}
              onChange={(e) => handleChange('fields', e.target.value)}
              placeholder="email, name, phone, data.nested.field"
              className={inputClass}
            />
          </div>
        )}

        {codeType === 'rename_keys' && (
          <div>
            <label className={labelClass}>Key Mappings (JSON)</label>
            <textarea
              value={config.mappings || ''}
              onChange={(e) => handleChange('mappings', e.target.value)}
              placeholder='{"old_name": "new_name", "email": "user_email"}'
              rows={4}
              className={`${inputClass} font-mono text-xs`}
            />
          </div>
        )}

        {codeType === 'merge' && (
          <div>
            <label className={labelClass}>Merge Mode</label>
            <select
              value={config.merge_mode || 'append'}
              onChange={(e) => handleChange('merge_mode', e.target.value)}
              className={inputClass}
            >
              <option value="append">Append All</option>
              <option value="combine">Combine by Key</option>
              <option value="keep_key">Keep Matching Keys</option>
            </select>
          </div>
        )}

        {codeType === 'split' && (
          <>
            <div>
              <label className={labelClass}>Field to Split *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="Array field to split"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Batch Size</label>
              <input
                type="number"
                min="1"
                value={config.batch_size || ''}
                onChange={(e) => handleChange('batch_size', e.target.value)}
                placeholder="1"
                className={inputClass}
              />
            </div>
          </>
        )}

        {codeType === 'aggregate' && (
          <>
            <div>
              <label className={labelClass}>Operation</label>
              <select
                value={config.operation || 'count'}
                onChange={(e) => handleChange('operation', e.target.value)}
                className={inputClass}
              >
                <option value="count">Count</option>
                <option value="sum">Sum</option>
                <option value="average">Average</option>
                <option value="min">Minimum</option>
                <option value="max">Maximum</option>
                <option value="concat">Concatenate</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Field (for sum/avg/min/max)</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="Field to aggregate"
                className={inputClass}
              />
            </div>
          </>
        )}

        {codeType === 'sort' && (
          <>
            <div>
              <label className={labelClass}>Sort By Field *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="Field to sort by"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Order</label>
              <select
                value={config.order || 'asc'}
                onChange={(e) => handleChange('order', e.target.value)}
                className={inputClass}
              >
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </div>
          </>
        )}

        {codeType === 'limit' && (
          <div>
            <label className={labelClass}>Max Items *</label>
            <input
              type="number"
              min="1"
              value={config.limit || ''}
              onChange={(e) => handleChange('limit', e.target.value)}
              placeholder="10"
              className={inputClass}
            />
          </div>
        )}

        {codeType === 'generate_key' && (
          <>
            <div>
              <label className={labelClass}>Key Prefix</label>
              <input
                type="text"
                value={config.prefix || ''}
                onChange={(e) => handleChange('prefix', e.target.value)}
                placeholder="key"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Output Variable</label>
              <input
                type="text"
                value={config.output_variable || 'generated_key'}
                onChange={(e) => handleChange('output_variable', e.target.value)}
                className={inputClass}
              />
            </div>
          </>
        )}

        {codeType === 'increment' && (
          <>
            <div>
              <label className={labelClass}>Counter Name *</label>
              <input
                type="text"
                value={config.counter_name || ''}
                onChange={(e) => handleChange('counter_name', e.target.value)}
                placeholder="my_counter"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Increment By</label>
              <input
                type="number"
                value={config.increment_by || 1}
                onChange={(e) => handleChange('increment_by', parseInt(e.target.value) || 1)}
                className={inputClass}
              />
            </div>
          </>
        )}

        {codeType === 'datetime' && (
          <>
            <div>
              <label className={labelClass}>Operation</label>
              <select
                value={config.operation || 'format'}
                onChange={(e) => handleChange('operation', e.target.value)}
                className={inputClass}
              >
                <option value="format">Format Date</option>
                <option value="add">Add Time</option>
                <option value="subtract">Subtract Time</option>
                <option value="difference">Calculate Difference</option>
                <option value="now">Current Time</option>
              </select>
            </div>
            {config.operation === 'format' && (
              <div>
                <label className={labelClass}>Format</label>
                <input
                  type="text"
                  value={config.format || ''}
                  onChange={(e) => handleChange('format', e.target.value)}
                  placeholder="YYYY-MM-DD HH:mm:ss"
                  className={inputClass}
                />
              </div>
            )}
          </>
        )}

        {codeType === 'crypto' && (
          <>
            <div>
              <label className={labelClass}>Operation</label>
              <select
                value={config.operation || 'hash'}
                onChange={(e) => handleChange('operation', e.target.value)}
                className={inputClass}
              >
                <option value="hash">Hash (SHA256)</option>
                <option value="md5">MD5</option>
                <option value="base64_encode">Base64 Encode</option>
                <option value="base64_decode">Base64 Decode</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Input Field *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="Field to process"
                className={inputClass}
              />
            </div>
          </>
        )}
      </div>
    );
  };

  // ==================== ACTION CONFIGS ====================
  const renderEmailConfig = () => (
    <div className="space-y-4">
      <div>
        <label className={labelClass}>To Email *</label>
        <input
          type="email"
          value={config.to_email || ''}
          onChange={(e) => handleChange('to_email', e.target.value)}
          placeholder="recipient@example.com or {{customer_email}}"
          className={inputClass}
        />
        <p className={helpClass}>Use {'{{field}}'} for dynamic values</p>
      </div>
      <div>
        <label className={labelClass}>CC (optional)</label>
        <input
          type="text"
          value={config.cc || ''}
          onChange={(e) => handleChange('cc', e.target.value)}
          placeholder="cc@example.com"
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Subject *</label>
        <input
          type="text"
          value={config.subject || ''}
          onChange={(e) => handleChange('subject', e.target.value)}
          placeholder="Email subject"
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Body *</label>
        <textarea
          value={config.body || ''}
          onChange={(e) => handleChange('body', e.target.value)}
          placeholder="Email content... Use {{field}} for dynamic values"
          rows={6}
          className={inputClass}
        />
      </div>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="include_summary"
            checked={config.include_summary || false}
            onChange={(e) => handleChange('include_summary', e.target.checked)}
            className="rounded border-gray-700 bg-gray-800 text-purple-500"
          />
          <label htmlFor="include_summary" className="text-sm text-gray-300">
            Include call summary
          </label>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="include_transcript"
            checked={config.include_transcript || false}
            onChange={(e) => handleChange('include_transcript', e.target.checked)}
            className="rounded border-gray-700 bg-gray-800 text-purple-500"
          />
          <label htmlFor="include_transcript" className="text-sm text-gray-300">
            Include transcript
          </label>
        </div>
      </div>
    </div>
  );

  const renderSlackConfig = () => (
    <div className="space-y-4">
      <div>
        <label className={labelClass}>Webhook URL *</label>
        <input
          type="url"
          value={config.webhook_url || ''}
          onChange={(e) => handleChange('webhook_url', e.target.value)}
          placeholder="https://hooks.slack.com/services/..."
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Channel (optional)</label>
        <input
          type="text"
          value={config.channel || ''}
          onChange={(e) => handleChange('channel', e.target.value)}
          placeholder="#channel-name"
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Message *</label>
        <textarea
          value={config.message || ''}
          onChange={(e) => handleChange('message', e.target.value)}
          placeholder="Message to send... Use {{field}} for dynamic values"
          rows={4}
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Username (optional)</label>
        <input
          type="text"
          value={config.username || ''}
          onChange={(e) => handleChange('username', e.target.value)}
          placeholder="Bot username"
          className={inputClass}
        />
      </div>
    </div>
  );

  const renderHttpConfig = () => (
    <div className="space-y-4">
      <div>
        <label className={labelClass}>URL *</label>
        <input
          type="url"
          value={config.url || ''}
          onChange={(e) => handleChange('url', e.target.value)}
          placeholder="https://api.example.com/endpoint"
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Method</label>
        <select
          value={config.method || 'POST'}
          onChange={(e) => handleChange('method', e.target.value)}
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
          value={config.headers || ''}
          onChange={(e) => handleChange('headers', e.target.value)}
          placeholder='{"Authorization": "Bearer xxx", "Content-Type": "application/json"}'
          rows={3}
          className={`${inputClass} font-mono text-xs`}
        />
      </div>
      <div>
        <label className={labelClass}>Body (JSON)</label>
        <textarea
          value={config.body || ''}
          onChange={(e) => handleChange('body', e.target.value)}
          placeholder='{"key": "{{value}}"}'
          rows={5}
          className={`${inputClass} font-mono text-xs`}
        />
      </div>
      <div>
        <label className={labelClass}>Timeout (seconds)</label>
        <input
          type="number"
          min="1"
          max="300"
          value={config.timeout || ''}
          onChange={(e) => handleChange('timeout', e.target.value)}
          placeholder="30"
          className={inputClass}
        />
      </div>
    </div>
  );

  const renderDatabaseConfig = () => {
    const actionType = selectedNode.data.actionType;

    return (
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Database Type</label>
          <p className="text-sm text-gray-400 capitalize">
            {actionType?.replace(/_/g, ' ')}
          </p>
        </div>
        <div>
          <label className={labelClass}>Connection String *</label>
          <input
            type="password"
            value={config.connection_string || ''}
            onChange={(e) => handleChange('connection_string', e.target.value)}
            placeholder="Connection string or use integration"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Operation</label>
          <select
            value={config.operation || 'query'}
            onChange={(e) => handleChange('operation', e.target.value)}
            className={inputClass}
          >
            <option value="query">Query</option>
            <option value="insert">Insert</option>
            <option value="update">Update</option>
            <option value="delete">Delete</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>Table/Collection *</label>
          <input
            type="text"
            value={config.table || ''}
            onChange={(e) => handleChange('table', e.target.value)}
            placeholder="Table or collection name"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Query/Data (JSON)</label>
          <textarea
            value={config.query || ''}
            onChange={(e) => handleChange('query', e.target.value)}
            placeholder='{"field": "value"}'
            rows={4}
            className={`${inputClass} font-mono text-xs`}
          />
        </div>
      </div>
    );
  };

  const renderAIConfig = () => {
    const actionType = selectedNode.data.actionType;

    return (
      <div className="space-y-4">
        <div>
          <label className={labelClass}>AI Provider</label>
          <p className="text-sm text-gray-400 capitalize">
            {actionType?.replace(/_/g, ' ')}
          </p>
        </div>
        <div>
          <label className={labelClass}>API Key *</label>
          <input
            type="password"
            value={config.api_key || ''}
            onChange={(e) => handleChange('api_key', e.target.value)}
            placeholder="API key or use integration"
            className={inputClass}
          />
        </div>
        {(actionType === 'openai' || actionType === 'anthropic') && (
          <>
            <div>
              <label className={labelClass}>Model</label>
              <select
                value={config.model || ''}
                onChange={(e) => handleChange('model', e.target.value)}
                className={inputClass}
              >
                {actionType === 'openai' ? (
                  <>
                    <option value="gpt-4o">GPT-4o</option>
                    <option value="gpt-4o-mini">GPT-4o Mini</option>
                    <option value="gpt-4-turbo">GPT-4 Turbo</option>
                    <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                  </>
                ) : (
                  <>
                    <option value="claude-3-opus-20240229">Claude 3 Opus</option>
                    <option value="claude-3-sonnet-20240229">Claude 3 Sonnet</option>
                    <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
                  </>
                )}
              </select>
            </div>
            <div>
              <label className={labelClass}>Prompt *</label>
              <textarea
                value={config.prompt || ''}
                onChange={(e) => handleChange('prompt', e.target.value)}
                placeholder="Enter your prompt... Use {{field}} for dynamic values"
                rows={6}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>System Prompt (optional)</label>
              <textarea
                value={config.system_prompt || ''}
                onChange={(e) => handleChange('system_prompt', e.target.value)}
                placeholder="System instructions..."
                rows={3}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Max Tokens</label>
              <input
                type="number"
                min="1"
                max="4096"
                value={config.max_tokens || ''}
                onChange={(e) => handleChange('max_tokens', e.target.value)}
                placeholder="1000"
                className={inputClass}
              />
            </div>
          </>
        )}
        {actionType === 'summarize' && (
          <>
            <div>
              <label className={labelClass}>Text Field *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="Field containing text to summarize"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Max Length (words)</label>
              <input
                type="number"
                value={config.max_length || ''}
                onChange={(e) => handleChange('max_length', e.target.value)}
                placeholder="100"
                className={inputClass}
              />
            </div>
          </>
        )}
        {actionType === 'translate' && (
          <>
            <div>
              <label className={labelClass}>Text Field *</label>
              <input
                type="text"
                value={config.field || ''}
                onChange={(e) => handleChange('field', e.target.value)}
                placeholder="Field to translate"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Target Language *</label>
              <select
                value={config.target_language || ''}
                onChange={(e) => handleChange('target_language', e.target.value)}
                className={inputClass}
              >
                <option value="">Select language</option>
                <option value="en">English</option>
                <option value="es">Spanish</option>
                <option value="fr">French</option>
                <option value="de">German</option>
                <option value="it">Italian</option>
                <option value="pt">Portuguese</option>
                <option value="ja">Japanese</option>
                <option value="ko">Korean</option>
                <option value="zh">Chinese</option>
              </select>
            </div>
          </>
        )}
      </div>
    );
  };

  const renderDelayConfig = () => (
    <div className="space-y-4">
      <div>
        <label className={labelClass}>Delay Duration</label>
        <div className="flex gap-2">
          <input
            type="number"
            min="1"
            value={config.delay_amount || ''}
            onChange={(e) => {
              const amount = parseInt(e.target.value) || 1;
              const unit = config.delay_unit || 'minutes';
              let seconds = amount;
              if (unit === 'minutes') seconds = amount * 60;
              else if (unit === 'hours') seconds = amount * 3600;
              else if (unit === 'days') seconds = amount * 86400;
              handleChange('delay_amount', amount);
              handleChange('delay_seconds', seconds);
            }}
            placeholder="Amount"
            className={`flex-1 ${inputClass}`}
          />
          <select
            value={config.delay_unit || 'minutes'}
            onChange={(e) => {
              const unit = e.target.value;
              const amount = config.delay_amount || 1;
              let seconds = amount;
              if (unit === 'minutes') seconds = amount * 60;
              else if (unit === 'hours') seconds = amount * 3600;
              else if (unit === 'days') seconds = amount * 86400;
              handleChange('delay_unit', unit);
              handleChange('delay_seconds', seconds);
            }}
            className={`w-28 ${inputClass}`}
          >
            <option value="seconds">Seconds</option>
            <option value="minutes">Minutes</option>
            <option value="hours">Hours</option>
            <option value="days">Days</option>
          </select>
        </div>
      </div>
    </div>
  );

  const renderLoopConfig = () => (
    <div className="space-y-4">
      <div>
        <label className={labelClass}>Array Field to Loop *</label>
        <input
          type="text"
          value={config.array_field || ''}
          onChange={(e) => handleChange('array_field', e.target.value)}
          placeholder="items, data.results"
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Item Variable Name</label>
        <input
          type="text"
          value={config.item_variable || 'item'}
          onChange={(e) => handleChange('item_variable', e.target.value)}
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Max Iterations</label>
        <input
          type="number"
          min="1"
          value={config.max_iterations || ''}
          onChange={(e) => handleChange('max_iterations', e.target.value)}
          placeholder="100"
          className={inputClass}
        />
      </div>
    </div>
  );

  const renderGenericConfig = () => {
    const actionType = selectedNode.data.actionType;

    return (
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Action Type</label>
          <p className="text-sm text-gray-400 capitalize">
            {actionType?.replace(/_/g, ' ')}
          </p>
        </div>
        <div className="p-4 bg-gray-800/50 rounded-lg">
          <p className="text-sm text-gray-400">
            This node requires an integration to be configured. Go to Settings → Integrations to connect your {actionType?.replace(/_/g, ' ')} account.
          </p>
        </div>
        <div>
          <label className={labelClass}>Integration</label>
          <select
            value={config.integration_id || ''}
            onChange={(e) => handleChange('integration_id', e.target.value)}
            className={inputClass}
          >
            <option value="">Select integration...</option>
          </select>
        </div>
      </div>
    );
  };

  const renderResponseConfig = () => (
    <div className="space-y-4">
      <div>
        <label className={labelClass}>Response Type</label>
        <p className="text-sm text-gray-400 capitalize">
          {config.responseType || selectedNode.data.config?.responseType || 'OK'}
        </p>
      </div>
      <div>
        <label className={labelClass}>Custom Message (optional)</label>
        <input
          type="text"
          value={config.message || ''}
          onChange={(e) => handleChange('message', e.target.value)}
          placeholder="Custom response message"
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Response Data (JSON, optional)</label>
        <textarea
          value={config.response_data || ''}
          onChange={(e) => handleChange('response_data', e.target.value)}
          placeholder='{"status": "success"}'
          rows={3}
          className={`${inputClass} font-mono text-xs`}
        />
      </div>
    </div>
  );

  // ==================== AI AGENT TRIGGER CONFIGS ====================
  const renderAIAgentTriggerConfig = () => {
    const triggerType = selectedNode.data.triggerType;

    return (
      <div className="space-y-4">
        <div className="p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg">
          <p className="text-xs text-purple-300">
            This trigger fires during an active AI agent call based on the specified conditions.
          </p>
        </div>

        {triggerType === 'ai_agent_intent' && (
          <>
            <div>
              <label className={labelClass}>Intent to Detect *</label>
              <select
                value={config.intent || ''}
                onChange={(e) => handleChange('intent', e.target.value)}
                className={inputClass}
              >
                <option value="">Select intent...</option>
                <option value="booking">Booking/Appointment</option>
                <option value="pricing">Pricing Inquiry</option>
                <option value="support">Support Request</option>
                <option value="complaint">Complaint</option>
                <option value="sales">Sales Inquiry</option>
                <option value="cancellation">Cancellation</option>
                <option value="refund">Refund Request</option>
                <option value="feedback">Feedback</option>
                <option value="custom">Custom Intent</option>
              </select>
            </div>
            {config.intent === 'custom' && (
              <div>
                <label className={labelClass}>Custom Intent Name *</label>
                <input
                  type="text"
                  value={config.custom_intent || ''}
                  onChange={(e) => handleChange('custom_intent', e.target.value)}
                  placeholder="e.g., request_demo"
                  className={inputClass}
                />
              </div>
            )}
            <div>
              <label className={labelClass}>Confidence Threshold</label>
              <input
                type="number"
                min="0"
                max="100"
                value={config.confidence_threshold || 70}
                onChange={(e) => handleChange('confidence_threshold', e.target.value)}
                className={inputClass}
              />
              <p className={helpClass}>Minimum confidence % to trigger (0-100)</p>
            </div>
          </>
        )}

        {triggerType === 'ai_agent_keyword' && (
          <>
            <div>
              <label className={labelClass}>Keywords *</label>
              <input
                type="text"
                value={config.keywords || ''}
                onChange={(e) => handleChange('keywords', e.target.value)}
                placeholder="manager, supervisor, human, cancel"
                className={inputClass}
              />
              <p className={helpClass}>Comma-separated keywords to detect</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="match_exact"
                checked={config.match_exact || false}
                onChange={(e) => handleChange('match_exact', e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-purple-500"
              />
              <label htmlFor="match_exact" className="text-sm text-gray-300">
                Exact match only
              </label>
            </div>
          </>
        )}

        {triggerType === 'ai_agent_sentiment' && (
          <>
            <div>
              <label className={labelClass}>Sentiment to Detect *</label>
              <select
                value={config.sentiment || ''}
                onChange={(e) => handleChange('sentiment', e.target.value)}
                className={inputClass}
              >
                <option value="">Select sentiment...</option>
                <option value="angry">Angry/Frustrated</option>
                <option value="happy">Happy/Satisfied</option>
                <option value="confused">Confused</option>
                <option value="neutral">Neutral</option>
                <option value="negative">Any Negative</option>
                <option value="positive">Any Positive</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Sensitivity</label>
              <select
                value={config.sensitivity || 'medium'}
                onChange={(e) => handleChange('sensitivity', e.target.value)}
                className={inputClass}
              >
                <option value="low">Low (strong signals only)</option>
                <option value="medium">Medium</option>
                <option value="high">High (subtle signals)</option>
              </select>
            </div>
          </>
        )}

        {triggerType === 'ai_agent_data_collected' && (
          <>
            <div>
              <label className={labelClass}>Data Field *</label>
              <input
                type="text"
                value={config.data_field || ''}
                onChange={(e) => handleChange('data_field', e.target.value)}
                placeholder="e.g., email, phone, name"
                className={inputClass}
              />
              <p className={helpClass}>Field name that AI agent collects</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="validate_field"
                checked={config.validate_field || false}
                onChange={(e) => handleChange('validate_field', e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-purple-500"
              />
              <label htmlFor="validate_field" className="text-sm text-gray-300">
                Validate format (email, phone, etc.)
              </label>
            </div>
          </>
        )}

        {triggerType === 'ai_agent_started' && (
          <div>
            <label className={labelClass}>Filter by Assistant (optional)</label>
            <input
              type="text"
              value={config.assistant_id || ''}
              onChange={(e) => handleChange('assistant_id', e.target.value)}
              placeholder="Assistant ID to filter"
              className={inputClass}
            />
          </div>
        )}

        {triggerType === 'ai_agent_escalation' && (
          <div>
            <label className={labelClass}>Escalation Type</label>
            <select
              value={config.escalation_type || 'any'}
              onChange={(e) => handleChange('escalation_type', e.target.value)}
              className={inputClass}
            >
              <option value="any">Any escalation request</option>
              <option value="explicit">Explicit request only</option>
              <option value="implicit">Implicit signals</option>
            </select>
          </div>
        )}
      </div>
    );
  };

  // ==================== AI AGENT ACTION CONFIGS ====================
  const renderAIAgentActionConfig = () => {
    const actionType = selectedNode.data.actionType;

    return (
      <div className="space-y-4">
        <div className="p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg">
          <p className="text-xs text-purple-300">
            This action affects the current AI agent call in real-time.
          </p>
        </div>

        {actionType === 'ai_agent_respond' && (
          <>
            <div>
              <label className={labelClass}>Response Type</label>
              <select
                value={config.response_type || 'speak'}
                onChange={(e) => handleChange('response_type', e.target.value)}
                className={inputClass}
              >
                <option value="speak">Speak Text</option>
                <option value="inject_context">Inject Context</option>
                <option value="override_next">Override Next Response</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Message/Script *</label>
              <textarea
                value={config.message || ''}
                onChange={(e) => handleChange('message', e.target.value)}
                placeholder="What the AI agent should say... Use {{caller_name}} for dynamic values"
                rows={4}
                className={inputClass}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="interruptible"
                checked={config.interruptible !== false}
                onChange={(e) => handleChange('interruptible', e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-purple-500"
              />
              <label htmlFor="interruptible" className="text-sm text-gray-300">
                Allow caller to interrupt
              </label>
            </div>
          </>
        )}

        {actionType === 'ai_agent_transfer' && (
          <>
            <div>
              <label className={labelClass}>Transfer Type *</label>
              <select
                value={config.transfer_type || 'phone'}
                onChange={(e) => handleChange('transfer_type', e.target.value)}
                className={inputClass}
              >
                <option value="phone">Phone Number</option>
                <option value="sip">SIP URI</option>
                <option value="queue">Call Queue</option>
                <option value="extension">Extension</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Transfer To *</label>
              <input
                type="text"
                value={config.transfer_to || ''}
                onChange={(e) => handleChange('transfer_to', e.target.value)}
                placeholder={config.transfer_type === 'phone' ? '+1234567890' : 'Queue/Extension name'}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Announce Message (optional)</label>
              <textarea
                value={config.announce_message || ''}
                onChange={(e) => handleChange('announce_message', e.target.value)}
                placeholder="Let me transfer you to a specialist..."
                rows={2}
                className={inputClass}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="warm_transfer"
                checked={config.warm_transfer || false}
                onChange={(e) => handleChange('warm_transfer', e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-purple-500"
              />
              <label htmlFor="warm_transfer" className="text-sm text-gray-300">
                Warm transfer (announce caller to agent)
              </label>
            </div>
          </>
        )}

        {actionType === 'ai_agent_hold' && (
          <>
            <div>
              <label className={labelClass}>Hold Message</label>
              <input
                type="text"
                value={config.hold_message || ''}
                onChange={(e) => handleChange('hold_message', e.target.value)}
                placeholder="Please hold while I check on that..."
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Hold Music</label>
              <select
                value={config.hold_music || 'default'}
                onChange={(e) => handleChange('hold_music', e.target.value)}
                className={inputClass}
              >
                <option value="default">Default Music</option>
                <option value="silence">Silence</option>
                <option value="custom">Custom Audio URL</option>
              </select>
            </div>
            {config.hold_music === 'custom' && (
              <div>
                <label className={labelClass}>Audio URL</label>
                <input
                  type="url"
                  value={config.hold_audio_url || ''}
                  onChange={(e) => handleChange('hold_audio_url', e.target.value)}
                  placeholder="https://example.com/music.mp3"
                  className={inputClass}
                />
              </div>
            )}
            <div>
              <label className={labelClass}>Max Hold Time (seconds)</label>
              <input
                type="number"
                min="5"
                max="300"
                value={config.max_hold_time || 60}
                onChange={(e) => handleChange('max_hold_time', e.target.value)}
                className={inputClass}
              />
            </div>
          </>
        )}

        {actionType === 'ai_agent_hangup' && (
          <>
            <div>
              <label className={labelClass}>Goodbye Message (optional)</label>
              <textarea
                value={config.goodbye_message || ''}
                onChange={(e) => handleChange('goodbye_message', e.target.value)}
                placeholder="Thank you for calling. Have a great day!"
                rows={2}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Hangup Reason</label>
              <select
                value={config.hangup_reason || 'completed'}
                onChange={(e) => handleChange('hangup_reason', e.target.value)}
                className={inputClass}
              >
                <option value="completed">Completed Successfully</option>
                <option value="caller_request">Caller Request</option>
                <option value="no_response">No Response</option>
                <option value="error">Error</option>
              </select>
            </div>
          </>
        )}

        {actionType === 'ai_agent_set_context' && (
          <>
            <div>
              <label className={labelClass}>Context Key *</label>
              <input
                type="text"
                value={config.context_key || ''}
                onChange={(e) => handleChange('context_key', e.target.value)}
                placeholder="e.g., customer_tier, order_status"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Context Value *</label>
              <input
                type="text"
                value={config.context_value || ''}
                onChange={(e) => handleChange('context_value', e.target.value)}
                placeholder="Value or {{dynamic_field}}"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Additional Instructions (optional)</label>
              <textarea
                value={config.instructions || ''}
                onChange={(e) => handleChange('instructions', e.target.value)}
                placeholder="Tell AI how to use this context..."
                rows={3}
                className={inputClass}
              />
            </div>
          </>
        )}

        {actionType === 'ai_agent_send_sms' && (
          <>
            <div>
              <label className={labelClass}>To Number</label>
              <input
                type="text"
                value={config.to_number || '{{caller_phone}}'}
                onChange={(e) => handleChange('to_number', e.target.value)}
                placeholder="{{caller_phone}} or specific number"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>SMS Message *</label>
              <textarea
                value={config.sms_message || ''}
                onChange={(e) => handleChange('sms_message', e.target.value)}
                placeholder="Hi {{caller_name}}, here's the info you requested..."
                rows={3}
                className={inputClass}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="announce_sms"
                checked={config.announce_sms !== false}
                onChange={(e) => handleChange('announce_sms', e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-purple-500"
              />
              <label htmlFor="announce_sms" className="text-sm text-gray-300">
                Tell caller SMS was sent
              </label>
            </div>
          </>
        )}

        {actionType === 'ai_agent_book_meeting' && (
          <>
            <div>
              <label className={labelClass}>Calendar Integration *</label>
              <select
                value={config.calendar_type || ''}
                onChange={(e) => handleChange('calendar_type', e.target.value)}
                className={inputClass}
              >
                <option value="">Select calendar...</option>
                <option value="google">Google Calendar</option>
                <option value="outlook">Outlook Calendar</option>
                <option value="calendly">Calendly</option>
                <option value="calcom">Cal.com</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Meeting Type</label>
              <input
                type="text"
                value={config.meeting_type || ''}
                onChange={(e) => handleChange('meeting_type', e.target.value)}
                placeholder="e.g., Demo Call, Consultation"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Default Duration (minutes)</label>
              <select
                value={config.duration || '30'}
                onChange={(e) => handleChange('duration', e.target.value)}
                className={inputClass}
              >
                <option value="15">15 minutes</option>
                <option value="30">30 minutes</option>
                <option value="45">45 minutes</option>
                <option value="60">1 hour</option>
              </select>
            </div>
          </>
        )}

        {actionType === 'ai_agent_lookup_crm' && (
          <>
            <div>
              <label className={labelClass}>CRM System *</label>
              <select
                value={config.crm_system || ''}
                onChange={(e) => handleChange('crm_system', e.target.value)}
                className={inputClass}
              >
                <option value="">Select CRM...</option>
                <option value="hubspot">HubSpot</option>
                <option value="salesforce">Salesforce</option>
                <option value="pipedrive">Pipedrive</option>
                <option value="zoho">Zoho CRM</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Lookup Field</label>
              <select
                value={config.lookup_field || 'phone'}
                onChange={(e) => handleChange('lookup_field', e.target.value)}
                className={inputClass}
              >
                <option value="phone">Phone Number</option>
                <option value="email">Email</option>
                <option value="name">Name</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Fields to Retrieve</label>
              <input
                type="text"
                value={config.retrieve_fields || ''}
                onChange={(e) => handleChange('retrieve_fields', e.target.value)}
                placeholder="name, email, company, deal_stage"
                className={inputClass}
              />
              <p className={helpClass}>Comma-separated field names</p>
            </div>
          </>
        )}

        {actionType === 'ai_agent_update_crm' && (
          <>
            <div>
              <label className={labelClass}>CRM System *</label>
              <select
                value={config.crm_system || ''}
                onChange={(e) => handleChange('crm_system', e.target.value)}
                className={inputClass}
              >
                <option value="">Select CRM...</option>
                <option value="hubspot">HubSpot</option>
                <option value="salesforce">Salesforce</option>
                <option value="pipedrive">Pipedrive</option>
                <option value="zoho">Zoho CRM</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Update Action</label>
              <select
                value={config.update_action || 'update'}
                onChange={(e) => handleChange('update_action', e.target.value)}
                className={inputClass}
              >
                <option value="update">Update Contact</option>
                <option value="create">Create Contact</option>
                <option value="add_note">Add Note</option>
                <option value="create_task">Create Task</option>
                <option value="update_deal">Update Deal</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Data to Update (JSON)</label>
              <textarea
                value={config.update_data || ''}
                onChange={(e) => handleChange('update_data', e.target.value)}
                placeholder='{"call_notes": "{{transcript_summary}}", "last_contact": "{{today}}"}'
                rows={4}
                className={`${inputClass} font-mono text-xs`}
              />
            </div>
          </>
        )}

        {actionType === 'ai_agent_tag_call' && (
          <>
            <div>
              <label className={labelClass}>Tags *</label>
              <input
                type="text"
                value={config.tags || ''}
                onChange={(e) => handleChange('tags', e.target.value)}
                placeholder="hot_lead, callback_required, vip"
                className={inputClass}
              />
              <p className={helpClass}>Comma-separated tags</p>
            </div>
            <div>
              <label className={labelClass}>Tag Action</label>
              <select
                value={config.tag_action || 'add'}
                onChange={(e) => handleChange('tag_action', e.target.value)}
                className={inputClass}
              >
                <option value="add">Add Tags</option>
                <option value="remove">Remove Tags</option>
                <option value="replace">Replace All Tags</option>
              </select>
            </div>
          </>
        )}

        {actionType === 'ai_agent_set_priority' && (
          <>
            <div>
              <label className={labelClass}>Priority Level *</label>
              <select
                value={config.priority || 'medium'}
                onChange={(e) => handleChange('priority', e.target.value)}
                className={inputClass}
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Reason (optional)</label>
              <input
                type="text"
                value={config.priority_reason || ''}
                onChange={(e) => handleChange('priority_reason', e.target.value)}
                placeholder="e.g., High-value customer"
                className={inputClass}
              />
            </div>
          </>
        )}

        {actionType === 'ai_agent_create_task' && (
          <>
            <div>
              <label className={labelClass}>Task Title *</label>
              <input
                type="text"
                value={config.task_title || ''}
                onChange={(e) => handleChange('task_title', e.target.value)}
                placeholder="Follow up with {{caller_name}}"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Task Description</label>
              <textarea
                value={config.task_description || ''}
                onChange={(e) => handleChange('task_description', e.target.value)}
                placeholder="Details about the follow-up..."
                rows={3}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Due In</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min="1"
                  value={config.due_value || '1'}
                  onChange={(e) => handleChange('due_value', e.target.value)}
                  className={`w-20 ${inputClass}`}
                />
                <select
                  value={config.due_unit || 'days'}
                  onChange={(e) => handleChange('due_unit', e.target.value)}
                  className={inputClass}
                >
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                  <option value="weeks">Weeks</option>
                </select>
              </div>
            </div>
            <div>
              <label className={labelClass}>Assign To (optional)</label>
              <input
                type="text"
                value={config.assign_to || ''}
                onChange={(e) => handleChange('assign_to', e.target.value)}
                placeholder="User email or ID"
                className={inputClass}
              />
            </div>
          </>
        )}

        {actionType === 'ai_agent_webhook' && (
          <>
            <div>
              <label className={labelClass}>Webhook URL *</label>
              <input
                type="url"
                value={config.webhook_url || ''}
                onChange={(e) => handleChange('webhook_url', e.target.value)}
                placeholder="https://api.example.com/webhook"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>HTTP Method</label>
              <select
                value={config.method || 'POST'}
                onChange={(e) => handleChange('method', e.target.value)}
                className={inputClass}
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Request Body (JSON)</label>
              <textarea
                value={config.body || ''}
                onChange={(e) => handleChange('body', e.target.value)}
                placeholder='{"caller": "{{caller_phone}}", "transcript": "{{transcript}}"}'
                rows={4}
                className={`${inputClass} font-mono text-xs`}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="wait_response"
                checked={config.wait_response || false}
                onChange={(e) => handleChange('wait_response', e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-purple-500"
              />
              <label htmlFor="wait_response" className="text-sm text-gray-300">
                Wait for response and use in conversation
              </label>
            </div>
          </>
        )}

        {(actionType === 'ai_agent_play_audio' || actionType === 'ai_agent_change_voice') && (
          <>
            {actionType === 'ai_agent_play_audio' && (
              <div>
                <label className={labelClass}>Audio URL *</label>
                <input
                  type="url"
                  value={config.audio_url || ''}
                  onChange={(e) => handleChange('audio_url', e.target.value)}
                  placeholder="https://example.com/audio.mp3"
                  className={inputClass}
                />
              </div>
            )}
            {actionType === 'ai_agent_change_voice' && (
              <>
                <div>
                  <label className={labelClass}>Voice Provider</label>
                  <select
                    value={config.voice_provider || 'elevenlabs'}
                    onChange={(e) => handleChange('voice_provider', e.target.value)}
                    className={inputClass}
                  >
                    <option value="elevenlabs">ElevenLabs</option>
                    <option value="openai">OpenAI</option>
                    <option value="deepgram">Deepgram</option>
                  </select>
                </div>
                <div>
                  <label className={labelClass}>Voice ID *</label>
                  <input
                    type="text"
                    value={config.voice_id || ''}
                    onChange={(e) => handleChange('voice_id', e.target.value)}
                    placeholder="Voice ID from provider"
                    className={inputClass}
                  />
                </div>
              </>
            )}
          </>
        )}

        {actionType === 'ai_agent_collect_input' && (
          <>
            <div>
              <label className={labelClass}>Input Type</label>
              <select
                value={config.input_type || 'dtmf'}
                onChange={(e) => handleChange('input_type', e.target.value)}
                className={inputClass}
              >
                <option value="dtmf">DTMF (Keypad)</option>
                <option value="speech">Speech</option>
                <option value="both">Both</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Prompt Message *</label>
              <input
                type="text"
                value={config.prompt || ''}
                onChange={(e) => handleChange('prompt', e.target.value)}
                placeholder="Please enter your account number..."
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Store As Variable *</label>
              <input
                type="text"
                value={config.variable_name || ''}
                onChange={(e) => handleChange('variable_name', e.target.value)}
                placeholder="account_number"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Max Digits (for DTMF)</label>
              <input
                type="number"
                min="1"
                max="20"
                value={config.max_digits || ''}
                onChange={(e) => handleChange('max_digits', e.target.value)}
                placeholder="10"
                className={inputClass}
              />
            </div>
          </>
        )}
      </div>
    );
  };

  const renderConfig = () => {
    const nodeType = selectedNode.type;
    const data = selectedNode.data;

    if (nodeType === 'trigger') {
      // Check if it's an AI Agent trigger
      const triggerType = data.triggerType;
      if (triggerType?.startsWith('ai_agent_')) {
        return renderAIAgentTriggerConfig();
      }
      return renderTriggerConfig();
    }

    if (nodeType === 'condition') {
      return renderConditionConfig();
    }

    if (nodeType === 'code') {
      return renderCodeConfig();
    }

    if (nodeType === 'action') {
      const actionType = data.actionType;

      // AI Agent Actions
      if (actionType?.startsWith('ai_agent_')) {
        return renderAIAgentActionConfig();
      }

      // Communication
      if (actionType === 'send_email' || actionType === 'gmail' || actionType === 'sendgrid') {
        return renderEmailConfig();
      }
      if (actionType === 'slack_message' || actionType === 'teams_message' || actionType === 'discord') {
        return renderSlackConfig();
      }

      // HTTP/API
      if (actionType === 'http_request' || actionType === 'graphql' || actionType === 'webhook_response') {
        return renderHttpConfig();
      }

      // Databases
      if (['postgresql', 'mysql', 'mongodb', 'redis', 'supabase', 'firebase', 'airtable', 'google_sheets'].includes(actionType)) {
        return renderDatabaseConfig();
      }

      // AI
      if (['openai', 'anthropic', 'summarize', 'translate', 'sentiment', 'text_classification', 'extract_entities'].includes(actionType)) {
        return renderAIConfig();
      }

      // Flow Control
      if (actionType === 'delay' || actionType === 'wait') {
        return renderDelayConfig();
      }
      if (actionType === 'loop' || actionType === 'split_batches') {
        return renderLoopConfig();
      }

      // Responses
      if (actionType === 'respond') {
        return renderResponseConfig();
      }

      // Generic for other integrations
      return renderGenericConfig();
    }

    return null;
  };

  return (
    <div className="w-80 bg-gray-900 border-l border-gray-700 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{selectedNode.data.icon || '⚙️'}</span>
          <h3 className="text-sm font-semibold text-white">
            {selectedNode.data.label}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-gray-800 text-gray-400 hover:text-white"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Config Form */}
      <div className="flex-1 overflow-auto p-4">
        {renderConfig()}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700">
        <p className="text-xs text-gray-500">
          Changes are saved automatically. Use {'{{field}}'} syntax for dynamic values.
        </p>
      </div>
    </div>
  );
}
