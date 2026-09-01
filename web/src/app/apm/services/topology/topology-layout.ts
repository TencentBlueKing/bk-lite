import { DagreLayout } from '@antv/layout';
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
  minWidth: 176,
  widthSpan: 28,
  height: 48,
  radius: 6,
  iconSize: 20,
  iconPaddingX: 10,
  nameOffsetX: 40,
  healthGutter: 22,
  inferredBadgeWidth: 28,
} as const;

export const TOPOLOGY_NODE_MIN_GAP = 24;

export const TOPOLOGY_ENTRY_PILL = {
  minWidth: 128,
  maxWidth: 176,
  height: 32,
  radius: 16,
  paddingX: 12,
  iconSize: 14,
  iconGap: 8,
  countGap: 8,
  nameFontSize: 12,
  countFontSize: 11,
} as const;

const LATIN_CHAR_WIDTH_RATIO = 0.62;
const ELLIPSIS = '…';

const topologyCharWidth = (character: string, fontSize: number) => {
  if (character === ELLIPSIS || character === '.') return fontSize * 0.45;
  if (/[\u1100-\u115F\u3000-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]/.test(character)) return fontSize;
  return fontSize * LATIN_CHAR_WIDTH_RATIO;
};

const topologyTextWidth = (text: string, fontSize: number) => (
  [...text].reduce((sum, character) => sum + topologyCharWidth(character, fontSize), 0)
);

export const topologyEntryPillWidth = (label: string, countLabel: string) => {
  const content = TOPOLOGY_ENTRY_PILL.iconSize
    + TOPOLOGY_ENTRY_PILL.iconGap
    + topologyTextWidth(label, TOPOLOGY_ENTRY_PILL.nameFontSize)
    + TOPOLOGY_ENTRY_PILL.countGap
    + topologyTextWidth(countLabel, TOPOLOGY_ENTRY_PILL.countFontSize);
  return Math.round(Math.min(
    TOPOLOGY_ENTRY_PILL.maxWidth,
    Math.max(TOPOLOGY_ENTRY_PILL.minWidth, TOPOLOGY_ENTRY_PILL.paddingX * 2 + content),
  ));
};

export const topologyEntryNameWidth = (pillWidth: number, countLabel: string) => {
  const reserved = TOPOLOGY_ENTRY_PILL.paddingX
    + TOPOLOGY_ENTRY_PILL.iconSize
    + TOPOLOGY_ENTRY_PILL.iconGap
    + TOPOLOGY_ENTRY_PILL.countGap
    + topologyTextWidth(countLabel, TOPOLOGY_ENTRY_PILL.countFontSize)
    + TOPOLOGY_ENTRY_PILL.paddingX;
  return Math.max(24, pillWidth - reserved);
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
  const fitted = Math.min(usableWidth / spanX, usableHeight / spanY, 1.25);
  const scale = Math.max(fitted, 1);
  const offsetX = CANVAS_PADDING.left + Math.max(0, (usableWidth - spanX * scale) / 2);
  const offsetY = CANVAS_PADDING.top + Math.max(0, (usableHeight - spanY * scale) / 2);

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
    nodesep: TOPOLOGY_NODE_MIN_GAP + TOPOLOGY_NODE_CARD.widthSpan,
    edgesep: 28,
    ranksep: 104,
    nodeSize: [TOPOLOGY_NODE_CARD.minWidth + TOPOLOGY_NODE_CARD.widthSpan, TOPOLOGY_NODE_CARD.height],
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

export const isInferredTopologyNode = (node: ApmTopologyNode | undefined): boolean => node?.kind === 'inferred';

export const isUserRequestTopologyNode = (node: ApmTopologyNode | undefined): boolean => node?.kind === 'user_request';

const FORCE_LAYOUT = {
  iterations: 64,
  damping: 0.78,
  maxStep: 18,
  repulsion: 2400,
  yRepulsionScale: 0.28,
  edgeSpring: 0.05,
  seedSpringX: 0.055,
  seedSpringY: 0.32,
  kindSpringY: 0.48,
  minDistance: TOPOLOGY_NODE_CARD.minWidth + TOPOLOGY_NODE_CARD.widthSpan + TOPOLOGY_NODE_MIN_GAP,
} as const;

const compareTopologyId = (left: string, right: string) => (left < right ? -1 : left > right ? 1 : 0);

const stabilizeTopologyGraph = (nodes: ApmTopologyNode[], edges: ApmTopologyEdge[]) => ({
  nodes: [...nodes].sort((left, right) => compareTopologyId(left.id, right.id)),
  edges: [...edges].sort((left, right) => compareTopologyId(left.source, right.source) || compareTopologyId(left.target, right.target)),
});

const forceSeparation = (left: number, right: number, dx: number, dy: number) => {
  const dist = Math.hypot(dx, dy);
  if (dist > 0) return { x: dx / dist, y: dy / dist, dist };
  return { x: left < right ? -1 : 1, y: 0, dist: 0 };
};

const runSeededForce = (
  seeded: PositionedApmTopologyNode[],
  edges: ApmTopologyEdge[],
): Map<string, { x: number; y: number }> => {
  const indexById = new Map(seeded.map((node, index) => [node.id, index]));
  const px = seeded.map((node) => node.x);
  const py = seeded.map((node) => node.y);
  const vx = seeded.map(() => 0);
  const vy = seeded.map(() => 0);
  const seedX = seeded.map((node) => node.x);
  const seedY = seeded.map((node) => node.y);
  const minSeedY = Math.min(...seedY);
  const maxSeedY = Math.max(...seedY);
  const targetY = seeded.map((node) => {
    if (isUserRequestTopologyNode(node)) return Math.min(node.y, minSeedY);
    if (isInferredTopologyNode(node)) return Math.max(node.y, maxSeedY);
    return node.y;
  });
  const links = edges.flatMap((edge) => {
    const source = indexById.get(edge.source);
    const target = indexById.get(edge.target);
    if (source == null || target == null || source === target) return [];
    return [{ source, target }];
  });

  for (let iteration = 0; iteration < FORCE_LAYOUT.iterations; iteration += 1) {
    const fx = seeded.map(() => 0);
    const fy = seeded.map(() => 0);

    for (let i = 0; i < seeded.length; i += 1) {
      for (let j = i + 1; j < seeded.length; j += 1) {
        const { x, y, dist } = forceSeparation(i, j, px[j] - px[i], py[j] - py[i]);
        const overlap = Math.max(FORCE_LAYOUT.minDistance - dist, 0);
        const force = FORCE_LAYOUT.repulsion / ((dist * dist) + 24) + overlap * 0.35;
        fx[i] -= x * force;
        fy[i] -= y * force * FORCE_LAYOUT.yRepulsionScale;
        fx[j] += x * force;
        fy[j] += y * force * FORCE_LAYOUT.yRepulsionScale;
      }
    }

    links.forEach((link) => {
      const { x, y, dist } = forceSeparation(link.source, link.target, px[link.target] - px[link.source], py[link.target] - py[link.source]);
      const rest = Math.hypot(FORCE_LAYOUT.minDistance, 88);
      const pull = (dist - rest) * FORCE_LAYOUT.edgeSpring;
      fx[link.source] += x * pull;
      fy[link.source] += y * pull * FORCE_LAYOUT.yRepulsionScale;
      fx[link.target] -= x * pull;
      fy[link.target] -= y * pull * FORCE_LAYOUT.yRepulsionScale;
    });

    seeded.forEach((node, index) => {
      const ySpring = isUserRequestTopologyNode(node) || isInferredTopologyNode(node)
        ? FORCE_LAYOUT.kindSpringY
        : FORCE_LAYOUT.seedSpringY;
      fx[index] += (seedX[index] - px[index]) * FORCE_LAYOUT.seedSpringX;
      fy[index] += (targetY[index] - py[index]) * ySpring;
    });

    seeded.forEach((_, index) => {
      vx[index] = (vx[index] + fx[index]) * FORCE_LAYOUT.damping;
      vy[index] = (vy[index] + fy[index]) * FORCE_LAYOUT.damping;
      const speed = Math.hypot(vx[index], vy[index]) || 1;
      if (speed > FORCE_LAYOUT.maxStep) {
        vx[index] = (vx[index] / speed) * FORCE_LAYOUT.maxStep;
        vy[index] = (vy[index] / speed) * FORCE_LAYOUT.maxStep;
      }
      px[index] += vx[index];
      py[index] += vy[index];
      py[index] = Math.min(maxSeedY, Math.max(minSeedY, py[index]));
    });
  }

  return new Map(seeded.map((node, index) => [node.id, { x: px[index], y: py[index] }]));
};

export const layoutForceTopology = async (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
): Promise<PositionedApmTopologyNode[]> => {
  if (nodes.length === 0) return [];
  const stable = stabilizeTopologyGraph(nodes, edges);
  const seeded = await layoutLayeredTopology(stable.nodes, stable.edges);
  const positioned = seeded.length <= 1
    ? new Map(seeded.map((item) => [item.id, { x: item.x, y: item.y }]))
    : runSeededForce(seeded, stable.edges);
  return nodes.map((item) => {
    const raw = positioned.get(item.id) ?? { x: CANVAS_PADDING.left, y: CANVAS_PADDING.top };
    return { ...item, x: roundCoordinate(raw.x), y: roundCoordinate(raw.y) };
  });
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
    if (focusNodeIds.has(edge.source)) visibleIds.add(edge.target);
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

export const filterAnomalousTopology = (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
): { nodes: ApmTopologyNode[]; edges: ApmTopologyEdge[] } => {
  const anomalyEdges = edges.filter((edge) => edge.error_calls > 0);
  const visibleIds = new Set(anomalyEdges.flatMap((edge) => [edge.source, edge.target]));
  return {
    nodes: nodes.filter((node) => visibleIds.has(node.id)),
    edges: anomalyEdges,
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

export const topologyCardsOverlap = (
  nodes: { x: number; y: number }[],
  width = TOPOLOGY_NODE_CARD.minWidth,
  height = TOPOLOGY_NODE_CARD.height,
  gap = TOPOLOGY_NODE_MIN_GAP,
) => {
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      if (
        Math.abs(nodes[i].x - nodes[j].x) < width + gap
        && Math.abs(nodes[i].y - nodes[j].y) < height + gap
      ) {
        return true;
      }
    }
  }
  return false;
};

export const fitTopologyView = (
  nodes: PositionedApmTopologyNode[],
  zoom = 1,
): { x: number; y: number; k: number } => {
  if (!nodes.length) return { x: 0, y: 0, k: zoom };
  const halfW = (TOPOLOGY_NODE_CARD.minWidth + TOPOLOGY_NODE_CARD.widthSpan) / 2;
  const halfH = TOPOLOGY_NODE_CARD.height / 2;
  const minX = Math.min(...nodes.map((node) => node.x - halfW));
  const maxX = Math.max(...nodes.map((node) => node.x + halfW));
  const minY = Math.min(...nodes.map((node) => node.y - halfH));
  const maxY = Math.max(...nodes.map((node) => node.y + halfH));
  const width = Math.max(maxX - minX, 1);
  const height = Math.max(maxY - minY, 1);
  const k = Math.min(zoom, TOPOLOGY_CANVAS_SIZE.width / width, TOPOLOGY_CANVAS_SIZE.height / height);
  return {
    k,
    x: (TOPOLOGY_CANVAS_SIZE.width - width * k) / 2 - minX * k,
    y: (TOPOLOGY_CANVAS_SIZE.height - height * k) / 2 - minY * k,
  };
};
