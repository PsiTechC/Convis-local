'use client';

import { useState } from 'react';
import { availableNodes } from './index';

interface NodeSidebarProps {
  onDragStart: (event: React.DragEvent, nodeData: any) => void;
}

// Category display configuration
const categoryConfig: Record<string, { label: string; color: string; icon: string }> = {
  triggers: { label: 'Triggers', color: 'border-orange-500 bg-orange-500/10', icon: '⚡' },
  aiAgent: { label: 'AI Agent', color: 'border-purple-500 bg-purple-500/10', icon: '🤖' },
  conditions: { label: 'Flow Control', color: 'border-cyan-500 bg-cyan-500/10', icon: '🔀' },
  code: { label: 'Data Transform', color: 'border-yellow-500 bg-yellow-500/10', icon: '{ }' },
  communication: { label: 'Communication', color: 'border-blue-500 bg-blue-500/10', icon: '💬' },
  crm: { label: 'CRM', color: 'border-orange-400 bg-orange-400/10', icon: '👥' },
  projectManagement: { label: 'Project Management', color: 'border-green-500 bg-green-500/10', icon: '📋' },
  databases: { label: 'Databases', color: 'border-emerald-500 bg-emerald-500/10', icon: '🗄️' },
  files: { label: 'Files & Storage', color: 'border-indigo-500 bg-indigo-500/10', icon: '📁' },
  api: { label: 'HTTP & APIs', color: 'border-violet-500 bg-violet-500/10', icon: '🌐' },
  ai: { label: 'AI & ML', color: 'border-pink-500 bg-pink-500/10', icon: '🧠' },
  flowControl: { label: 'Flow Actions', color: 'border-teal-500 bg-teal-500/10', icon: '⏱️' },
  responses: { label: 'Responses', color: 'border-gray-500 bg-gray-500/10', icon: '↩️' },
  utility: { label: 'Developer', color: 'border-slate-500 bg-slate-500/10', icon: '💻' },
  ecommerce: { label: 'E-commerce', color: 'border-amber-500 bg-amber-500/10', icon: '🛒' },
  marketing: { label: 'Marketing', color: 'border-rose-500 bg-rose-500/10', icon: '📢' },
  calendar: { label: 'Calendar', color: 'border-sky-500 bg-sky-500/10', icon: '📅' },
};

// Order categories for display - AI Agent at top for prominence
const categoryOrder = [
  'triggers',
  'aiAgent',
  'conditions',
  'code',
  'flowControl',
  'communication',
  'crm',
  'projectManagement',
  'databases',
  'files',
  'api',
  'ai',
  'ecommerce',
  'marketing',
  'calendar',
  'utility',
  'responses',
];

export function NodeSidebar({ onDragStart }: NodeSidebarProps) {
  const [expandedCategories, setExpandedCategories] = useState<string[]>([
    'triggers',
    'conditions',
  ]);
  const [searchTerm, setSearchTerm] = useState('');

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category)
        : [...prev, category]
    );
  };

  const filterNodes = (nodes: any[]) => {
    if (!searchTerm) return nodes;
    const term = searchTerm.toLowerCase();
    return nodes.filter(
      (node) =>
        node.label.toLowerCase().includes(term) ||
        node.description?.toLowerCase().includes(term) ||
        node.category?.toLowerCase().includes(term)
    );
  };

  // Get all nodes that match search
  const getAllMatchingNodes = () => {
    if (!searchTerm) return null;
    const allNodes: any[] = [];
    Object.entries(availableNodes).forEach(([category, nodes]) => {
      const filtered = filterNodes(nodes);
      filtered.forEach((node) => {
        allNodes.push({ ...node, _category: category });
      });
    });
    return allNodes;
  };

  const matchingNodes = getAllMatchingNodes();

  // Get border color for a node
  const getNodeColor = (category: string) => {
    return categoryConfig[category]?.color || 'border-gray-500 bg-gray-500/10';
  };

  return (
    <div className="w-72 bg-gray-900 border-r border-gray-700 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
          </svg>
          Add Nodes
        </h3>
        <input
          type="text"
          placeholder="Search 150+ nodes..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
        />
      </div>

      {/* Node Categories or Search Results */}
      <div className="flex-1 overflow-auto p-2">
        {searchTerm && matchingNodes ? (
          // Show search results
          <div>
            <p className="text-xs text-gray-500 px-2 mb-2">
              {matchingNodes.length} nodes found
            </p>
            <div className="space-y-1">
              {matchingNodes.map((node, index) => (
                <div
                  key={`search-${index}`}
                  draggable
                  onDragStart={(e) => onDragStart(e, node)}
                  className={`
                    flex items-center gap-2 px-3 py-2 rounded-lg cursor-grab
                    border-l-4 ${getNodeColor(node._category)}
                    hover:bg-gray-750 active:cursor-grabbing
                    transition-colors
                  `}
                >
                  <span className="text-lg flex-shrink-0">{node.icon}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">
                      {node.label}
                    </p>
                    <p className="text-xs text-gray-500 truncate">
                      {node.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          // Show categories
          categoryOrder.map((category) => {
            const nodes = (availableNodes as any)[category];
            if (!nodes || nodes.length === 0) return null;

            const config = categoryConfig[category] || {
              label: category,
              color: 'border-gray-500',
              icon: '📦',
            };

            return (
              <div key={category} className="mb-1">
                {/* Category Header */}
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-800 rounded-lg transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-base">{config.icon}</span>
                    <span>{config.label}</span>
                    <span className="text-xs text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">
                      {nodes.length}
                    </span>
                  </div>
                  <svg
                    className={`w-4 h-4 transition-transform ${
                      expandedCategories.includes(category) ? 'rotate-180' : ''
                    }`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                </button>

                {/* Node List */}
                {expandedCategories.includes(category) && (
                  <div className="mt-1 space-y-1 ml-2">
                    {nodes.map((node: any, index: number) => (
                      <div
                        key={`${category}-${index}`}
                        draggable
                        onDragStart={(e) => onDragStart(e, node)}
                        className={`
                          flex items-center gap-2 px-3 py-2 rounded-lg cursor-grab
                          border-l-4 ${config.color}
                          hover:brightness-110 active:cursor-grabbing
                          transition-all
                        `}
                      >
                        <span className="text-lg flex-shrink-0">{node.icon}</span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">
                            {node.label}
                          </p>
                          <p className="text-xs text-gray-500 truncate">
                            {node.description}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Help Text */}
      <div className="p-4 border-t border-gray-700">
        <p className="text-xs text-gray-500">
          Drag nodes onto canvas to build your workflow. Connect nodes by dragging from output to input handles.
        </p>
      </div>
    </div>
  );
}
