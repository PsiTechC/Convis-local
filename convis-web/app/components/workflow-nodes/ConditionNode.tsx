'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

export interface ConditionNodeData {
  label: string;
  description?: string;
  icon?: string;
  conditionType: 'if' | 'switch' | 'filter' | 'validation' | 'dedup';
  config?: {
    field?: string;
    operator?: string;
    value?: string;
    expression?: string;
  };
}

function ConditionNodeComponent({ data, selected }: NodeProps<ConditionNodeData>) {
  const nodeColor = '#06b6d4'; // Cyan
  const isConfigured = data.config?.field || data.config?.expression;

  // Determine number of outputs based on condition type
  const outputs = data.conditionType === 'switch'
    ? [
        { id: 'case1', label: 'Case 1' },
        { id: 'case2', label: 'Case 2' },
        { id: 'default', label: 'Default' },
      ]
    : data.conditionType === 'if' || data.conditionType === 'validation' || data.conditionType === 'dedup'
    ? [
        { id: 'true', label: 'True' },
        { id: 'false', label: 'False' },
      ]
    : [{ id: 'output', label: '' }];

  return (
    <div
      className={`
        relative min-w-[200px] rounded-lg border-2 shadow-lg transition-all
        ${selected ? 'ring-2 ring-offset-2 ring-cyan-500 ring-offset-gray-900' : ''}
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
        <span className="text-lg">{data.icon || '🔀'}</span>
        <span className="text-xs font-semibold uppercase tracking-wider text-white">
          {data.conditionType === 'if' ? 'IF' :
           data.conditionType === 'validation' ? 'Validation' :
           data.conditionType === 'dedup' ? 'Dedup Check' :
           data.conditionType}
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

        {/* Condition Preview */}
        {isConfigured && data.config && (
          <div className="mt-2 p-2 rounded bg-gray-800 text-xs text-gray-300 font-mono">
            {data.config.field} {data.config.operator} {data.config.value}
          </div>
        )}

        {/* Configuration Status */}
        {!isConfigured && (
          <div className="flex items-center gap-1.5 mt-2">
            <div className="w-2 h-2 rounded-full bg-yellow-500" />
            <span className="text-xs text-gray-500">Click to configure</span>
          </div>
        )}
      </div>

      {/* Output Handles with Labels */}
      {outputs.map((output, index) => {
        const yPosition = outputs.length > 1
          ? 60 + (index * 30)  // Start after header, space 30px apart
          : '50%';

        return (
          <div key={output.id}>
            <Handle
              type="source"
              position={Position.Right}
              id={output.id}
              className="!w-3 !h-3 !border-2 !border-gray-700"
              style={{
                backgroundColor: output.id === 'true' ? '#22c55e' : output.id === 'false' ? '#ef4444' : nodeColor,
                top: yPosition,
              }}
            />
            {output.label && (
              <span
                className="absolute right-5 text-[10px] text-gray-400"
                style={{ top: typeof yPosition === 'number' ? yPosition - 6 : yPosition }}
              >
                {output.label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export const ConditionNode = memo(ConditionNodeComponent);
