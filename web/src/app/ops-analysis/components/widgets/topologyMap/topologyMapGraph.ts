import type { Graph as X6Graph } from '@antv/x6';
import type {
  PositionedTopologyMapNode,
  TopologyMapEdge,
} from '@/app/ops-analysis/utils/topologyMapData';
import { TOPOLOGY_MAP_NODE_SIZE } from '@/app/ops-analysis/utils/topologyMapData';

const TOPOLOGY_MAP_NODE_SHAPE = 'ops-analysis-topology-map-node-v1';

const COLORS = {
  critical: 'var(--color-fail)',
  error: 'var(--color-fail)',
  warning: 'var(--theme-color-status-warning)',
  unknown: 'var(--color-text-3)',
  normal: 'var(--color-primary)',
} as const;

export type TopologyMapAlertStatus =
  | 'critical'
  | 'error'
  | 'warning'
  | 'unknown'
  | 'normal';

export const getTopologyMapAlertStatus = (
  level: string | undefined,
  alertCount: number,
): TopologyMapAlertStatus => {
  if (alertCount === 0) return 'normal';
  if (level === '0') return 'critical';
  if (level === '1') return 'error';
  if (level === '2') return 'warning';
  return 'unknown';
};

const truncate = (value: string, maxLength: number) =>
  value.length <= maxLength ? value : `${value.slice(0, maxLength - 1)}…`;

export const getTopologyMapAlertVisual = (
  level: string | undefined,
  alertCount: number,
) => {
  const status = getTopologyMapAlertStatus(level, alertCount);
  if (status === 'normal') {
    return {
      color: COLORS.normal,
      strokeWidth: 1.5,
      strokeOpacity: 0.32,
      criticalRingOpacity: 0,
      pulse: false,
    };
  }
  if (status === 'critical') {
    return {
      color: COLORS.critical,
      strokeWidth: 3,
      strokeOpacity: 1,
      criticalRingOpacity: 1,
      pulse: true,
    };
  }
  if (status === 'error') {
    return {
      color: COLORS.error,
      strokeWidth: 1.5,
      strokeOpacity: 1,
      criticalRingOpacity: 0,
      pulse: false,
    };
  }
  if (status === 'warning') {
    return {
      color: COLORS.warning,
      strokeWidth: 1.5,
      strokeOpacity: 1,
      criticalRingOpacity: 0,
      pulse: false,
    };
  }
  return {
    color: COLORS.unknown,
    strokeWidth: 1.5,
    strokeOpacity: 0.72,
    criticalRingOpacity: 0,
    pulse: false,
  };
};

type GraphConstructor = typeof X6Graph;

export const ensureTopologyMapNodeRegistered = (Graph: GraphConstructor) => {
  Graph.registerNode(
    TOPOLOGY_MAP_NODE_SHAPE,
    {
      inherit: 'rect',
      width: TOPOLOGY_MAP_NODE_SIZE.width,
      height: TOPOLOGY_MAP_NODE_SIZE.height,
      markup: [
        { tagName: 'rect', selector: 'pulse' },
        { tagName: 'rect', selector: 'criticalRing' },
        { tagName: 'rect', selector: 'body' },
        { tagName: 'text', selector: 'title' },
        { tagName: 'text', selector: 'model' },
        { tagName: 'text', selector: 'subtitle' },
        { tagName: 'rect', selector: 'badge' },
        { tagName: 'text', selector: 'badgeText' },
        { tagName: 'title', selector: 'accessibleTitle' },
      ],
      attrs: {
        pulse: {
          x: -3,
          y: -3,
          width: TOPOLOGY_MAP_NODE_SIZE.width + 6,
          height: TOPOLOGY_MAP_NODE_SIZE.height + 6,
          rx: 10,
          ry: 10,
          fill: 'none',
          strokeWidth: 2,
          opacity: 0,
          pointerEvents: 'none',
        },
        criticalRing: {
          x: 0,
          y: 0,
          width: 4,
          height: TOPOLOGY_MAP_NODE_SIZE.height,
          rx: 4,
          ry: 4,
          fill: 'var(--color-fail)',
          stroke: 'none',
          opacity: 0,
          pointerEvents: 'none',
        },
        body: {
          width: TOPOLOGY_MAP_NODE_SIZE.width,
          height: TOPOLOGY_MAP_NODE_SIZE.height,
          rx: 8,
          ry: 8,
          fill: 'var(--color-bg-1)',
          stroke: 'var(--color-border-2)',
        },
        title: {
          refX: 16,
          refY: 27,
          fontSize: 14,
          fontWeight: 600,
          fill: 'var(--color-text-1)',
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          pointerEvents: 'none',
        },
        model: {
          refX: 16,
          refY: 52,
          fontSize: 11,
          fill: 'var(--color-text-3)',
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          pointerEvents: 'none',
        },
        subtitle: {
          refX: 16,
          refY: 62,
          fontSize: 11,
          fill: 'var(--color-text-3)',
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          pointerEvents: 'none',
        },
        badge: {
          x: 165,
          y: 14,
          width: 30,
          height: 20,
          rx: 10,
          ry: 10,
          opacity: 0,
          stroke: 'var(--color-bg-1)',
          strokeWidth: 1,
          pointerEvents: 'none',
        },
        badgeText: {
          refX: 180,
          refY: 24,
          fontSize: 11,
          fontWeight: 700,
          fill: 'var(--color-bg-1)',
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          opacity: 0,
          pointerEvents: 'none',
        },
      },
    },
    true,
  );
};

export const buildTopologyMapNodeCell = (node: PositionedTopologyMapNode) => {
  const visual = getTopologyMapAlertVisual(node.alert_level, node.alert_count);
  const showBadge = node.alert_count > 0;
  const hasSubtitle = Boolean(node.subtitle);
  // Keep outer node geometry fixed; only redistribute internal text baselines.
  const titleY = hasSubtitle ? 18 : 27;
  const modelY = hasSubtitle ? 40 : 52;
  const subtitleY = 62;
  return {
    id: node.id,
    shape: TOPOLOGY_MAP_NODE_SHAPE,
    x: node.x,
    y: node.y,
    width: TOPOLOGY_MAP_NODE_SIZE.width,
    height: TOPOLOGY_MAP_NODE_SIZE.height,
    attrs: {
      pulse: {
        stroke: visual.color,
        opacity: visual.pulse ? 0.45 : 0,
        class: visual.pulse ? 'topology-map-critical-pulse' : '',
      },
      criticalRing: {
        stroke: visual.color,
        opacity: visual.criticalRingOpacity,
      },
      body: {
        stroke: visual.color,
        strokeWidth: visual.strokeWidth,
        strokeOpacity: visual.strokeOpacity,
      },
      title: {
        text: truncate(node.instance_name, 22),
        refX: 16,
        refY: titleY,
      },
      model: {
        text: truncate(node.model_name, 28),
        refX: 16,
        refY: modelY,
      },
      subtitle: {
        text: hasSubtitle ? truncate(node.subtitle || '', 28) : '',
        refX: 16,
        refY: subtitleY,
        opacity: hasSubtitle ? 1 : 0,
      },
      badge: {
        fill: visual.color,
        opacity: showBadge ? 1 : 0,
      },
      badgeText: {
        text: node.alert_count > 99 ? '99+' : String(node.alert_count),
        refX: 180,
        refY: 24,
        opacity: showBadge ? 1 : 0,
      },
      accessibleTitle: {
        text: [node.instance_name, node.model_name, node.subtitle]
          .filter(Boolean)
          .join(' · '),
      },
    },
    data: node,
  };
};

const marker = { name: 'block', width: 8, height: 7 } as const;

const buildTopologyMapEdgeCell = (
  edge: TopologyMapEdge,
  index: number,
  vertices?: Array<{ x: number; y: number }>,
) => {
  const hasSourceMarker = edge.connection_type === 'double';
  const hasTargetMarker =
    edge.connection_type === 'single' || edge.connection_type === 'double';
  return {
    id: `topology-map-edge-${index}`,
    shape: 'edge',
    source: { cell: edge.source },
    target: { cell: edge.target },
    ...(vertices ? { vertices } : {}),
    zIndex: 0,
    connector: { name: 'rounded' },
    attrs: {
      line: {
        stroke: 'var(--color-primary)',
        strokeOpacity: 0.58,
        strokeWidth: 1.5,
        strokeDasharray: edge.line_style === 'dashed' ? '6 4' : undefined,
        sourceMarker: hasSourceMarker ? marker : undefined,
        targetMarker: hasTargetMarker ? marker : undefined,
      },
    },
    labels: edge.label
      ? [
        {
          attrs: {
            label: {
              text: edge.label,
              fill: 'var(--color-text-2)',
              fontSize: 12,
            },
            body: {
              fill: 'var(--color-bg-1)',
              stroke: 'var(--color-border-2)',
              strokeWidth: 1,
              rx: 4,
              ry: 4,
            },
          },
        },
      ]
      : [],
    data: edge,
  };
};

export const buildTopologyMapEdgeCells = (
  edges: TopologyMapEdge[],
  nodes: PositionedTopologyMapNode[],
) => {
  const positions = new Map(nodes.map((node) => [node.id, node]));
  const directedPairs = new Set(
    edges.map((edge) => JSON.stringify([edge.source, edge.target])),
  );
  return edges.map((edge, index) => {
    const hasReverse = directedPairs.has(
      JSON.stringify([edge.target, edge.source]),
    );
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    // Reverse-pair separation only: keep A→B and B→A from fully overlapping.
    // This is not same-direction parallel-edge / multigraph routing support.
    if (!hasReverse || !source || !target || edge.source === edge.target) {
      return buildTopologyMapEdgeCell(edge, index);
    }
    const sourceCenter = {
      x: source.x + TOPOLOGY_MAP_NODE_SIZE.width / 2,
      y: source.y + TOPOLOGY_MAP_NODE_SIZE.height / 2,
    };
    const targetCenter = {
      x: target.x + TOPOLOGY_MAP_NODE_SIZE.width / 2,
      y: target.y + TOPOLOGY_MAP_NODE_SIZE.height / 2,
    };
    const dx = targetCenter.x - sourceCenter.x;
    const dy = targetCenter.y - sourceCenter.y;
    const length = Math.hypot(dx, dy) || 1;
    const offset = 18;
    const vertices = [{
      x: (sourceCenter.x + targetCenter.x) / 2 - (dy / length) * offset,
      y: (sourceCenter.y + targetCenter.y) / 2 + (dx / length) * offset,
    }];
    return buildTopologyMapEdgeCell(edge, index, vertices);
  });
};
