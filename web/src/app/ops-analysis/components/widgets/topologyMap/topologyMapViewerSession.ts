import type {
  PositionedTopologyMapNode,
  TopologyMapNode,
  TopologyMapPayload,
} from '@/app/ops-analysis/utils/topologyMapData';

export const buildTopologyMapStructureSignature = (
  payload: TopologyMapPayload,
): string =>
  JSON.stringify({
    nodes: payload.nodes.map((node) => node.id).sort(),
    edges: payload.edges
      .map((edge) => `${edge.source}\u0000${edge.target}`)
      .sort(),
  });

export const applyPreservedNodePosition = (
  node: TopologyMapNode,
  position: { x: number; y: number },
): PositionedTopologyMapNode => ({
  ...node,
  x: position.x,
  y: position.y,
});
