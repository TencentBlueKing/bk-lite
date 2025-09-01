import {
  ReactFlow,
  Node,
  Edge,
  addEdge,
  Connection,
  useNodesState,
  // ReactFlowProvider,
  ReactFlowInstance,
  Background,
  Controls,
  // MiniMap,
  Panel,
  getOutgoers,
  useEdgesState,
  useReactFlow,
  NodeTypes,
  IsValidConnection
} from '@xyflow/react';
import { Button } from 'antd';
import { IntentNode, ResponseNode, SlotNode, FormNode } from './CustomNodes';
import '@xyflow/react/dist/style.css';
import { useCallback, useMemo, useState } from 'react';
import { NodeType } from '@/app/mlops/types';
import { useTranslation } from '@/utils/i18n';
import NodePanel from './NodePanel';
import NodeDetailDrawer from './NodeDetail';

const NodeFlow = ({
  initialNodes,
  initialEdges,
  nodeTypes,
  dataset,
  panel = [],
  handleSaveFlow
}: {
  initialNodes: Node[],
  initialEdges: Edge[],
  nodeTypes: NodeType[],
  dataset: string,
  panel?: React.ReactNode[],
  handleSaveFlow: (data: any) => void;
}) => {
  const { t } = useTranslation();
  const { getNodes, getEdges, screenToFlowPosition } = useReactFlow();
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [detailOpen, setDetailOpen] = useState<boolean>(false);
  const [currentNode, setCurrentNode] = useState<Node | null>(null);

  // 处理链接线
  const onConnect = useCallback(
    (params: Connection) => {
      console.log(params);
      if (params.source === params.target) return;
      setEdges((eds) => addEdge(params, eds));
      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === params.source || node.id === params.target) {
            return {
              ...node,
              data: {
                ...node.data,
                source: node.id === params.source ? params.target : node.data?.source,
                target: node.id === params.target ? params.source : node.data?.target
              }
            }
          }
          return node;
        })
      );
    },
    [setEdges]
  );

  // 处理拖拽开始
  const onDragStart = (event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  // 处理拖拽悬停
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
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
    const newNode: Node = {
      id: `${type}_${Date.now()}`,
      type,
      position,
      data: { label: `${getNodeLabel(type)}`, ...getDefaultNodeData(type) }
    };

    setNodes((nds) => nds.concat(newNode));
  }, [setNodes, screenToFlowPosition]);

  const onSave = useCallback(() => {
    if (rfInstance) {
      const flow = rfInstance.toObject();
      handleSaveFlow(flow);
    }
  }, [rfInstance, handleSaveFlow]);

  const onRestore = useCallback(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [setNodes]);

  // 获取节点标签
  const getNodeLabel = (type: string) => {
    const labels: Record<string, string> = {
      intent: t(`datasets.intentNode`),
      response: t(`datasets.responseNode`),
      slot: t(`datasets.slotNode`)
    };

    return labels[type] || t(`mlops-common.defaultNode`);
  };

  // 选中节点处理
  const handleNodeClick = (event: React.MouseEvent, node: Node) => {
    if (node) {
      setDetailOpen(true);
      setCurrentNode(node);
    }
  };

  // 更改节点详情处理
  const handleChangeNodeDetail = (data: any) => {
    const _nodes = nodes.map((item) => {
      if (item.id === currentNode?.id) {
        return {
          ...item,
          id: `${item.type}_${data?.name}_${Date.now()}`,
          data: {
            id: `${item.type}_${data?.name}`,
            name: data?.name,
          }
        }
      }
      return {
        ...item,
        data: {
          ...item.data,
          source: item.data?.source === currentNode?.id ? null : item.data?.source,
          target: item.data?.target === currentNode?.id ? null : item.data?.target,
        }
      };
    });
    // const _edges = edges.map((item) => {
    //   if(item.target === currentNode?.id) {
    //     return {
    //       ...item,
    //       target: data?.name
    //     }
    //   }
    //   if(item.source === currentNode?.id) {
    //     return {
    //       ...item,
    //       source: data?.name
    //     }
    //   }
    //   return item;
    // });
    const _edges = edges.filter(item => ![item.source, item.target].includes(currentNode?.id as string));

    setEdges(_edges);
    setNodes(_nodes);
  };

  // 删除节点处理
  const handleDelNode = () => {
    const _nodes = nodes.filter((item) => item.id !== currentNode?.id);
    const _edges = edges.filter((item) => ![item.source, item.target].includes(currentNode?.id as string));
    setNodes(_nodes);
    setEdges(_edges);
  };

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

  // 获取默认节点数据
  const getDefaultNodeData = (type: string) => {
    // switch (type) {
    //   case 'intent':
    //     return {
    //       target: null,
    //       source: null
    //     };
    //   case 'response':
    //     return {};
    //   default:
    //     return {}
    // }
    return {
      type: type,
      name: '',
      target: null,
      source: null
    }
  };

  const customNodeTypes: NodeTypes = useMemo(() => ({
    intent: IntentNode,
    response: ResponseNode,
    slot: SlotNode,
    form: FormNode,
  }), [])

  return (
    <div className='flex w-full h-full relative'>
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
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={setRfInstance}
        isValidConnection={isValidConnection}
        onDrop={onDrop}
        onDragOver={onDragOver}
        fitView
        nodeTypes={customNodeTypes}
      >
        <Background />
        <Panel position='top-right'>
          <Button
            key="save"
            size="small"
            color="default"
            variant="outlined"
            className="mr-2 text-xs"
            onClick={onSave}
          >{t(`common.save`)}</Button>
          <Button
            key="reset"
            size="small"
            variant="outlined"
            className="mr-2 text-xs"
            onClick={onRestore}
          >{t(`mlops-common.reset`)}</Button>
          {panel?.length > 0 && panel}
        </Panel>
        <Controls />
        {/* <MiniMap /> */}
      </ReactFlow>
    </div>
  )
};

export default NodeFlow;