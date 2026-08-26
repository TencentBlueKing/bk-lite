import { DagreLayout, ForceLayout } from '@antv/layout';
import type { ApmTopologyEdge, ApmTopologyGraph, ApmTopologyNode } from '@/app/apm/types';

export interface PositionedApmTopologyNode extends ApmTopologyNode {
  x: number;
  y: number;
}

interface EdgeEndpoint {
  x: number;
  y: number;
  radius: number;
}

export type TopologyEdgeRouting = 'polyline' | 'curve';

export interface TopologyEdgeGeometry {
  path: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  controlX: number;
  controlY: number;
  labelX: number;
  labelY: number;
}

export const TOPOLOGY_CANVAS_SIZE = {
  width: 1030,
  height: 640,
} as const;

const CANVAS_PADDING = {
  top: 56,
  right: 168,
  bottom: 56,
  left: 64,
} as const;

const roundCoordinate = (value: number) => Math.round(value * 100) / 100;

const mapLayoutPositions = (
  nodes: ApmTopologyNode[],
  rawPositions: Map<string, { x: number; y: number }>,
): PositionedApmTopologyNode[] => {
  const rawValues = nodes.map((item) => rawPositions.get(item.id) ?? { x: 0, y: 0 });
  const xValues = rawValues.map((item) => item.x);
  const yValues = rawValues.map((item) => item.y);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const usableWidth = TOPOLOGY_CANVAS_SIZE.width - CANVAS_PADDING.left - CANVAS_PADDING.right;
  const usableHeight = TOPOLOGY_CANVAS_SIZE.height - CANVAS_PADDING.top - CANVAS_PADDING.bottom;
  const scale = Math.min(usableWidth / spanX, usableHeight / spanY, 1.25);
  const offsetX = CANVAS_PADDING.left + (usableWidth - spanX * scale) / 2;
  const offsetY = CANVAS_PADDING.top + (usableHeight - spanY * scale) / 2;

  return nodes.map((item) => {
    const raw = rawPositions.get(item.id) ?? { x: 0, y: 0 };
    return {
      ...item,
      x: roundCoordinate(offsetX + (raw.x - minX) * scale),
      y: roundCoordinate(offsetY + (raw.y - minY) * scale),
    };
  });
};

export const layoutLayeredTopology = async (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
): Promise<PositionedApmTopologyNode[]> => {
  if (nodes.length === 0) return [];

  const layout = new DagreLayout({
    rankdir: 'TB',
    align: 'UL',
    nodesep: 128,
    edgesep: 28,
    ranksep: 118,
    nodeSize: [36, 36],
    edgeLabelSize: [96, 18],
    edgeLabelOffset: 10,
    controlPoints: true,
  });

  await layout.execute({
    nodes: nodes.map((item) => ({ id: item.id })),
    edges: edges.map((item, index) => ({
      id: `apm-topology-edge-${index}`,
      source: item.source,
      target: item.target,
    })),
  });

  const rawPositions = new Map<string, { x: number; y: number }>();
  layout.forEachNode((item) => {
    rawPositions.set(String(item.id), { x: item.x, y: item.y });
  });
  return mapLayoutPositions(nodes, rawPositions);
};

const unitVector = (fromX: number, fromY: number, toX: number, toY: number) => {
  const dx = toX - fromX;
  const dy = toY - fromY;
  const length = Math.hypot(dx, dy) || 1;
  return { x: dx / length, y: dy / length };
};

export const buildTopologyEdgeGeometry = (
  source: EdgeEndpoint,
  target: EdgeEndpoint,
  reciprocal: boolean,
  routing: TopologyEdgeRouting = 'curve',
): TopologyEdgeGeometry => {
  if (routing === 'polyline') {
    const startX = source.x;
    const startY = source.y + Math.sign(target.y - source.y || 1) * (source.radius + 4);
    const endX = target.x;
    const endY = target.y - Math.sign(target.y - source.y || 1) * (target.radius + 9);
    const midY = (startY + endY) / 2 + (reciprocal ? 18 : 0);
    return {
      path: `M ${roundCoordinate(startX)} ${roundCoordinate(startY)} L ${roundCoordinate(startX)} ${roundCoordinate(midY)} L ${roundCoordinate(endX)} ${roundCoordinate(midY)} L ${roundCoordinate(endX)} ${roundCoordinate(endY)}`,
      startX,
      startY,
      endX,
      endY,
      controlX: (startX + endX) / 2,
      controlY: midY,
      labelX: (startX + endX) / 2,
      labelY: midY,
    };
  }

  const direct = unitVector(source.x, source.y, target.x, target.y);
  const midpointX = (source.x + target.x) / 2;
  const midpointY = (source.y + target.y) / 2;
  const curveOffset = reciprocal ? 28 : 0;
  const controlX = midpointX - direct.y * curveOffset;
  const controlY = midpointY + direct.x * curveOffset;
  const sourceDirection = unitVector(source.x, source.y, controlX, controlY);
  const targetDirection = unitVector(target.x, target.y, controlX, controlY);
  const startX = source.x + sourceDirection.x * (source.radius + 4);
  const startY = source.y + sourceDirection.y * (source.radius + 4);
  const endX = target.x + targetDirection.x * (target.radius + 9);
  const endY = target.y + targetDirection.y * (target.radius + 9);
  const labelX = (startX + 2 * controlX + endX) / 4;
  const labelY = (startY + 2 * controlY + endY) / 4;

  return {
    path: `M ${roundCoordinate(startX)} ${roundCoordinate(startY)} Q ${roundCoordinate(controlX)} ${roundCoordinate(controlY)} ${roundCoordinate(endX)} ${roundCoordinate(endY)}`,
    startX,
    startY,
    endX,
    endY,
    controlX,
    controlY,
    labelX,
    labelY,
  };
};

export const hasReciprocalTopologyEdge = (
  edge: ApmTopologyEdge,
  edgePairs: ReadonlySet<string>,
) => edgePairs.has(`${edge.target}\u0000${edge.source}`);

export const layoutForceTopology = async (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
): Promise<PositionedApmTopologyNode[]> => {
  if (nodes.length === 0) return [];

  const layout = new ForceLayout({
    dimensions: 2,
    width: TOPOLOGY_CANVAS_SIZE.width,
    height: TOPOLOGY_CANVAS_SIZE.height,
    linkDistance: 168,
    nodeStrength: 900,
    preventOverlap: true,
    nodeSize: 48,
    nodeSpacing: 72,
  });

  try {
    await layout.execute({
      nodes: nodes.map((item) => ({ id: item.id })),
      edges: edges.map((item, index) => ({
        id: `apm-topology-force-edge-${index}`,
        source: item.source,
        target: item.target,
      })),
    });

    const rawPositions = new Map<string, { x: number; y: number }>();
    layout.forEachNode((item) => {
      rawPositions.set(String(item.id), { x: item.x, y: item.y });
    });
    return mapLayoutPositions(nodes, rawPositions);
  } finally {
    layout.stop();
  }
};

export const focusApplicationTopology = (
  graph: ApmTopologyGraph,
  applicationId: string,
): { graph: ApmTopologyGraph; focusNodeIds: Set<string> } => {
  const focusNodeIds = new Set(
    graph.nodes
      .filter((node) => node.service_namespace === applicationId)
      .map((node) => node.id),
  );
  const visibleIds = new Set(focusNodeIds);
  graph.edges.forEach((edge) => {
    if (focusNodeIds.has(edge.source)) visibleIds.add(edge.target);
    if (focusNodeIds.has(edge.target)) visibleIds.add(edge.source);
  });
  return {
    focusNodeIds,
    graph: {
      ...graph,
      nodes: graph.nodes.filter((node) => visibleIds.has(node.id)),
      edges: graph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
    },
  };
};
