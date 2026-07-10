import {
  K8S_TOPOLOGY_LAYERS,
  K8sLayer,
  K8sTopologyData,
  K8sTopologyEdge,
  K8sTopologyNode,
} from './model';

export interface TopologyNodeBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface TopologyPath {
  id: string;
  d: string;
}

export const getTopologyFocus = (
  selectedId: string | null,
  topology: K8sTopologyData
) => {
  if (!selectedId) {
    return { nodes: new Set<string>(), edges: new Set<string>() };
  }
  const nodes = new Set([selectedId]);
  const edges = new Set<string>();
  const ancestors = [selectedId];
  const descendants = [selectedId];

  while (ancestors.length) {
    const current = ancestors.shift()!;
    topology.edges.forEach((edge) => {
      if (edge.target !== current || nodes.has(edge.source)) return;
      nodes.add(edge.source);
      edges.add(edge.id);
      ancestors.push(edge.source);
    });
  }

  while (descendants.length) {
    const current = descendants.shift()!;
    topology.edges.forEach((edge) => {
      if (edge.source !== current || nodes.has(edge.target)) return;
      nodes.add(edge.target);
      edges.add(edge.id);
      descendants.push(edge.target);
    });
  }

  return { nodes, edges };
};

export const groupTopologyNodes = (
  nodes: K8sTopologyNode[]
): Record<K8sLayer, K8sTopologyNode[]> => {
  const grouped: Record<K8sLayer, K8sTopologyNode[]> = {
    cluster: [],
    namespace: [],
    workload: [],
    pod: [],
    node: [],
  };
  nodes.forEach((node) => grouped[node.layer].push(node));
  K8S_TOPOLOGY_LAYERS.forEach((layer) => {
    grouped[layer].sort((left, right) =>
      Number(left.model_id === 'virtual') - Number(right.model_id === 'virtual')
      || left.name.localeCompare(right.name)
    );
  });
  return grouped;
};

export const buildTopologyPaths = (
  edges: K8sTopologyEdge[],
  boxes: Map<string, TopologyNodeBox>
): TopologyPath[] => edges.flatMap((edge) => {
  const source = boxes.get(edge.source);
  const target = boxes.get(edge.target);
  if (!source || !target) return [];

  const sourceX = source.left + source.width;
  const sourceY = source.top + source.height / 2;
  const targetX = target.left;
  const targetY = target.top + target.height / 2;
  const controlX = sourceX + (targetX - sourceX) / 2;
  return [{
    id: edge.id,
    d: `M ${sourceX} ${sourceY} C ${controlX} ${sourceY}, ${controlX} ${targetY}, ${targetX} ${targetY}`,
  }];
});
