'use client';

import React, { useCallback, useState, useMemo, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  BackgroundVariant,
  ReactFlowProvider,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useTranslation } from '@/utils/i18n';
import NodeConfigDrawer from './NodeConfigDrawer';
import ExecuteNodeDrawer from './ExecuteNodeDrawer';
import styles from './ChatflowEditor.module.scss';
import type { ChatflowEditorRef, ChatflowEditorProps, ChatflowNode } from './types';
import { isChatflowNode } from './types';
import {
  TimeTriggerNode,
  RestfulApiNode,
  OpenAIApiNode,
  AgentsNode,
  HttpRequestNode,
  IfConditionNode,
  NotificationNode,
  EnterpriseWechatNode,
  DingtalkNode,
  WechatOfficialNode,
} from './nodes';
import { useNodeExecution } from './hooks/useNodeExecution';
import { useNodeDeletion } from './hooks/useNodeDeletion';
import { useNodeDrop } from './hooks/useNodeDrop';

const ChatflowEditor = forwardRef<ChatflowEditorRef, ChatflowEditorProps>(({ onSave, initialData }, ref) => {
  const { t } = useTranslation();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);
  const [selectedNode, setSelectedNode] = useState<ChatflowNode | null>(null);
  const [isConfigDrawerVisible, setIsConfigDrawerVisible] = useState(false);
  const [selectedNodes, setSelectedNodes] = useState<any[]>([]);
  const [selectedEdges, setSelectedEdges] = useState<any[]>([]);
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 0.6 });
  const [isInitialized, setIsInitialized] = useState(false);
  const lastSaveData = useRef<string>('');

  const [nodes, setNodes, onNodesChange] = useNodesState(
    initialData?.nodes && Array.isArray(initialData.nodes) ? initialData.nodes : []
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(
    initialData?.edges && Array.isArray(initialData.edges) ? initialData.edges : []
  );

  // 使用自定义 Hooks
  const executionProps = useNodeExecution(t);
  const { handleDeleteNode, handleKeyDown } = useNodeDeletion({
    setNodes,
    setEdges,
    setSelectedNodes,
    setSelectedEdges,
    setIsConfigDrawerVisible,
    selectedNodes,
    selectedEdges,
    t,
  });
  const { onDragOver, onDrop } = useNodeDrop({
    reactFlowInstance,
    setNodes,
    edges,
    onSave,
    t,
  });

  // Auto-save
  useEffect(() => {
    if (!isInitialized) {
      setIsInitialized(true);
      return;
    }

    if (isInitialized && onSave) {
      const currentData = JSON.stringify({
        nodes: nodes.map(n => ({ id: n.id, type: n.type, position: n.position, data: n.data })),
        edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target }))
      });

      if (currentData !== lastSaveData.current) {
        lastSaveData.current = currentData;
        const timeoutId = setTimeout(() => {
          console.log('ChatflowEditor: Saving data changes');
          onSave(nodes, edges);
        }, 100);
        return () => clearTimeout(timeoutId);
      }
    }
  }, [nodes, edges, onSave, isInitialized]);

  const clearCanvas = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setSelectedNode(null);
    setSelectedNodes([]);
    setSelectedEdges([]);
    setIsConfigDrawerVisible(false);
    lastSaveData.current = JSON.stringify({ nodes: [], edges: [] });
  }, [setNodes, setEdges]);

  useImperativeHandle(ref, () => ({ clearCanvas }), [clearCanvas]);

  const handleConfigNode = useCallback((nodeId: string) => {
    const node = nodes.find(n => n.id === nodeId);
    if (node && isChatflowNode(node)) {
      setSelectedNode(node);
      setIsConfigDrawerVisible(true);
    }
  }, [nodes]);

  const nodeTypes: NodeTypes = useMemo(() => {
    const createNodeComponent = (Component: React.ComponentType<any>) => {
      const NodeComponentWithProps = (props: any) => (
        <Component {...props} onDelete={handleDeleteNode} onConfig={handleConfigNode} />
      );
      NodeComponentWithProps.displayName = `NodeComponent(${Component.displayName || Component.name})`;
      return NodeComponentWithProps;
    };

    return {
      celery: createNodeComponent(TimeTriggerNode),
      restful: createNodeComponent(RestfulApiNode),
      openai: createNodeComponent(OpenAIApiNode),
      agents: createNodeComponent(AgentsNode),
      condition: createNodeComponent(IfConditionNode),
      http: createNodeComponent(HttpRequestNode),
      notification: createNodeComponent(NotificationNode),
      enterprise_wechat: createNodeComponent(EnterpriseWechatNode),
      dingtalk: createNodeComponent(DingtalkNode),
      wechat_official: createNodeComponent(WechatOfficialNode),
    };
  }, [handleDeleteNode, handleConfigNode]);

  const onInit = useCallback((instance: any) => {
    setReactFlowInstance(instance);
    setViewport(instance.getViewport());
  }, []);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onSelectionChange = useCallback((params: { nodes: any[]; edges: any[] }) => {
    setSelectedNodes(params.nodes);
    setSelectedEdges(params.edges);
  }, []);

  const handleSaveConfig = useCallback((nodeId: string, values: any) => {
    const { name, ...config } = values;
    
    setNodes((nds) => {
      const updatedNodes = nds.map((node) =>
        node.id === nodeId
          ? { ...node, data: { ...node.data, label: name || node.data.label, config } }
          : node
      );
      
      // 立即触发 onSave 回调，同步更新上层状态
      if (onSave) {
        onSave(updatedNodes, edges);
      }
      
      return updatedNodes;
    });
    setIsConfigDrawerVisible(false);
  }, [setNodes, edges, onSave]);

  useEffect(() => {
    const flowContainer = reactFlowWrapper.current;
    if (flowContainer) {
      flowContainer.tabIndex = 0;
      flowContainer.addEventListener('keydown', handleKeyDown);
      return () => flowContainer.removeEventListener('keydown', handleKeyDown);
    }
  }, [handleKeyDown]);

  return (
    <div className={styles.chatflowEditor}>
      <div
        className={styles.flowContainer}
        ref={reactFlowWrapper}
        onFocus={() => reactFlowWrapper.current?.focus()}
        style={{ outline: 'none' }}
      >
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={onInit}
            onDrop={(e) => onDrop(e, reactFlowWrapper)}
            onDragOver={onDragOver}
            onSelectionChange={onSelectionChange}
            nodeTypes={nodeTypes}
            defaultViewport={viewport}
            onMove={(_, newViewport) => setViewport(newViewport)}
            minZoom={0.1}
            maxZoom={2}
            attributionPosition="bottom-left"
            fitView={false}
            fitViewOptions={{ padding: 0.2, includeHiddenNodes: false }}
            deleteKeyCode={null}
            selectionKeyCode={null}
            multiSelectionKeyCode={null}
          >
            <MiniMap
              nodeColor="#1890ff"
              nodeStrokeColor="#f0f0f0"
              nodeStrokeWidth={1}
              maskColor="rgba(255, 255, 255, 0.8)"
              pannable
              zoomable
              ariaLabel="Flowchart minimap"
            />
            <Controls />
            <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>

      <NodeConfigDrawer
        visible={isConfigDrawerVisible}
        node={selectedNode}
        nodes={Array.isArray(nodes) ? nodes.filter(isChatflowNode) : []}
        onClose={() => setIsConfigDrawerVisible(false)}
        onSave={handleSaveConfig}
        onDelete={handleDeleteNode}
      />

      <ExecuteNodeDrawer
        visible={executionProps.isExecuteDrawerVisible}
        nodeId={executionProps.executeNodeId}
        message={executionProps.executeMessage}
        result={executionProps.executeResult}
        loading={executionProps.executeLoading}
        onMessageChange={executionProps.setExecuteMessage}
        onExecute={executionProps.handleExecuteNode}
        onClose={() => executionProps.setIsExecuteDrawerVisible(false)}
      />
    </div>
  );
});

ChatflowEditor.displayName = 'ChatflowEditor';

export default ChatflowEditor;
export type { ChatflowNodeData, ChatflowEditorRef } from './types';
