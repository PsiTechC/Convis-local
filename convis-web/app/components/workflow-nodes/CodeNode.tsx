'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

export interface CodeNodeData {
  label: string;
  description?: string;
  icon?: string;
  codeType: 'extract_fields' | 'generate_key' | 'increment' | 'mark_processed' | 'custom';
  config?: {
    code?: string;
    language?: 'javascript' | 'python';
    inputFields?: string[];
    outputFields?: string[];
  };
}

function CodeNodeComponent({ data, selected }: NodeProps<CodeNodeData>) {
  const nodeColor = '#eab308'; // Yellow
  const isConfigured = data.config?.code || data.codeType !== 'custom';

  // Code type labels
  const codeTypeLabels: Record<string, string> = {
    extract_fields: 'Extract Fields',
    generate_key: 'Generate Key',
    increment: 'Increment',
    mark_processed: 'Mark Processed',
    custom: 'Custom Code',
  };

  return (
    <div
      className={`
        relative min-w-[200px] rounded-lg border-2 shadow-lg transition-all
        ${selected ? 'ring-2 ring-offset-2 ring-yellow-500 ring-offset-gray-900' : ''}
        bg-gray-900 border-gray-700
      `}
      style={{ borderColor: selected ? nodeColor : undefined }}
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
        <span className="text-lg">{data.icon || '{ }'}</span>
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-900">
          Code
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

        {/* Code Type Badge */}
        <div className="mt-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-900/50 text-yellow-300">
            {codeTypeLabels[data.codeType] || data.codeType}
          </span>
        </div>

        {/* Code Preview */}
        {data.config?.code && (
          <div className="mt-2 p-2 rounded bg-gray-800 text-xs text-gray-300 font-mono max-h-16 overflow-hidden">
            {data.config.code.slice(0, 100)}
            {data.config.code.length > 100 && '...'}
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

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        className="!w-3 !h-3 !border-2 !border-gray-700"
        style={{ backgroundColor: nodeColor }}
      />
    </div>
  );
}

export const CodeNode = memo(CodeNodeComponent);
