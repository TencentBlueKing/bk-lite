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

export type TopologyEdgeRouting = 'polyline' | 'curve' | 'arc';

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
  minWidth: 180,
  widthSpan: 24,
  height: 48,
  radius: 10,
  iconSize: 16,
  iconPaddingX: 12,
  nameOffsetX: 40,
  healthGutter: 22,
  inferredBadgeWidth: 28,
} as const;

export const TOPOLOGY_NODE_MIN_GAP = 24;

export const TOPOLOGY_ENTRY_PILL = {
  minWidth: 140,
  maxWidth: 188,
  height: 32,
  radius: 16,
  paddingX: 12,
  iconSize: 16,
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

export const topologyTextWidth = (text: string, fontSize: number) => (
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
  const cardW = TOPOLOGY_NODE_CARD.minWidth + TOPOLOGY_NODE_CARD.widthSpan;
  const cardH = TOPOLOGY_NODE_CARD.height;
  const usableWidth = TOPOLOGY_CANVAS_SIZE.width - CANVAS_PADDING.left - CANVAS_PADDING.right - cardW;
  const usableHeight = TOPOLOGY_CANVAS_SIZE.height - CANVAS_PADDING.top - CANVAS_PADDING.bottom - cardH;
  const fitted = Math.min(usableWidth / spanX, usableHeight / spanY, 1.25);
  const scale = Math.max(fitted, 1);
  const offsetX = CANVAS_PADDING.left + cardW / 2 + Math.max(0, (usableWidth - spanX * scale) / 2);
  const offsetY = CANVAS_PADDING.top + cardH / 2 + Math.max(0, (usableHeight - spanY * scale) / 2);

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

  const cardW = TOPOLOGY_NODE_CARD.minWidth + TOPOLOGY_NODE_CARD.widthSpan;
  const cardH = TOPOLOGY_NODE_CARD.height;

  const layout = new DagreLayout({
    rankdir: 'LR',
    align: 'UL',
    nodesep: TOPOLOGY_NODE_MIN_GAP,
    edgesep: 16,
    ranksep: 32,
    nodeSize: [cardW, cardH],
    edgeLabelSize: [40, 18],
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

const compareTopologyId = (left: string, right: string) => (left < right ? -1 : left > right ? 1 : 0);

const stabilizeTopologyGraph = (nodes: ApmTopologyNode[], edges: ApmTopologyEdge[]) => ({
  nodes: [...nodes].sort((left, right) => compareTopologyId(left.id, right.id)),
  edges: [...edges].sort((left, right) => compareTopologyId(left.source, right.source) || compareTopologyId(left.target, right.target)),
});

export const layoutForceTopology = async (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
): Promise<PositionedApmTopologyNode[]> => {
  if (nodes.length === 0) return [];
  const stable = stabilizeTopologyGraph(nodes, edges);
  const seeded = await layoutLayeredTopology(stable.nodes, stable.edges);
  if (seeded.length <= 1) return seeded;

  const seedMap = new Map(seeded.map((item) => [item.id, { x: item.x, y: item.y }]));

  const degreeMap = new Map<string, number>();
  stable.edges.forEach((edge) => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
  });
  const maxCalls = Math.max(...stable.edges.map((edge) => edge.sampled_calls), 1);

  const force = new ForceLayout({
    width: TOPOLOGY_CANVAS_SIZE.width,
    height: TOPOLOGY_CANVAS_SIZE.height,
    maxIteration: 300,
    gravity: 3,
    damping: 0.9,
    factor: 1,
    coulombDisScale: 0.005,
    preventOverlap: true,
    nodeSize: 250,
    collideStrength: 1,
    clustering: true,
    nodeClusterBy: (n) => {
      const raw = (n as { _original?: { data?: { service_namespace?: string }; id?: string }; id?: string; data?: { service_namespace?: string } })._original || n;
      const ns = raw.data?.service_namespace;
      return ns && ns.length > 0 ? ns : raw.id || 'default';
    },
    clusterNodeStrength: 48,
    getCenter: (n) => {
      const raw = (n as { _original?: { data?: { kind?: string } }; data?: { kind?: string } })._original || n;
      const kind = raw.data?.kind;
      if (kind === 'user_request') {
        return [TOPOLOGY_CANVAS_SIZE.width * 0.12, TOPOLOGY_CANVAS_SIZE.height * 0.5, 12];
      }
      if (kind === 'inferred') {
        return [TOPOLOGY_CANVAS_SIZE.width * 0.88, TOPOLOGY_CANVAS_SIZE.height * 0.5, 12];
      }
      return undefined;
    },
    getMass: (n) => {
      const raw = (n as { _original?: { data?: { kind?: string }; id?: string }; id?: string; data?: { kind?: string } })._original || n;
      const kind = raw.data?.kind;
      if (kind === 'user_request' || kind === 'inferred') return 12;
      const deg = degreeMap.get(raw.id || '') || 1;
      return 1 + 0.5 * deg;
    },
    nodeStrength: (n) => {
      const raw = (n as { _original?: { id?: string }; id?: string })._original || n;
      const deg = degreeMap.get(raw.id || '') || 1;
      return -(600 + 100 * deg);
    },
    linkDistance: (e) => {
      const calls = (e as { sampled_calls?: number } | undefined)?.sampled_calls || 50;
      return 210 + 50 * (1 - calls / maxCalls);
    },
    edgeStrength: (e) => {
      const calls = (e as { sampled_calls?: number } | undefined)?.sampled_calls || 50;
      return 40 + 30 * (calls / maxCalls);
    },
  });

  await force.execute({
    nodes: stable.nodes.map((item, index) => {
      const s = seedMap.get(item.id) || { x: 500, y: 320 };
      return {
        id: item.id,
        size: 240,
        x: s.x * 0.45 + TOPOLOGY_CANVAS_SIZE.width * 0.25,
        y: s.y + (index % 2 === 0 ? -18 : 18),
        data: {
          service_namespace: item.service_namespace || '',
          kind: item.kind,
        },
      };
    }),
    edges: stable.edges.map((item, index) => ({
      id: `apm-force-edge-${index}`,
      source: item.source,
      target: item.target,
      sampled_calls: item.sampled_calls,
    })),
  });

  const rawPositions = new Map<string, { x: number; y: number }>();
  force.forEachNode((item) => {
    rawPositions.set(String(item.id), { x: item.x, y: item.y });
  });

  return mapLayoutPositions(nodes, rawPositions);
};

export const buildTopologyEdgeGeometry = (
  source: EdgeEndpoint,
  target: EdgeEndpoint,
  reciprocal: boolean,
  routing: TopologyEdgeRouting = 'curve',
): TopologyEdgeGeometry => {
  if (routing === 'arc') {
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const dist = Math.hypot(dx, dy) || 1;
    const ux = dx / dist;
    const uy = dy / dist;
    const nx = -uy;
    const ny = ux;

    const absUx = Math.abs(ux) || 0.0001;
    const absUy = Math.abs(uy) || 0.0001;
    const halfH = TOPOLOGY_NODE_CARD.height / 2;
    const sOffset = Math.min(source.radius / absUx, halfH / absUy);
    const tOffset = Math.min(target.radius / absUx, halfH / absUy);

    const startX = source.x + ux * (sOffset + 2);
    const startY = source.y + uy * (sOffset + 2);
    const endX = target.x - ux * (tOffset + 8);
    const endY = target.y - uy * (tOffset + 8);

    const mx = (startX + endX) / 2;
    const my = (startY + endY) / 2;
    const isForward = target.x >= source.x;
    const curveOffset = reciprocal ? (isForward ? 18 : -18) : Math.min(22, Math.max(-22, dist * 0.08));

    const cx = mx + nx * curveOffset;
    const cy = my + ny * curveOffset;

    const labelX = roundCoordinate((startX + 2 * cx + endX) / 4);
    const labelY = roundCoordinate((startY + 2 * cy + endY) / 4);
    const path = `M ${roundCoordinate(startX)} ${roundCoordinate(startY)} Q ${roundCoordinate(cx)} ${roundCoordinate(cy)} ${roundCoordinate(endX)} ${roundCoordinate(endY)}`;

    return {
      path,
      startX: roundCoordinate(startX),
      startY: roundCoordinate(startY),
      endX: roundCoordinate(endX),
      endY: roundCoordinate(endY),
      controlX: roundCoordinate(cx),
      controlY: roundCoordinate(cy),
      labelX,
      labelY,
    };
  }

  if (routing === 'polyline') {
    const ySign = Math.sign(target.y - source.y || 1);
    const startX = source.x;
    const startY = source.y + ySign * (source.radius + 4);
    const endX = target.x;
    const endY = target.y - ySign * (target.radius + 9);
    const midY = (startY + endY) / 2 + (reciprocal ? 18 : 0);
    const spanX = Math.abs(endX - startX);
    const deltaY = Math.abs(endY - startY);
    const corner = Math.min(48, spanX / 2, deltaY / 2.2);
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

  // Horizontal S-curve routing (Left-to-Right)
  const isForward = target.x >= source.x;
  const yOffset = reciprocal ? (isForward ? -10 : 10) : 0;
  const startX = isForward ? (source.x + source.radius) : (source.x - source.radius);
  const startY = source.y + yOffset;
  const endX = isForward ? (target.x - target.radius) : (target.x + target.radius);
  const endY = target.y + yOffset;
  const dx = endX - startX;
  const dy = endY - startY;

  let cx1: number, cy1: number, cx2: number, cy2: number;
  if (isForward) {
    const extend = Math.max(36, dx * 0.46);
    cx1 = startX + extend;
    cy1 = startY;
    cx2 = endX - extend;
    cy2 = endY;
  } else {
    const extend = Math.max(36, Math.abs(dx) * 0.3);
    const loopY = Math.sign(dy || 1) * 48;
    cx1 = startX - extend;
    cy1 = startY + loopY;
    cx2 = endX + extend;
    cy2 = endY + loopY;
  }

  const labelX = roundCoordinate((startX + 3 * cx1 + 3 * cx2 + endX) / 8);
  const labelY = roundCoordinate((startY + 3 * cy1 + 3 * cy2 + endY) / 8);
  const path = `M ${roundCoordinate(startX)} ${roundCoordinate(startY)} C ${roundCoordinate(cx1)} ${roundCoordinate(cy1)}, ${roundCoordinate(cx2)} ${roundCoordinate(cy2)}, ${roundCoordinate(endX)} ${roundCoordinate(endY)}`;

  return {
    path,
    startX,
    startY,
    endX,
    endY,
    controlX: roundCoordinate((cx1 + cx2) / 2),
    controlY: roundCoordinate((cy1 + cy2) / 2),
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
  canvasSize: { width: number; height: number } = TOPOLOGY_CANVAS_SIZE,
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
  const padding = 20;
  const usableW = Math.max(canvasSize.width - padding * 2, 1);
  const usableH = Math.max(canvasSize.height - padding * 2, 1);
  const k = Math.min(zoom, usableW / width, usableH / height);
  return {
    k,
    x: (canvasSize.width - width * k) / 2 - minX * k,
    y: (canvasSize.height - height * k) / 2 - minY * k,
  };
};
