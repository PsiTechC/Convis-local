'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

export interface BaseNodeData {
  label: string;
  description?: string;
  icon?: string;
  config?: Record<string, any>;
  isConfigured?: boolean;
}

interface BaseNodeProps extends NodeProps<BaseNodeData> {
  nodeColor: string;
  nodeType: string;
  handles?: {
    inputs?: Array<{ id: string; position?: Position }>;
    outputs?: Array<{ id: string; label?: string; position?: Position }>;
  };
}

function BaseNodeComponent({
  data,
  selected,
  nodeColor,
  nodeType,
  handles = { inputs: [{ id: 'input' }], outputs: [{ id: 'output' }] },
}: BaseNodeProps) {
  const isConfigured = data.isConfigured ?? Object.keys(data.config || {}).length > 0;

  return (
    <div
      className={`
        relative min-w-[180px] rounded-lg border-2 shadow-lg transition-all
        ${selected ? 'ring-2 ring-offset-2 ring-blue-500' : ''}
        bg-gray-900 border-gray-700
      `}
      style={{ borderColor: selected ? nodeColor : undefined }}
    >
      {/* Input Handles */}
      {handles.inputs?.map((input, index) => (
        <Handle
          key={input.id}
          type="target"
          position={input.position || Position.Left}
          id={input.id}
          className="!w-3 !h-3 !bg-gray-500 !border-2 !border-gray-700"
          style={{
            top: handles.inputs!.length > 1
              ? `${((index + 1) / (handles.inputs!.length + 1)) * 100}%`
              : '50%',
          }}
        />
      ))}

      {/* Header */}
      <div
        className="px-3 py-2 rounded-t-md flex items-center gap-2"
        style={{ backgroundColor: nodeColor }}
      >
        <span className="text-lg">{data.icon || '⚙️'}</span>
        <span className="text-xs font-semibold uppercase tracking-wider text-white/90">
          {nodeType}
        </span>
      </div>

      {/* Body */}
      <div className="px-3 py-3">
        <h3 className="text-sm font-semibold text-white truncate">
          {data.label}
        </h3>
        {data.description && (
          <p className="text-xs text-gray-400 mt-1 truncate">
            {data.description}
          </p>
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

      {/* Output Handles */}
      {handles.outputs?.map((output, index) => (
        <div key={output.id} className="relative">
          <Handle
            type="source"
            position={output.position || Position.Right}
            id={output.id}
            className="!w-3 !h-3 !border-2 !border-gray-700"
            style={{
              backgroundColor: nodeColor,
              top: handles.outputs!.length > 1
                ? `${((index + 1) / (handles.outputs!.length + 1)) * 100}%`
                : '50%',
            }}
          />
          {output.label && (
            <span
              className="absolute right-6 text-[10px] text-gray-400 whitespace-nowrap"
              style={{
                top: handles.outputs!.length > 1
                  ? `${((index + 1) / (handles.outputs!.length + 1)) * 100}%`
                  : '50%',
                transform: 'translateY(-50%)',
              }}
            >
              {output.label}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export const BaseNode = memo(BaseNodeComponent);
