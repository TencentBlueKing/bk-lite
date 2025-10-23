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
  Edge,
  Node,
  NodeTypes,
  Handle,
  Position,
  BackgroundVariant,
  ReactFlowProvider,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Modal, message } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import NodeConfigDrawer from './NodeConfigDrawer';
import ExecuteNodeDrawer from './ExecuteNodeDrawer';
import styles from './ChatflowEditor.module.scss';
import { useStudioApi } from '../../api/studio';

interface ChatflowNodeData {
  label: string;
  type: 'celery' | 'restful' | 'openai' | 'agents' | 'condition' | 'http' | 'notification';
  config?: any;
  description?: string;
  [key: string]: unknown;
}

// Type guard to check if a node is a valid ChatflowNode
const isChatflowNode = (node: Node): node is ChatflowNode => {
  return node.data && 
         typeof (node.data as any).label === 'string' && 
         typeof (node.data as any).type === 'string';
}

interface ChatflowNode extends Node {
  data: ChatflowNodeData;
}

// Node configuration mapping for icons and colors
const nodeConfig = {
  celery: { icon: 'a-icon-dingshichufa1x', color: 'green' },
  restful: { icon: 'RESTfulAPI', color: 'purple' },
  openai: { icon: 'icon-test2', color: 'blue' },
  agents: { icon: 'zhinengti', color: 'orange' },
  condition: { icon: 'tiaojianfenzhi', color: 'yellow' },
  http: { icon: 'HTTP', color: 'cyan' },
  notification: { icon: 'alarm', color: 'pink' },
};

// Base node component with configurable input/output handles
const BaseNode = ({ 
  data, 
  id, 
  selected, 
  onConfig, 
  icon, 
  color = 'blue',
  hasInput = false,
  hasOutput = true,
  hasMultipleOutputs = false
}: { 
  data: ChatflowNodeData; 
  id: string; 
  selected?: boolean;
  onConfig: (id: string) => void;
  icon: string;
  color?: string;
  hasInput?: boolean;
  hasOutput?: boolean;
  hasMultipleOutputs?: boolean;
}) => {
  const { t } = useTranslation();
  
  // Tailwind classes for handle colors
  const handleColorClasses = {
    green: '!bg-green-500',
    purple: '!bg-purple-500',
    blue: '!bg-blue-500',
    orange: '!bg-orange-500', 
    yellow: '!bg-yellow-500',
    cyan: '!bg-cyan-500',
  };

  const handleNodeClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onConfig(id);
  };

  // 检查是否为触发类型节点
  const isTriggerNode = ['celery', 'restful', 'openai'].includes(data.type);

  // 处理执行按钮点击
  const handleExecuteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    // 触发自定义事件，由父组件处理
    const event = new CustomEvent('executeNode', {
      detail: { nodeId: id, nodeType: data.type }
    });
    window.dispatchEvent(event);
  };

  // Format node configuration information for display
  const formatConfigInfo = () => {
    const config = data.config;
    
    if (!config || Object.keys(config).length === 0) {
      return t('chatflow.notConfigured');
    }

    switch (data.type) {
      case 'celery':
        if (config.frequency) {
          const frequencyMap: { [key: string]: string } = {
            'daily': t('chatflow.daily'),
            'weekly': t('chatflow.weekly'), 
            'monthly': t('chatflow.monthly')
          };
          const timeStr = config.time ? ` ${config.time.format ? config.time.format('HH:mm') : config.time}` : '';
          const weekdayStr = config.weekday !== undefined ? ` ${t('chatflow.weekday')}${config.weekday}` : '';
          const dayStr = config.day ? ` ${config.day}${t('chatflow.day')}` : '';
          return `${frequencyMap[config.frequency] || config.frequency}${timeStr}${weekdayStr}${dayStr}`;
        }
        return t('chatflow.triggerFrequency') + ': --';

      case 'http':
        if (config.method && config.url) {
          return `${config.method} ${config.url}`;
        } else if (config.method) {
          return config.method;
        } else if (config.url) {
          return config.url;
        }
        return t('chatflow.httpMethod') + ': --';

      case 'agents':
        if (config.agent) {
          const agentDisplayName = config.agentName || config.agent;
          return t('chatflow.selectedAgent') + `: ${agentDisplayName}`;
        }
        return t('chatflow.selectedAgent') + ': --';

      case 'condition':
        if (config.conditionField && config.conditionOperator && config.conditionValue) {
          return `${config.conditionField} ${config.conditionOperator} ${config.conditionValue}`;
        }
        return t('chatflow.condition') + ': --';

      case 'restful':
      case 'openai':
        return t('chatflow.apiInterface');

      case 'notification':
        if (config.notificationType && config.notificationMethod && config.notificationChannels) {
          // Find the channel name from notificationChannels array
          const selectedChannel = config.notificationChannels.find((channel: any) => 
            channel.id === config.notificationMethod
          );
          const channelName = selectedChannel ? selectedChannel.name : `ID: ${config.notificationMethod}`;
          const typeDisplay = config.notificationType === 'email' ? t('chatflow.email') : t('chatflow.enterpriseWechatBot');
          return `${typeDisplay} - ${channelName}`;
        } else if (config.notificationType) {
          const typeDisplay = config.notificationType === 'email' ? t('chatflow.email') : t('chatflow.enterpriseWechatBot');
          return `${typeDisplay} - ${t('chatflow.notificationMethod')}: --`;
        }
        return t('chatflow.notificationCategory') + ': --';

      default:
        return t('chatflow.notConfigured');
    }
  };

  return (
    <div 
      className={`${styles.nodeContainer} ${selected ? styles.selected : ''} group relative cursor-pointer`}
      onClick={handleNodeClick}
    >
      {/* Input handle - appears on the left side */}
      {hasInput && (
        <Handle 
          type="target" 
          position={Position.Left} 
          className={`w-2.5 h-2.5 ${handleColorClasses[color as keyof typeof handleColorClasses] || handleColorClasses.blue} !border-2 !border-white shadow-md`} 
        />
      )}
      
      {/* Execute button for trigger nodes */}
      {isTriggerNode && (
        <button
          onClick={handleExecuteClick}
          className="absolute -top-3 -right-3 w-8 h-8 bg-green-500 hover:bg-green-600 rounded-full flex items-center justify-center shadow-lg transition-colors z-10"
          title={t('chatflow.executeNode')}
        >
          <PlayCircleOutlined className="text-white text-xl" />
        </button>
      )}
      
      <div className={styles.nodeHeader}>
        <Icon type={icon} className={`${styles.nodeIcon} text-${color}-500`} />
        <span className={styles.nodeTitle}>{data.label}</span>
      </div>
      
      <div className={styles.nodeContent}>
        <div className={styles.nodeConfigInfo}>
          {formatConfigInfo()}
        </div>
        {data.description && (
          <p className={styles.nodeDescription}>
            {data.description}
          </p>
        )}
      </div>
      
      {/* Single output handle - appears on the right side */}
      {hasOutput && !hasMultipleOutputs && (
        <Handle 
          type="source" 
          position={Position.Right} 
          className={`w-2.5 h-2.5 ${handleColorClasses[color as keyof typeof handleColorClasses] || handleColorClasses.blue} !border-2 !border-white shadow-md`} 
        />
      )}
      
      {/* Multiple output handles - for condition nodes (true/false branches) */}
      {hasMultipleOutputs && (
        <>
          <Handle 
            type="source" 
            position={Position.Right} 
            className="w-2.5 h-2.5 !bg-green-500 !border-2 !border-white shadow-md" 
            id="true"
            style={{ top: '30%' }}
          />
          <Handle 
            type="source" 
            position={Position.Right} 
            className="w-2.5 h-2.5 !bg-red-500 !border-2 !border-white shadow-md" 
            id="false"
            style={{ top: '70%' }}
          />
        </>
      )}
    </div>
  );
};

// Specific node type components
const TimeTriggerNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.celery.icon} color={nodeConfig.celery.color} hasOutput={true} />
);

const RestfulApiNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.restful.icon} color={nodeConfig.restful.color} hasOutput={true} />
);

const OpenAIApiNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.openai.icon} color={nodeConfig.openai.color} hasOutput={true} />
);

const AgentsNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.agents.icon} color={nodeConfig.agents.color} hasInput={true} hasOutput={true} />
);

const HttpRequestNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.http.icon} color={nodeConfig.http.color} hasInput={true} hasOutput={true} />
);

const IfConditionNode = (props: any) => (
  <BaseNode 
    {...props} 
    icon={nodeConfig.condition.icon} 
    color={nodeConfig.condition.color} 
    hasInput={true} 
    hasOutput={false}
    hasMultipleOutputs={true} 
  />
);

const NotificationNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.notification.icon} color={nodeConfig.notification.color} hasInput={true} hasOutput={true} />
);

interface ChatflowEditorRef {
  clearCanvas: () => void;
}

interface ChatflowEditorProps {
  onSave?: (nodes: Node[], edges: Edge[]) => void;
  initialData?: { nodes: Node[], edges: Edge[] } | null;
}

const ChatflowEditor = forwardRef<ChatflowEditorRef, ChatflowEditorProps>(({ onSave, initialData }, ref) => {
  const { t } = useTranslation();
  const { executeWorkflow } = useStudioApi();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);
  const [selectedNode, setSelectedNode] = useState<ChatflowNode | null>(null);
  const [isConfigDrawerVisible, setIsConfigDrawerVisible] = useState(false);
  const [selectedNodes, setSelectedNodes] = useState<Node[]>([]);
  const [selectedEdges, setSelectedEdges] = useState<Edge[]>([]);
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 0.6 });

  // 添加执行相关状态
  const [isExecuteDrawerVisible, setIsExecuteDrawerVisible] = useState(false);
  const [executeNodeId, setExecuteNodeId] = useState<string>('');
  const [executeMessage, setExecuteMessage] = useState<string>('');
  const [executeResult, setExecuteResult] = useState<any>(null);
  const [executeLoading, setExecuteLoading] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState(
    initialData?.nodes && Array.isArray(initialData.nodes) ? initialData.nodes : []
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(
    initialData?.edges && Array.isArray(initialData.edges) ? initialData.edges : []
  );

  // Auto-save functionality: save changes automatically when nodes or edges change
  const [isInitialized, setIsInitialized] = useState(false);
  const lastSaveData = useRef<string>('');
  
  useEffect(() => {
    // Skip auto-save on initial load
    if (!isInitialized) {
      setIsInitialized(true);
      return;
    }
    
    if (isInitialized && onSave) {
      const currentData = JSON.stringify({ 
        nodes: nodes.map(n => ({ id: n.id, type: n.type, position: n.position, data: n.data })), 
        edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target }))
      });
      
      // Only save if data has actually changed
      if (currentData !== lastSaveData.current) {
        lastSaveData.current = currentData;
        
        // Debounce save operation to avoid excessive saves
        const timeoutId = setTimeout(() => {
          console.log('ChatflowEditor: Saving data changes', { 
            nodes: nodes.length, 
            edges: edges.length,
            actualNodes: nodes,
            actualEdges: edges
          });
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

  useImperativeHandle(ref, () => ({
    clearCanvas
  }), [clearCanvas]);

  const handleDeleteNode = useCallback((nodeId: string) => {
    Modal.confirm({
      title: t('chatflow.messages.deleteConfirm'),
      onOk: () => {
        setNodes((nds) => nds.filter((n) => n.id !== nodeId));
        setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
        setIsConfigDrawerVisible(false);
        message.success(t('chatflow.messages.nodeDeleted'));
      }
    });
  }, [setNodes, setEdges, t]);

  const handleConfigNode = useCallback((nodeId: string) => {
    const node = nodes.find(n => n.id === nodeId);
    if (node && isChatflowNode(node)) {
      setSelectedNode(node);
      setIsConfigDrawerVisible(true);
    } else {
      console.log('Node not found or type mismatch:', nodeId);
    }
  }, [nodes]);

  // Create node type mapping with wrapped components that include event handlers
  const nodeTypes: NodeTypes = useMemo(() => {
    const createNodeComponent = (Component: React.ComponentType<any>) => {
      const NodeComponentWithProps = (props: any) => (
        <Component 
          {...props} 
          onDelete={handleDeleteNode} 
          onConfig={handleConfigNode}
        />
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
    };
  }, [handleDeleteNode, handleConfigNode]);

  const onInit = useCallback((instance: any) => {
    setReactFlowInstance(instance);
    const currentViewport = instance.getViewport();
    setViewport(currentViewport);
  }, []);

  const onMove = useCallback((event: any, newViewport: any) => {
    setViewport(newViewport);
  }, []);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onSelectionChange = useCallback((params: { nodes: Node[]; edges: Edge[] }) => {
    setSelectedNodes(params.nodes);
    setSelectedEdges(params.edges);
  }, []);

  // Handle Delete/Backspace key press for removing selected nodes and edges
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if ((event.key === 'Delete' || event.key === 'Backspace') && (selectedNodes.length > 0 || selectedEdges.length > 0)) {
      event.preventDefault();
      
      const hasNodes = selectedNodes.length > 0;
      const hasEdges = selectedEdges.length > 0;
      
      if (hasNodes) {
        // Save current selection state to prevent changes during confirmation dialog
        const currentSelectedNodes = [...selectedNodes];
        const currentSelectedEdges = [...selectedEdges];
        
        let title = '';
        let content = '';
        
        if (currentSelectedNodes.length === 1) {
          const nodeToDelete = currentSelectedNodes[0];
          title = t('chatflow.messages.deleteConfirm');
          content = `${t('chatflow.messages.deleteNodeContent')} ${nodeToDelete.data.label}`;
        } else {
          title = t('chatflow.messages.deleteMultipleConfirm');
          content = `${t('chatflow.messages.deleteMultipleContent')} ${currentSelectedNodes.length}`;
        }

        Modal.confirm({
          title,
          content,
          okText: t('common.confirm'),
          cancelText: t('common.cancel'),
          okButtonProps: { danger: true },
          onOk: () => {
            const selectedNodeIds = currentSelectedNodes.map(node => node.id);
            setNodes((nds) => nds.filter((n) => !selectedNodeIds.includes(n.id)));
            setEdges((eds) => eds.filter((e) => !selectedNodeIds.includes(e.source) && !selectedNodeIds.includes(e.target)));
            
            if (currentSelectedEdges.length > 0) {
              const selectedEdgeIds = currentSelectedEdges.map(edge => edge.id);
              setEdges((eds) => eds.filter((e) => !selectedEdgeIds.includes(e.id)));
            }
            
            setSelectedNodes([]);
            setSelectedEdges([]);
            setIsConfigDrawerVisible(false);
            
            if (currentSelectedEdges.length > 0) {
              message.success(`${t('chatflow.messages.itemsDeleted')} ${currentSelectedNodes.length} ${t('chatflow.messages.nodes')} ${currentSelectedEdges.length} ${t('chatflow.messages.edges')}`);
            } else {
              message.success(`${t('chatflow.messages.multipleNodesDeleted')} ${currentSelectedNodes.length}`);
            }
          },
          onCancel: () => {
            console.log('User cancelled deletion');
          }
        });
      } else if (hasEdges) {
        const selectedEdgeIds = selectedEdges.map(edge => edge.id);
        setEdges((eds) => eds.filter((e) => !selectedEdgeIds.includes(e.id)));
        
        setSelectedEdges([]);
        
        message.success(`${t('chatflow.messages.edgesDeleted')} ${selectedEdges.length}`);
      }
    }
  }, [selectedNodes, selectedEdges, setNodes, setEdges, t]);

  // Set up keyboard event listeners for the flow container
  useEffect(() => {
    const flowContainer = reactFlowWrapper.current;
    if (flowContainer) {
      flowContainer.tabIndex = 0; // Make container focusable
      flowContainer.addEventListener('keydown', handleKeyDown);
      
      return () => {
        flowContainer.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [handleKeyDown]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  // Handle drag and drop operations for adding new nodes to the canvas
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      
      try {
        const reactFlowBounds = reactFlowWrapper.current?.getBoundingClientRect();
        const type = event.dataTransfer.getData('application/reactflow');

        if (!type || !reactFlowBounds || !reactFlowInstance) {
          return;
        }

        // Calculate mouse position relative to ReactFlow container
        const mouseX = event.clientX - reactFlowBounds.left;
        const mouseY = event.clientY - reactFlowBounds.top;

        // Check if mouse is within canvas bounds
        if (mouseX < 0 || mouseY < 0 || mouseX > reactFlowBounds.width || mouseY > reactFlowBounds.height) {
          return;
        }

        // Convert screen coordinates to flow position using ReactFlow's built-in method
        const flowPosition = reactFlowInstance.screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });

        // Node dimensions for positioning adjustment
        const nodeWidth = 240;
        const nodeHeight = 120;
        
        // Adjust position to center node on mouse position
        const adjustedPosition = {
          x: flowPosition.x - nodeWidth / 2,
          y: flowPosition.y - nodeHeight / 2,
        };

        const getNodeLabel = (nodeType: string) => {
          try {
            return t(`chatflow.${nodeType}`);
          } catch {
            return nodeType;
          }
        };

        // Set default input/output parameters and node-specific configurations
        const getDefaultConfig = (nodeType: string) => {
          const baseConfig = {
            inputParams: 'last_message',
            outputParams: 'last_message'
          };

          // Add node-type specific default configurations
          switch (nodeType) {
            case 'celery':
              return {
                ...baseConfig,
                frequency: 'daily',
                time: null,
                message: ''
              };
            case 'http':
              return {
                ...baseConfig,
                method: 'GET',
                url: '',
                params: [],
                headers: [],
                requestBody: '',
                timeout: 30,
                outputMode: 'once'
              };
            case 'agents':
              return {
                ...baseConfig,
                agent: null,
                agentName: '',
                prompt: '',
                uploadedFiles: []
              };
            case 'condition':
              return {
                ...baseConfig,
                conditionField: '',
                conditionOperator: 'equals',
                conditionValue: ''
              };
            case 'restful':
            case 'openai':
              return baseConfig;
            default:
              return baseConfig;
          }
        };

        const newNode: ChatflowNode = {
          id: `${type}-${Date.now()}`,
          type,
          position: adjustedPosition,
          data: { 
            label: getNodeLabel(type),
            type: type as ChatflowNodeData['type'],
            config: getDefaultConfig(type),
            description: ''
          },
        };

        
        setNodes((nds) => {
          const updatedNodes = nds.concat(newNode);
          
          // Immediately trigger save after node addition
          setTimeout(() => {
            if (onSave) {
              onSave(updatedNodes, edges);
            }
          }, 50);
          
          return updatedNodes;
        });
        
      } catch (error) {
        console.error('Drag and drop error:', error);
        message.error(t('chatflow.messages.dragFailed'));
      }
    },
    [reactFlowInstance, setNodes, edges, onSave, t]
  );

  const handleSaveConfig = useCallback((nodeId: string, values: any) => {
    const { name, ...config } = values;
    
    setNodes((nds) => 
      nds.map((node) => 
        node.id === nodeId 
          ? { 
            ...node, 
            data: { 
              ...node.data, 
              label: name || node.data.label,
              config 
            } 
          }
          : node
      )
    );
    setIsConfigDrawerVisible(false);
  }, [setNodes]);

  // 处理执行节点事件
  useEffect(() => {
    const handleExecuteNode = (event: any) => {
      const { nodeId } = event.detail;
      setExecuteNodeId(nodeId);
      setExecuteMessage('');
      setExecuteResult(null);
      setIsExecuteDrawerVisible(true);
    };

    window.addEventListener('executeNode', handleExecuteNode);
    return () => {
      window.removeEventListener('executeNode', handleExecuteNode);
    };
  }, []);

  // 执行节点
  const handleExecuteNode = async () => {
    if (!executeNodeId) return;

    setExecuteLoading(true);
    try {
      const response = await executeWorkflow({
        message: executeMessage,
        bot_id: getBotIdFromUrl(),
        node_id: executeNodeId,
      });

      setExecuteResult(response);
      message.success(t('chatflow.executeSuccess'));
    } catch (error) {
      console.error('Execute node error:', error);
      message.error(t('chatflow.executeFailed'));
    } finally {
      setExecuteLoading(false);
    }
  };

  // 从URL获取botId的辅助函数
  const getBotIdFromUrl = () => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      return urlParams.get('id') || '1';
    }
    return '1';
  };

  return (
    <div className={styles.chatflowEditor}>
      <div 
        className={styles.flowContainer} 
        ref={reactFlowWrapper}
        onFocus={() => {
          if (reactFlowWrapper.current) {
            reactFlowWrapper.current.focus();
          }
        }}
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
            onDrop={onDrop}
            onDragOver={onDragOver}
            onSelectionChange={onSelectionChange}
            nodeTypes={nodeTypes}
            defaultViewport={viewport}
            onMove={onMove}
            minZoom={0.1}
            maxZoom={2}
            attributionPosition="bottom-left"
            fitView={false}
            fitViewOptions={{
              padding: 0.2,
              includeHiddenNodes: false,
            }}
            deleteKeyCode={null}
            selectionKeyCode={null}
            multiSelectionKeyCode={null}
          >
            <MiniMap 
              nodeColor="#1890ff"
              nodeStrokeColor="#f0f0f0"
              nodeStrokeWidth={1}
              maskColor="rgba(255, 255, 255, 0.8)"
              pannable={true}
              zoomable={true}
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

      {/* 执行节点侧边栏 */}
      <ExecuteNodeDrawer
        visible={isExecuteDrawerVisible}
        nodeId={executeNodeId}
        message={executeMessage}
        result={executeResult}
        loading={executeLoading}
        onMessageChange={setExecuteMessage}
        onExecute={handleExecuteNode}
        onClose={() => setIsExecuteDrawerVisible(false)}
      />
    </div>
  );
});

ChatflowEditor.displayName = 'ChatflowEditor';

export default ChatflowEditor;

// Export type definitions for use by other components
export type { ChatflowNodeData, ChatflowEditorRef };