/**
 * 图数据转换工具函数
 * 用于将 API 返回的图数据格式转换为 KnowledgeGraphView 组件所需的格式
 */

import { GraphData } from '@/app/opspilot/types/knowledge';

/**
 * 将 API 返回的图数据转换为标准图数据格式
 * @param graphData - API 返回的原始图数据数组
 * @returns 转换后的图数据，包含 nodes 和 edges 数组
 */
export const transformGraphData = (graphData: any): GraphData => {
  if (!graphData || !Array.isArray(graphData)) {
    return { nodes: [], edges: [] };
  }

  const nodesMap = new Map();
  const edges: any[] = [];

  graphData.forEach((relation: any, index: number) => {
    const { source_node, target_node, fact, name } = relation;
    
    if (!source_node || !target_node) {
      return;
    }

    // 添加源节点（如果不存在）
    if (source_node.uuid && !nodesMap.has(source_node.uuid)) {
      nodesMap.set(source_node.uuid, {
        id: source_node.uuid,
        label: source_node.name || `节点${source_node.uuid.slice(0, 8)}`,
        type: 'entity',
        labels: source_node.labels || [],
        uuid: source_node.uuid,
        name: source_node.name,
        summary: source_node.summary
      });
    }

    // 添加目标节点（如果不存在）
    if (target_node.uuid && !nodesMap.has(target_node.uuid)) {
      nodesMap.set(target_node.uuid, {
        id: target_node.uuid,
        label: target_node.name || `节点${target_node.uuid.slice(0, 8)}`,
        type: 'entity',
        labels: target_node.labels || [],
        uuid: target_node.uuid,
        name: target_node.name,
        summary: target_node.summary,
      });
    }

    // 添加边关系（如果两个节点都存在）
    if (source_node.uuid && target_node.uuid) {
      edges.push({
        id: `edge-${index}`,
        source: source_node.uuid,
        target: target_node.uuid,
        label: name,
        type: 'relation',
        relation_type: name,
        fact: fact
      });
    }
  });

  return {
    nodes: Array.from(nodesMap.values()) as any[],
    edges: edges
  };
};