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

export const TOPOLOGY_NODE_CARD = {
  minWidth: 148,
  widthSpan: 28,
  height: 44,
  radius: 6,
  nameOffsetX: 30,
  healthGutter: 22,
  inferredBadgeWidth: 28,
} as const;

const LATIN_CHAR_WIDTH_RATIO = 0.62;
const ELLIPSIS = '…';

const topologyCharWidth = (character: string, fontSize: number) => {
  if (character === ELLIPSIS || character === '.') return fontSize * 0.45;
  if (/[\u1100-\u115F\u3000-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]/.test(character)) return fontSize;
  return fontSize * LATIN_CHAR_WIDTH_RATIO;
};

export const topologyNodeNameWidth = (cardWidth: number, inferred: boolean) => {
  const reserved = TOPOLOGY_NODE_CARD.nameOffsetX
    + TOPOLOGY_NODE_CARD.healthGutter
    + (inferred ? TOPOLOGY_NODE_CARD.inferredBadgeWidth : 0);
  return Math.max(24, cardWidth - reserved);
};

export const truncateTopologyNodeLabel = (label: string, maxWidth: number, fontSize = 12) => {
  const characters = [...label];
  const fullWidth = characters.reduce((sum, character) => sum + topologyCharWidth(character, fontSize), 0);
  if (fullWidth <= maxWidth) return label;
  const ellipsisWidth = topologyCharWidth(ELLIPSIS, fontSize);
  let used = 0;
  const kept: string[] = [];
  for (const character of characters) {
    const next = used + topologyCharWidth(character, fontSize);
    if (next + ellipsisWidth > maxWidth) break;
    used = next;
    kept.push(character);
  }
  return `${kept.join('')}${ELLIPSIS}`;
};

const CANVAS_PADDING = {
  top: 52,
  right: 96,
  bottom: 52,
  left: 96,
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
    nodesep: 56,
    edgesep: 28,
    ranksep: 96,
    nodeSize: [TOPOLOGY_NODE_CARD.minWidth, TOPOLOGY_NODE_CARD.height],
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
    const ySign = Math.sign(target.y - source.y || 1);
    const startX = source.x;
    const startY = source.y + ySign * (source.radius + 4);
    const endX = target.x;
    const endY = target.y - ySign * (target.radius + 9);
    const midY = (startY + endY) / 2 + (reciprocal ? 18 : 0);
    const spanX = Math.abs(endX - startX);
    const corner = Math.min(10, spanX / 2, Math.abs(endY - startY) / 4);
    const path = spanX < 1
      ? `M ${roundCoordinate(startX)} ${roundCoordinate(startY)} L ${roundCoordinate(endX)} ${roundCoordinate(endY)}`
      : `M ${roundCoordinate(startX)} ${roundCoordinate(startY)} L ${roundCoordinate(startX)} ${roundCoordinate(midY - ySign * corner)} Q ${roundCoordinate(startX)} ${roundCoordinate(midY)} ${roundCoordinate(startX + Math.sign(endX - startX) * corner)} ${roundCoordinate(midY)} L ${roundCoordinate(endX - Math.sign(endX - startX) * corner)} ${roundCoordinate(midY)} Q ${roundCoordinate(endX)} ${roundCoordinate(midY)} ${roundCoordinate(endX)} ${roundCoordinate(midY + ySign * corner)} L ${roundCoordinate(endX)} ${roundCoordinate(endY)}`;
    return {
      path,
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
    linkDistance: 196,
    nodeStrength: 900,
    preventOverlap: true,
    nodeSize: TOPOLOGY_NODE_CARD.minWidth,
    nodeSpacing: 36,
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

export const isInferredTopologyNode = (node: ApmTopologyNode | undefined): boolean => node?.kind === 'inferred';

export const focusApplicationTopology = (
  graph: ApmTopologyGraph,
  applicationId: string,
): { graph: ApmTopologyGraph; focusNodeIds: Set<string> } => {
  const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]));
  const focusNodeIds = new Set(
    graph.nodes
      .filter((node) => node.service_namespace === applicationId && !isInferredTopologyNode(node))
      .map((node) => node.id),
  );
  const visibleIds = new Set(focusNodeIds);
  graph.edges.forEach((edge) => {
    const source = nodeMap.get(edge.source);
    const target = nodeMap.get(edge.target);
    if (focusNodeIds.has(edge.source) && !isInferredTopologyNode(target)) visibleIds.add(edge.target);
    if (focusNodeIds.has(edge.target) && !isInferredTopologyNode(source)) visibleIds.add(edge.source);
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

export const isolateTopologyNeighborhood = (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
  nodeId: string,
): { nodes: ApmTopologyNode[]; edges: ApmTopologyEdge[] } => {
  const visibleIds = new Set([nodeId]);
  const visibleEdges = edges.filter((edge) => {
    if (edge.source === nodeId) {
      visibleIds.add(edge.target);
      return true;
    }
    if (edge.target === nodeId) {
      visibleIds.add(edge.source);
      return true;
    }
    return false;
  });
  return {
    nodes: nodes.filter((node) => visibleIds.has(node.id)),
    edges: visibleEdges,
  };
};

export const filterTopologyByKeyword = (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
  keyword: string,
): { nodes: ApmTopologyNode[]; edges: ApmTopologyEdge[] } => {
  const needle = keyword.trim().toLowerCase();
  if (!needle) return { nodes, edges };
  const visibleIds = new Set(
    nodes
      .filter((node) => `${node.service_namespace} ${node.service_name}`.toLowerCase().includes(needle))
      .map((node) => node.id),
  );
  return {
    nodes: nodes.filter((node) => visibleIds.has(node.id)),
    edges: edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
  };
};

export const topologyNeighborIds = (edges: ApmTopologyEdge[], nodeId: string): Set<string> => {
  const ids = new Set<string>([nodeId]);
  edges.forEach((edge) => {
    if (edge.source === nodeId) ids.add(edge.target);
    if (edge.target === nodeId) ids.add(edge.source);
  });
  return ids;
};
