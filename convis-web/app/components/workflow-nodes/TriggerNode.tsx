'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

export interface TriggerNodeData {
  label: string;
  description?: string;
  icon?: string;
  triggerType: 'webhook' | 'call_completed' | 'call_failed' | 'campaign_completed' | 'schedule';
  config?: Record<string, any>;
}

function TriggerNodeComponent({ data, selected }: NodeProps<TriggerNodeData>) {
  const nodeColor = '#f97316'; // Orange

  return (
    <div
      className={`
        relative min-w-[200px] rounded-lg border-2 shadow-lg transition-all
        ${selected ? 'ring-2 ring-offset-2 ring-orange-500 ring-offset-gray-900' : ''}
        bg-gray-900 border-gray-700
      `}
      style={{ borderColor: selected ? nodeColor : undefined }}
    >
      {/* Header */}
      <div
        className="px-3 py-2 rounded-t-md flex items-center gap-2"
        style={{ backgroundColor: nodeColor }}
      >
        <span className="text-lg">{data.icon || '⚡'}</span>
        <span className="text-xs font-semibold uppercase tracking-wider text-white">
          Trigger
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

        {/* Trigger Type Badge */}
        <div className="mt-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-900/50 text-orange-300">
            {data.triggerType.replace(/_/g, ' ')}
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

export const TriggerNode = memo(TriggerNodeComponent);
