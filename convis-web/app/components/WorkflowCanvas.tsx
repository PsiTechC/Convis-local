'use client';

import { useState, useCallback, useRef, useMemo } from 'react';
import ReactFlow, {
  Node,
  Edge,
  addEdge,
  Connection,
  useNodesState,
  useEdgesState,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  ReactFlowProvider,
  ReactFlowInstance,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { nodeTypes } from './workflow-nodes';
import { NodeSidebar } from './workflow-nodes/NodeSidebar';
import { NodeConfigPanel } from './workflow-nodes/NodeConfigPanel';

interface WorkflowCanvasProps {
  initialNodes?: Node[];
  initialEdges?: Edge[];
  onSave?: (nodes: Node[], edges: Edge[]) => void;
  onChange?: (nodes: Node[], edges: Edge[]) => void;
}

let nodeId = 0;
const getNodeId = () => `node_${nodeId++}`;

export function WorkflowCanvas({
  initialNodes = [],
  initialEdges = [],
  onSave,
  onChange,
}: WorkflowCanvasProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  // Memoize nodeTypes to prevent re-renders
  const memoizedNodeTypes = useMemo(() => nodeTypes, []);

  // Handle node changes and notify parent
  const handleNodesChange = useCallback(
    (changes: any) => {
      onNodesChange(changes);
    },
    [onNodesChange]
  );

  const handleEdgesChange = useCallback(
    (changes: any) => {
      onEdgesChange(changes);
    },
    [onEdgesChange]
  );

  // Notify parent of changes
  const notifyChange = useCallback(() => {
    if (onChange) {
      onChange(nodes, edges);
    }
  }, [nodes, edges, onChange]);

  // Connect nodes
  const onConnect = useCallback(
    (params: Connection) => {
      // Custom edge styling
      const newEdge = {
        ...params,
        type: 'smoothstep',
        animated: true,
        style: { stroke: '#6366f1', strokeWidth: 2 },
      };
      setEdges((eds) => addEdge(newEdge, eds));
      notifyChange();
    },
    [setEdges, notifyChange]
  );

  // Handle drag start from sidebar
  const onDragStart = useCallback(
    (event: React.DragEvent, nodeData: any) => {
      event.dataTransfer.setData('application/reactflow', JSON.stringify(nodeData));
      event.dataTransfer.effectAllowed = 'move';
    },
    []
  );

  // Handle drop on canvas
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      if (!reactFlowWrapper.current || !reactFlowInstance) return;

      const reactFlowBounds = reactFlowWrapper.current.getBoundingClientRect();
      const nodeData = JSON.parse(
        event.dataTransfer.getData('application/reactflow')
      );

      // Calculate position
      const position = reactFlowInstance.project({
        x: event.clientX - reactFlowBounds.left,
        y: event.clientY - reactFlowBounds.top,
      });

      // Create new node
      const newNode: Node = {
        id: getNodeId(),
        type: nodeData.type,
        position,
        data: {
          label: nodeData.label,
          icon: nodeData.icon,
          description: nodeData.description,
          config: nodeData.config || {},
          // Type-specific data
          ...(nodeData.triggerType && { triggerType: nodeData.triggerType }),
          ...(nodeData.conditionType && { conditionType: nodeData.conditionType }),
          ...(nodeData.actionType && { actionType: nodeData.actionType }),
          ...(nodeData.codeType && { codeType: nodeData.codeType }),
        },
      };

      setNodes((nds) => nds.concat(newNode));
      notifyChange();
    },
    [reactFlowInstance, setNodes, notifyChange]
  );

  // Handle node selection
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  // Handle canvas click (deselect)
  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  // Update node data
  const updateNodeData = useCallback(
    (nodeId: string, newData: any) => {
      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === nodeId) {
            return {
              ...node,
              data: newData,
            };
          }
          return node;
        })
      );
      // Update selected node reference
      setSelectedNode((prev) =>
        prev?.id === nodeId ? { ...prev, data: newData } : prev
      );
      notifyChange();
    },
    [setNodes, notifyChange]
  );

  // Delete selected node
  const deleteSelectedNode = useCallback(() => {
    if (!selectedNode) return;
    setNodes((nds) => nds.filter((node) => node.id !== selectedNode.id));
    setEdges((eds) =>
      eds.filter(
        (edge) =>
          edge.source !== selectedNode.id && edge.target !== selectedNode.id
      )
    );
    setSelectedNode(null);
    notifyChange();
  }, [selectedNode, setNodes, setEdges, notifyChange]);

  // Keyboard shortcuts
  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Delete' || event.key === 'Backspace') {
        deleteSelectedNode();
      }
    },
    [deleteSelectedNode]
  );

  return (
    <div className="flex h-full bg-gray-950" onKeyDown={onKeyDown} tabIndex={0}>
      {/* Left Sidebar - Node Palette */}
      <NodeSidebar onDragStart={onDragStart} />

      {/* Main Canvas */}
      <div className="flex-1 h-full" ref={reactFlowWrapper}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={onConnect}
          onInit={setReactFlowInstance}
          onDrop={onDrop}
          onDragOver={onDragOver}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={memoizedNodeTypes}
          fitView
          snapToGrid
          snapGrid={[15, 15]}
          defaultEdgeOptions={{
            type: 'smoothstep',
            animated: true,
            style: { stroke: '#6366f1', strokeWidth: 2 },
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="#374151"
          />
          <Controls
            className="!bg-gray-800 !border-gray-700 !rounded-lg"
            showInteractive={false}
          />
          <MiniMap
            className="!bg-gray-800 !border-gray-700 !rounded-lg"
            nodeColor={(node) => {
              switch (node.type) {
                case 'trigger':
                  return '#f97316';
                case 'condition':
                  return '#06b6d4';
                case 'code':
                  return '#eab308';
                case 'action':
                  return '#8b5cf6';
                default:
                  return '#6b7280';
              }
            }}
            maskColor="rgba(0, 0, 0, 0.8)"
          />
        </ReactFlow>
      </div>

      {/* Right Sidebar - Node Configuration */}
      {selectedNode && (
        <NodeConfigPanel
          selectedNode={selectedNode}
          onUpdateNode={updateNodeData}
          onClose={() => setSelectedNode(null)}
        />
      )}
    </div>
  );
}

// Wrapper with ReactFlowProvider
export function WorkflowCanvasWithProvider(props: WorkflowCanvasProps) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvas {...props} />
    </ReactFlowProvider>
  );
}
