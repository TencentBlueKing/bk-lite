import { Graph, Edge } from '@antv/x6';
import { v4 as uuidv4 } from 'uuid';
import { getEdgeStyleWithConfig, addEdgeTools, calculateOptimalPorts } from './topologyUtils';
import type { EdgeData } from '@/app/ops-analysis/types/topology';
import { COLORS } from '../constants/nodeDefaults';

// 边创建配置接口
interface EdgeCreationConfig {
  sourceNodeId: string;
  targetNodeId: string;
  connectionType: 'none' | 'single' | 'double';
  lineType?: 'common_line' | 'network_line';
  lineName?: string;
  vertices?: Array<{ x: number; y: number }>;
}

// 边默认配置
const EDGE_DEFAULTS = {
  connector: { name: 'normal' },
  router: { name: 'manhattan' },
  shape: 'standard-edge',
  lineType: 'common_line' as const,
  lineName: '',
} as const;

// 注册标准边类型
export const registerStandardEdge = () => {
  Graph.registerEdge('standard-edge', {
    inherit: 'edge',
    connector: EDGE_DEFAULTS.connector,
    router: EDGE_DEFAULTS.router,
    attrs: {
      line: {
        stroke: COLORS.EDGE.DEFAULT,
        strokeWidth: 1,
      },
    },
  });
};

// 创建边的通用函数
export const createEdge = (graphInstance: any, config: EdgeCreationConfig): Edge | null => {
  if (!graphInstance) return null;

  const sourceNode = graphInstance.getCellById(config.sourceNodeId);
  const targetNode = graphInstance.getCellById(config.targetNodeId);

  if (!sourceNode || !targetNode) return null;

  // 计算最佳连接端口
  const { sourcePort, targetPort } = calculateOptimalPorts(sourceNode, targetNode);

  // 默认样式配置
  const defaultStyleConfig = {
    lineColor: COLORS.EDGE.DEFAULT,
    lineWidth: 1,
    lineStyle: 'line' as const,
    enableAnimation: false,
  };

  // 创建边
  const edge = graphInstance.createEdge({
    id: `edge_${uuidv4()}`,
    source: {
      cell: config.sourceNodeId,
      port: sourcePort,
    },
    target: {
      cell: config.targetNodeId,
      port: targetPort,
    },
    shape: EDGE_DEFAULTS.shape,
    connector: EDGE_DEFAULTS.connector,
    router: EDGE_DEFAULTS.router,
    ...getEdgeStyleWithConfig(config.connectionType, defaultStyleConfig),
  });

  // 添加到图中
  graphInstance.addCell(edge);

  // 设置边数据
  edge.setData({
    arrowDirection: config.connectionType, 
    lineType: config.lineType || EDGE_DEFAULTS.lineType,
    lineName: config.lineName || EDGE_DEFAULTS.lineName,
    vertices: config.vertices || [],
    styleConfig: defaultStyleConfig
  });

  // 如果有拐点数据，恢复拐点
  if (config.vertices && config.vertices.length > 0) {
    edge.setVertices(config.vertices);
  }

  // 添加边工具
  addEdgeTools(edge);

  return edge;
};

// 创建边数据对象
const createEdgeData = (edge: Edge, sourceNode: any, targetNode: any): EdgeData => {
  const getNodeName = (node: any): string => {
    const nodeData = node.getData?.();
    if (nodeData?.name) return nodeData.name;

    const attrs = node.getAttrs?.();
    if (attrs?.label?.text) return attrs.label.text;

    return node.id;
  };

  const edgeData = edge.getData() || {};

  return {
    id: edge.id,
    lineType: edgeData.lineType || 'common_line',
    lineName: edgeData.lineName || '',
    arrowDirection: edgeData.arrowDirection || 'single', 
    styleConfig: edgeData.styleConfig || { lineColor: COLORS.EDGE.DEFAULT },
    sourceNode: {
      id: sourceNode.id,
      name: getNodeName(sourceNode),
    },
    targetNode: {
      id: targetNode.id,
      name: getNodeName(targetNode),
    },
  };
};

// 边注册管理
const registeredEdges = new Set<string>();

export const registerEdges = () => {
  try {
    if (!registeredEdges.has('standard-edge')) {
      registerStandardEdge();
      registeredEdges.add('standard-edge');
    }
  } catch (error) {
    console.warn('边注册失败:', error);
  }
};

// 边创建工厂函数
export const createEdgeByType = (
  graphInstance: any,
  sourceNodeId: string,
  targetNodeId: string,
  connectionType: 'none' | 'single' | 'double' = 'single'
): { edge: Edge | null; edgeData: EdgeData | null } => {
  const config: EdgeCreationConfig = {
    sourceNodeId,
    targetNodeId,
    connectionType,
  };

  const edge = createEdge(graphInstance, config);

  if (!edge) {
    return { edge: null, edgeData: null };
  }

  const sourceNode = graphInstance.getCellById(sourceNodeId);
  const targetNode = graphInstance.getCellById(targetNodeId);
  const edgeData = createEdgeData(edge, sourceNode, targetNode);

  return { edge, edgeData };
};
