'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

export interface ActionNodeData {
  label: string;
  description?: string;
  icon?: string;
  actionType:
    | 'send_email'
    | 'slack_message'
    | 'create_jira'
    | 'update_jira'
    | 'hubspot_contact'
    | 'hubspot_note'
    | 'http_request'
    | 'database'
    | 'delay'
    | 'respond';
  config?: Record<string, any>;
}

// Action type colors
const actionColors: Record<string, string> = {
  send_email: '#8b5cf6',     // Purple
  slack_message: '#4ade80',  // Green
  create_jira: '#3b82f6',    // Blue
  update_jira: '#3b82f6',    // Blue
  hubspot_contact: '#f97316', // Orange
  hubspot_note: '#f97316',   // Orange
  http_request: '#ec4899',   // Pink
  database: '#6366f1',       // Indigo
  delay: '#f59e0b',          // Amber
  respond: '#6b7280',        // Gray
};

// Action type icons
const actionIcons: Record<string, string> = {
  send_email: '📧',
  slack_message: '💬',
  create_jira: '🎫',
  update_jira: '✏️',
  hubspot_contact: '👤',
  hubspot_note: '📝',
  http_request: '🔗',
  database: '💾',
  delay: '⏱️',
  respond: '↩️',
};

function ActionNodeComponent({ data, selected }: NodeProps<ActionNodeData>) {
  const nodeColor = actionColors[data.actionType] || '#8b5cf6';
  const icon = data.icon || actionIcons[data.actionType] || '⚙️';
  const isConfigured = Object.keys(data.config || {}).length > 0;

  // Get config preview based on action type
  const getConfigPreview = () => {
    if (!data.config) return null;

    switch (data.actionType) {
      case 'send_email':
        return data.config.to_email ? `To: ${data.config.to_email}` : null;
      case 'slack_message':
        return data.config.channel ? `Channel: ${data.config.channel}` : null;
      case 'create_jira':
      case 'update_jira':
        return data.config.project_key ? `Project: ${data.config.project_key}` : null;
      case 'http_request':
        return data.config.url ? `${data.config.method || 'GET'} ${new URL(data.config.url).hostname}` : null;
      case 'delay':
        if (data.config.delay_seconds) {
          const s = data.config.delay_seconds;
          if (s < 60) return `Wait ${s}s`;
          if (s < 3600) return `Wait ${Math.floor(s/60)}m`;
          return `Wait ${Math.floor(s/3600)}h`;
        }
        return null;
      default:
        return null;
    }
  };

  const configPreview = getConfigPreview();

  return (
    <div
      className={`
        relative min-w-[200px] rounded-lg border-2 shadow-lg transition-all
        ${selected ? 'ring-2 ring-offset-2 ring-offset-gray-900' : ''}
        bg-gray-900 border-gray-700
      `}
      style={{
        borderColor: selected ? nodeColor : undefined,
        '--tw-ring-color': nodeColor,
      } as React.CSSProperties}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        className="!w-3 !h-3 !bg-gray-500 !border-2 !border-gray-700"
      />

      {/* Header */}
      <div
        className="px-3 py-2 rounded-t-md flex items-center gap-2"
        style={{ backgroundColor: nodeColor }}
      >
        <span className="text-lg">{icon}</span>
        <span className="text-xs font-semibold uppercase tracking-wider text-white">
          Action
        </span>
      </div>

      {/* Body */}
      <div className="px-3 py-3">
        <h3 className="text-sm font-semibold text-white">
          {data.label}
        </h3>
        {data.description && (
          <p className="text-xs text-gray-400 mt-1">
            {data.description}
          </p>
        )}

        {/* Config Preview */}
        {configPreview && (
          <div className="mt-2 p-1.5 rounded bg-gray-800 text-xs text-gray-300 truncate">
            {configPreview}
          </div>
        )}

        {/* Configuration Status */}
        <div className="flex items-center gap-1.5 mt-2">
          <div
            className={`w-2 h-2 rounded-full ${
              isConfigured ? 'bg-green-500' : 'bg-yellow-500'
            }`}
          />
          <span className="text-xs text-gray-500">
            {isConfigured ? 'Configured' : 'Click to configure'}
          </span>
        </div>
      </div>

      {/* Output Handle (for chaining) */}
      {data.actionType !== 'respond' && (
        <Handle
          type="source"
          position={Position.Right}
          id="output"
          className="!w-3 !h-3 !border-2 !border-gray-700"
          style={{ backgroundColor: nodeColor }}
        />
      )}
    </div>
  );
}

export const ActionNode = memo(ActionNodeComponent);
