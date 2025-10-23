import {
  ReactFlow,
  Node,
  Edge,
  addEdge,
  Connection,
  useNodesState,
  ReactFlowInstance,
  Background,
  Controls,
  MiniMap,
  Panel,
  getOutgoers,
  useEdgesState,
  useReactFlow,
  NodeTypes,
  IsValidConnection,
  EdgeTypes,
} from '@xyflow/react';
import { Button, Tooltip } from 'antd';
import { SaveOutlined, ReloadOutlined, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import { IntentNode, ResponseNode, SlotNode, FormNode, ActionNode, CheckPoint } from './CustomNodes';
import CustomEdge from './ButtonEdge';
import '@xyflow/react/dist/style.css';
import { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { NodeType, NodeData } from '@/app/mlops/types';
import { useTranslation } from '@/utils/i18n';
import NodePanel from './NodePanel';
import NodeDetailDrawer from './NodeDetail';
import flowStyle from './index.module.scss';

const NodeFlow = ({
  initialNodes,
  initialEdges,
  nodeTypes,
  dataset,
  panel = [],
  handleSaveFlow
}: {
  initialNodes: Node<NodeData>[],
  initialEdges: Edge[],
  nodeTypes: NodeType[],
  dataset: string,
  panel?: React.ReactNode[],
  handleSaveFlow: (data: any) => void;
}) => {
  const { t } = useTranslation();
  const { getNodes, getEdges, screenToFlowPosition } = useReactFlow();
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance<Node<NodeData>> | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NodeData>>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [detailOpen, setDetailOpen] = useState<boolean>(false);
  const [currentNode, setCurrentNode] = useState<Node | null>(null);
  const [visiable, setVisiable] = useState<boolean>(false); // 缩略图显示控制

  // 用于存储边重连时的引用
  const edgeReconnectSuccessful = useRef(true);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  // 处理链接线
  const onConnect = useCallback(
    (params: Connection) => {
      const currentNodes = getNodes();
      const sourceNode = currentNodes.find((item) => item.id === params.source);
      const targetNode = currentNodes.find((item) => item.id === params.target);

      if (params.source === params.target) return;

      setEdges((eds) => addEdge({ ...params, animated: true, type: 'buttonedge' }, eds));
      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === params.source || node.id === params.target) {
            return {
              ...node,
              data: {
                ...node.data,
                source: node.id === params.source ? [...node.data.source, {
                  id: targetNode?.id,
                  name: targetNode?.data.name,
                  type: targetNode?.type
                }] : node.data?.source,
                target: node.id === params.target ? [...node.data.target, {
                  id: sourceNode?.id,
                  name: sourceNode?.data.name,
                  type: sourceNode?.type
                }] : node.data?.target
              }
            }
          }
          return node;
        })
      );
    },
    [setEdges, setNodes, getNodes]
  );

  // 处理边重连开始
  const onReconnectStart = useCallback(() => {
    edgeReconnectSuccessful.current = false;
  }, []);

  // 处理边重连结束
  // const onReconnectEnd = useCallback((_: any, edge: Edge) => {
  const onReconnectEnd = useCallback(() => {
    // if (!edgeReconnectSuccessful.current) {
    //   // 如果重连失败，移除这条边
    //   setEdges((eds) => eds.filter((e) => e.id !== edge.id));
    // }
    edgeReconnectSuccessful.current = true;
  }, []);

  // 主要的边重连处理函数
  const onReconnect = useCallback(
    (oldEdge: Edge, newConnection: Connection) => {
      const nodeSet = new Set([oldEdge.source, oldEdge.target, newConnection.source, newConnection.target]);

      // 标记重连成功
      edgeReconnectSuccessful.current = true;

      // 判断是源节点还是目标节点发生了改变
      const sourceChanged = oldEdge.source !== newConnection.source;
      const targetChanged = oldEdge.target !== newConnection.target;


      if (!sourceChanged && !targetChanged) {
        return;
      }

      // 获取当前节点状态
      const currentNodes = getNodes();
      const sourceNode = currentNodes.find((item) => item.id === newConnection.source);
      const targetNode = currentNodes.find(n => n.id === newConnection.target);

      // 手动更新边：移除旧边，添加新边
      setEdges((eds) => {
        const filteredEdges = eds.filter((e) => e.id !== oldEdge.id);
        const newEdge: Edge = {
          ...oldEdge,
          source: newConnection.source!,
          target: newConnection.target!,
          sourceHandle: newConnection.sourceHandle,
          targetHandle: newConnection.targetHandle,
        };
        return [...filteredEdges, newEdge];
      });

      // 更新节点的数据关系
      setNodes((nds) =>
        nds.map((node) => {
          if (!nodeSet.has(node.id)) return node;
          const updatedNode = { ...node };

          // 如果源节点发生了改变
          if (sourceChanged) {
            // 从旧的源节点中移除目标引用
            if (updatedNode.id === oldEdge.source) {
              updatedNode.data = {
                ...updatedNode.data,
                source: updatedNode.data.source.filter((item: { id: string, type: string, name: string }) =>
                  item.id !== oldEdge.target
                )
              };
            }

            if (updatedNode.id === oldEdge.target) {
              updatedNode.data = {
                ...updatedNode.data,
                target: updatedNode.data.target.map((item: any) => {
                  if (item.id === oldEdge.source) {
                    return {
                      id: sourceNode?.id,
                      name: sourceNode?.data.name,
                      type: sourceNode?.type
                    }
                  } else {
                    return item;
                  }

                })
              }
            }

            // 为新的源节点添加目标引用
            if (updatedNode.id === newConnection.source) {
              if (targetNode) {
                const targetRef = {
                  id: targetNode.id,
                  name: targetNode.data.name,
                  type: targetNode.type!
                };

                // 检查是否已存在相同的引用
                const existingTarget = updatedNode.data.source.find((item: { id: string, type: string, name: string }) =>
                  item.id === newConnection.target
                );

                if (!existingTarget) {
                  updatedNode.data = {
                    ...updatedNode.data,
                    source: [...updatedNode.data.source, targetRef]
                  };
                }
              }
            }
          }

          // 如果目标节点发生了改变
          if (targetChanged) {
            // 从旧的目标节点中移除源引用
            if (updatedNode.id === oldEdge.target) {
              updatedNode.data = {
                ...updatedNode.data,
                target: updatedNode.data.target.filter((item: { id: string, type: string, name: string }) =>
                  item.id !== oldEdge.source
                )
              };
            }

            if (updatedNode.id === oldEdge.source) {
              updatedNode.data = {
                ...updatedNode.data,
                source: updatedNode.data.source.map((item: any) => {
                  if (item.id === oldEdge.target) {
                    // const targetNode = currentNodes.find((item) => item.id === newConnection.target);
                    return {
                      id: targetNode?.id,
                      name: targetNode?.data.name,
                      type: targetNode?.type
                    }
                  } else {
                    return item
                  }
                })
              }
            }

            // 为新的目标节点添加源引用
            if (updatedNode.id === newConnection.target) {
              // const sourceNode = currentNodes.find(n => n.id === newConnection.source);
              if (sourceNode) {
                const sourceRef = {
                  id: sourceNode.id,
                  name: sourceNode.data.name,
                  type: sourceNode.type!
                };

                // 检查是否已存在相同的引用
                const existingSource = updatedNode.data.target.find((item: { id: string, type: string, name: string }) =>
                  item.id === newConnection.source
                );

                if (!existingSource) {
                  updatedNode.data = {
                    ...updatedNode.data,
                    target: [...updatedNode.data.target, sourceRef]
                  };
                }
              }
            }
          }

          return updatedNode;
        })
      );
    },
    [setEdges, setNodes, getNodes]
  );

  // 处理拖拽开始
  const onDragStart = useCallback((event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  }, []);

  // 处理拖拽悬停
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  // 获取默认节点数据
  const getDefaultNodeData = useCallback((type: string) => {
    return {
      type: type,
      name: '',
      target: [],
      source: []
    }
  }, []);

  // 处理拖拽放下
  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    const type = event.dataTransfer.getData('application/reactflow');

    // 校验节点类型
    if (typeof type === 'undefined' || !type) {
      return;
    }

    // 计算放下位置
    const position = screenToFlowPosition({
      x: event.clientX,
      y: event.clientY
    });

    if (!position) return;

    // 创建新节点
    const newNode: Node<NodeData> = {
      id: `${type}_${Date.now()}`,
      type,
      position,
      data: { ...getDefaultNodeData(type) }
    };

    setNodes((nds) => nds.concat(newNode));
  }, [setNodes, screenToFlowPosition, getDefaultNodeData]);

  const onSave = useCallback(() => {
    if (rfInstance) {
      const flow = rfInstance.toObject();
      handleSaveFlow(flow);
    }
  }, [rfInstance, handleSaveFlow]);

  const onRestore = useCallback(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [setNodes, setEdges, initialNodes, initialEdges]);

  // 选中节点处理
  const handleNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    if (node) {
      setDetailOpen(true);
      setCurrentNode(node);
    }
  }, []);

  // 更改节点详情处理
  const handleChangeNodeDetail = useCallback((name: string, type: string) => {
    const newId = `${type}_${name}_${Date.now()}`;
    const _nodes = nodes.map((item) => {
      if (item.id === currentNode?.id) {
        const node = {
          ...item,
          id: newId,
          data: {
            ...item.data,
            id: `${item.type}_${name}`,
            name: name,
          }
        };
        return node;
      }

      return {
        ...item,
        data: {
          ...item.data,
          source: item.data.source.map((ref: { id: string, type: string, name: string }) => {
            if (ref.id !== currentNode?.id) {
              return ref
            } else {
              return {
                id: newId,
                type,
                name
              }
            }
          }),
          target: item.data.target.map((ref: { id: string, type: string, name: string }) => {
            if (ref.id !== currentNode?.id) {
              return ref
            } else {
              return {
                id: newId,
                type,
                name
              }
            }
          }),
        }
      };
    });

    const _edges = edges.map((item) => {
      if ([item.target, item.source].includes(currentNode?.id as string)) {
        return {
          ...item,
          source: item.source === currentNode?.id ? newId : item.source,
          target: item.target === currentNode?.id ? newId : item.target
        }
      }
      return item;
    });

    setEdges(_edges);
    setNodes(_nodes);
  }, [currentNode, setNodes, setEdges]);

  // 删除节点处理
  const handleDelNode = useCallback(() => {
    const _nodes = nodes.filter((item) => item.id !== currentNode?.id).map((item) => {
      return {
        ...item,
        data: {
          ...item.data,
          source: item.data?.source.filter((item: any) => item?.id !== currentNode?.id),
          target: item.data?.target.filter((item: any) => item?.id !== currentNode?.id),
        }
      }
    });
    const _edges = edges.filter((item) => ![item.source, item.target].includes(currentNode?.id as string));
    setNodes(_nodes);
    setEdges(_edges);
  }, [nodes, edges, currentNode, setNodes, setEdges]);

  // 循环链接判断
  const isValidConnection: IsValidConnection<Edge> = useCallback(
    (connection) => {
      const nodes = getNodes();
      const edges = getEdges();
      const target = nodes.find((node) => node.id === connection.target);
      const hasCycle = (node: any, visited = new Set()) => {
        if (visited.has(node.id)) return false;

        visited.add(node.id);

        for (const outgoer of getOutgoers(node, nodes, edges)) {
          if (outgoer.id === connection.source) return true;
          if (hasCycle(outgoer, visited)) return true;
        }
      };

      if (target?.id === connection.source) return false;
      return !hasCycle(target);
    },
    [getNodes, getEdges],
  );

  const customNodeTypes: NodeTypes = useMemo(() => ({
    intent: IntentNode,
    response: ResponseNode,
    slot: SlotNode,
    form: FormNode,
    action: ActionNode,
    checkpoint: CheckPoint
  }), []);

  const edgeTypes: EdgeTypes = useMemo(() => ({
    buttonedge: CustomEdge,
  }), []);

  const getNodeColor = useCallback((node: Node<NodeData>) => {
    switch (node.type) {
      case 'intent':
        return '#0ea5e9';
      case 'response':
        return '#14b8a6';
      case 'slot':
        return '#22c55e';
      case 'form':
        return '#ef4444';
      case 'action':
        return '#3b82f6';
      case 'checkpoint':
        return '#f97316';
      default:
        return '#64748b';
    }
  }, []);

  // 根据节点状态调整颜色透明度
  const getNodeColorWithState = useCallback((node: Node<NodeData>) => {
    const baseColor = getNodeColor(node);

    // 如果节点没有名称，显示为半透明
    if (!node.data?.name) {
      return baseColor + '80'; // 添加50%透明度
    }

    // 如果节点被选中，增加亮度
    if (node.selected) {
      return baseColor;
    }

    return baseColor;
  }, [getNodeColor]);

  return (
    <div className={`${flowStyle.flowContainer} flex w-full h-full relative`}>
      {/*节点面板 */}
      <NodePanel onDragStart={onDragStart} nodeTypes={nodeTypes} />
      {/* 节点详情 */}
      <NodeDetailDrawer
        open={detailOpen}
        dataset={dataset}
        node={currentNode as Node}
        handleDelNode={handleDelNode}
        onChange={handleChangeNodeDetail}
        onClose={() => setDetailOpen(false)}
      />
      <ReactFlow<Node<NodeData>>
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onReconnect={onReconnect}
        onReconnectStart={onReconnectStart}
        onReconnectEnd={onReconnectEnd}
        onInit={setRfInstance}
        isValidConnection={isValidConnection}
        onDrop={onDrop}
        onDragOver={onDragOver}
        fitView
        nodeTypes={customNodeTypes}
        edgeTypes={edgeTypes}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Panel position='top-right'>
          <div className="flex bg-white" style={{ boxShadow: '0px 0px 1px 1px #f3f4f6' }}>
            <Tooltip title={t(`common.save`)}>
              <Button
                key="save"
                size="small"
                type="text"
                icon={<SaveOutlined />}
                onClick={onSave}
                className="border rounded-none border-gray-300 hover:border-blue-400 hover:text-blue-500"
                style={{
                  width: 26,
                  height: 26,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',

                }}
              />
            </Tooltip>

            <Tooltip title={t(`mlops-common.reset`)}>
              <Button
                key="reset"
                size="small"
                type="text"
                icon={<ReloadOutlined />}
                onClick={onRestore}
                className="border rounded-none border-gray-300 hover:border-orange-400 hover:text-orange-500"
                style={{
                  width: 26,
                  height: 26,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              />
            </Tooltip>

            <Tooltip title={t(`mlops-common.${visiable ? 'hide' : 'show'}Thumbnail`)}>
              <Button
                key="visiable"
                size="small"
                type="text"
                icon={visiable ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                onClick={() => setVisiable(prev => !prev)}
                className="border rounded-none border-gray-300 hover:border-purple-400 hover:text-purple-500"
                style={{
                  width: 26,
                  height: 26,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              />
            </Tooltip>
            {panel?.length > 0 && panel}
          </div>
        </Panel>
        <Controls position='top-left' orientation="horizontal" />
        {/* 优化后的 MiniMap */}
        {visiable && (
          <MiniMap
            nodeColor={getNodeColorWithState}
            nodeStrokeColor={(node: Node<NodeData>) => {
              if (node.selected) {
                return '#1f2937';
              }
              return node.data?.name ? '#ffffff' : '#e5e7eb';
            }}
            nodeBorderRadius={6}
            maskColor="rgba(15, 23, 42, 0.15)"
            maskStrokeColor="#334155"
            maskStrokeWidth={1.5}
            position="bottom-right"
            style={{
              backgroundColor: 'rgba(248, 250, 252, 0.98)',
              border: '1px solid #cbd5e1',
              borderRadius: '16px',
              backdropFilter: 'blur(12px) saturate(150%)',
              width: 200,
              height: 160,
            }}
            pannable
            zoomable
            inversePan
            zoomStep={0.5}
          />
        )}
      </ReactFlow>
    </div>
  )
};

export default NodeFlow;