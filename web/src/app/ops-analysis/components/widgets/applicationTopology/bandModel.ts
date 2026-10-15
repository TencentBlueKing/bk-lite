import {
  LAYER_KEYS,
  resolveLayer,
  resolveRootNode,
  type LayerKey,
} from '@/app/cmdb/utils/applicationResourceLayer';
import { ALERT_LEVEL_COLORS } from '@/constants/observabilityChart';
import type {
  ApplicationResourceNode,
  ApplicationResourceTopologyData,
} from '@/app/cmdb/types/applicationResourceOverview';

export const APPLICATION_TOPOLOGY_NODE = {
  width: 248,
  height: 68,
} as const;

export const APPLICATION_TOPOLOGY_LAYOUT = {
  rail: 24,
  padX: 16,
  padY: 12,
  gapX: 48,
  gapY: 28,
  bandPadY: 28,
  layerGap: 28,
} as const;

export type ApplicationTopologyTone =
  | 'unknown'
  | 'normal'
  | 'warning'
  | 'error'
  | 'critical';

export interface ApplicationTopologySourceNode {
  id: string;
  name: string;
  model_id: string;
  hop?: number;
  category?: string;
  app_topo_layer?: string;
  monitor_id?: string;
  alert_count?: number | null;
  max_level?: string | null;
}

export interface ApplicationTopologySourceLink {
  id?: string;
  source: string;
  target: string;
  asst_id?: string;
}

export interface ApplicationTopologyBandNode {
  id: string;
  name: string;
  modelId: string;
  layer: LayerKey;
  tone: ApplicationTopologyTone;
  alertCount: number | null;
  maxLevel: string | null;
  monitorId: string;
  badge: string | null;
  category: string;
  x: number;
  y: number;
}

export interface ApplicationTopologyBand {
  key: LayerKey;
  top: number;
  height: number;
  empty: boolean;
}

export interface ApplicationTopologyEdge {
  id: string;
  sourceId: string;
  targetId: string;
  points: Array<{ x: number; y: number }>;
  label: string | null;
  markerStart: boolean;
  markerEnd: boolean;
}

export interface ApplicationTopologyLayout {
  width: number;
  height: number;
  bands: ApplicationTopologyBand[];
  nodes: ApplicationTopologyBandNode[];
  edges: ApplicationTopologyEdge[];
}

export type ApplicationTopologyHover =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; id: string }
  | null;

/** 悬停线点亮两端节点和这条关系；悬停节点点亮相连的线，以及线另一端的节点。 */
export function resolveApplicationTopologyHover(
  hover: ApplicationTopologyHover,
  edges: Array<Pick<ApplicationTopologyEdge, 'id' | 'sourceId' | 'targetId'>>,
): { nodeIds: ReadonlySet<string>; edgeIds: ReadonlySet<string> } {
  const nodeIds = new Set<string>();
  const edgeIds = new Set<string>();
  if (!hover) return { nodeIds, edgeIds };
  if (hover.kind === 'edge') {
    const edge = edges.find((item) => item.id === hover.id);
    if (!edge) return { nodeIds, edgeIds };
    edgeIds.add(edge.id);
    nodeIds.add(edge.sourceId);
    nodeIds.add(edge.targetId);
    return { nodeIds, edgeIds };
  }
  nodeIds.add(hover.id);
  edges.forEach((edge) => {
    if (edge.sourceId === hover.id || edge.targetId === hover.id) {
      edgeIds.add(edge.id);
      nodeIds.add(edge.sourceId);
      nodeIds.add(edge.targetId);
    }
  });
  return { nodeIds, edgeIds };
}

export function formatAlertBadge(count: number | null | undefined): string | null {
  if (count == null || count <= 0) return null;
  if (count > 99) return '99+';
  return String(count);
}

/** 与监控告警列表的 LEVEL_MAP 相同，不用告警中心按 level_id 配置的颜色。 */
export function applicationTopologyToneColor(tone: ApplicationTopologyTone): string {
  if (tone === 'critical') return ALERT_LEVEL_COLORS.critical;
  if (tone === 'error') return ALERT_LEVEL_COLORS.error;
  if (tone === 'warning') return ALERT_LEVEL_COLORS.warning;
  if (tone === 'normal') return 'var(--color-success)';
  return 'var(--color-border-2)';
}

export function resolveApplicationTopologyTone(
  alertCount: number | null | undefined,
  maxLevel: string | null | undefined,
): ApplicationTopologyTone {
  if (alertCount == null) return 'unknown';
  if (alertCount <= 0) return 'normal';
  const level = String(maxLevel || '').toLowerCase();
  if (level === 'critical') return 'critical';
  if (level === 'error') return 'error';
  return 'warning';
}

const layerIndex = (layer: LayerKey) => LAYER_KEYS.indexOf(layer);

const nodeCenter = (
  node: ApplicationTopologyBandNode,
  nodeWidth: number,
  nodeHeight: number,
) => ({
  x: node.x + nodeWidth / 2,
  y: node.y + nodeHeight / 2,
});

const crossLayerPoints = (input: {
  source: { x: number; y: number };
  target: { x: number; y: number };
  nodes: ApplicationTopologyBandNode[];
  nodeWidth: number;
  nodeHeight: number;
}) => {
  const halfWidth = input.nodeWidth / 2;
  const clearance = 12;
  const intervals = input.nodes
    .map((node) => nodeCenter(node, input.nodeWidth, input.nodeHeight))
    .filter((center) => center.y > input.source.y && center.y < input.target.y)
    .map((center) => ({
      start: center.x - halfWidth - clearance,
      end: center.x + halfWidth + clearance,
    }))
    .sort((left, right) => left.start - right.start);
  const merged = intervals.reduce<Array<{ start: number; end: number }>>((items, interval) => {
    const previous = items[items.length - 1];
    if (!previous || interval.start > previous.end) {
      items.push({ ...interval });
    } else {
      previous.end = Math.max(previous.end, interval.end);
    }
    return items;
  }, []);
  const candidates: number[] = [];
  merged.forEach((interval, index) => {
    const next = merged[index + 1];
    if (next && next.start - interval.end >= 24) {
      candidates.push((interval.end + next.start) / 2);
    }
  });
  if (merged.length) {
    candidates.push(merged[0].start - 32, merged[merged.length - 1].end + 32);
  } else {
    candidates.push((input.source.x + input.target.x) / 2);
  }
  const corridorX = candidates.reduce((best, candidate) => {
    const score = Math.abs(candidate - input.source.x) + Math.abs(candidate - input.target.x);
    const bestScore = Math.abs(best - input.source.x) + Math.abs(best - input.target.x);
    return score < bestScore ? candidate : best;
  }, candidates[0]);
  const sourceY = input.source.y + input.nodeHeight / 2;
  const targetY = input.target.y - input.nodeHeight / 2;
  const turnOffset = Math.min(24, Math.max(12, (targetY - sourceY) / 5));
  return [
    { x: input.source.x, y: sourceY },
    { x: input.source.x, y: sourceY + turnOffset },
    { x: corridorX, y: sourceY + turnOffset },
    { x: corridorX, y: targetY - turnOffset },
    { x: input.target.x, y: targetY - turnOffset },
    { x: input.target.x, y: targetY },
  ];
};

export function buildApplicationTopologyEdges(input: {
  links: ApplicationTopologySourceLink[];
  nodes: ApplicationTopologyBandNode[];
  nodeWidth: number;
  nodeHeight: number;
  rowStride: number;
}): ApplicationTopologyEdge[] {
  const byId = new Map(input.nodes.map((node) => [node.id, node]));
  const groups = new Map<string, {
    id: string;
    source: ApplicationTopologyBandNode;
    target: ApplicationTopologyBandNode;
    forward: boolean;
    reverse: boolean;
    forwardNames: Set<string>;
    reverseNames: Set<string>;
  }>();
  input.links.forEach((link, index) => {
    const source = byId.get(link.source);
    const target = byId.get(link.target);
    if (!source || !target || source.id === target.id) return;
    const sourceCenter = nodeCenter(source, input.nodeWidth, input.nodeHeight);
    const targetCenter = nodeCenter(target, input.nodeWidth, input.nodeHeight);
    const sourceFirst = sourceCenter.y < targetCenter.y
      || (sourceCenter.y === targetCenter.y && sourceCenter.x <= targetCenter.x);
    const visualSource = sourceFirst ? source : target;
    const visualTarget = sourceFirst ? target : source;
    const key = `${visualSource.id}__${visualTarget.id}`;
    const group = groups.get(key) || {
      id: link.id || `${link.source}-${link.target}-${index}`,
      source: visualSource,
      target: visualTarget,
      forward: false,
      reverse: false,
      forwardNames: new Set<string>(),
      reverseNames: new Set<string>(),
    };
    const name = String(link.asst_id || '').trim();
    if (source.id === visualSource.id) {
      group.forward = true;
      if (name) group.forwardNames.add(name);
    } else {
      group.reverse = true;
      if (name) group.reverseNames.add(name);
    }
    groups.set(key, group);
  });

  return Array.from(groups.values()).map((group) => {
    const sourceCenter = nodeCenter(group.source, input.nodeWidth, input.nodeHeight);
    const targetCenter = nodeCenter(group.target, input.nodeWidth, input.nodeHeight);
    const vertical = sourceCenter.y !== targetCenter.y;
    const farApart = Math.abs(targetCenter.y - sourceCenter.y) > input.rowStride * 2;
    const crossesLayer = Math.abs(layerIndex(group.target.layer) - layerIndex(group.source.layer)) > 1
      || farApart;
    const points = crossesLayer
      ? crossLayerPoints({
        source: sourceCenter,
        target: targetCenter,
        nodes: input.nodes,
        nodeWidth: input.nodeWidth,
        nodeHeight: input.nodeHeight,
      })
      : vertical
        ? [
          { x: sourceCenter.x, y: sourceCenter.y + input.nodeHeight / 2 },
          { x: targetCenter.x, y: targetCenter.y - input.nodeHeight / 2 },
        ]
        : [
          { x: sourceCenter.x + input.nodeWidth / 2, y: sourceCenter.y },
          { x: targetCenter.x - input.nodeWidth / 2, y: targetCenter.y },
        ];
    const forwardArrow = vertical ? '↓' : '→';
    const reverseArrow = vertical ? '↑' : '←';
    const lines = [
      ...(group.forwardNames.size
        ? [`${Array.from(group.forwardNames).join(' / ')} ${forwardArrow}`]
        : []),
      ...(group.reverseNames.size
        ? [`${Array.from(group.reverseNames).join(' / ')} ${reverseArrow}`]
        : []),
    ];
    return {
      id: group.id,
      sourceId: group.source.id,
      targetId: group.target.id,
      points,
      label: lines.length ? lines.join('\n') : null,
      markerStart: group.reverse,
      markerEnd: group.forward,
    };
  });
}

const toResourceNode = (node: ApplicationTopologySourceNode): ApplicationResourceNode => ({
  id: node.id,
  name: node.name,
  model_id: node.model_id,
  hop: node.hop ?? 0,
  category: node.category || '',
  app_topo_layer: node.app_topo_layer,
});

export function buildApplicationTopologyLayout(input: {
  centerId: string;
  nodes: ApplicationTopologySourceNode[];
  links: ApplicationTopologySourceLink[];
  laneWidth: number;
}): ApplicationTopologyLayout {
  const { width: nodeWidth, height: nodeHeight } = APPLICATION_TOPOLOGY_NODE;
  const { rail, padX, gapX, gapY, bandPadY, layerGap } = APPLICATION_TOPOLOGY_LAYOUT;
  const laneWidth = Math.max(input.laneWidth, rail + padX * 2 + nodeWidth);
  const contentWidth = laneWidth - rail - padX * 2;
  const columns = Math.max(
    1,
    Math.floor((contentWidth + gapX) / (nodeWidth + gapX)),
  );

  const sourceNodes = input.nodes.filter((node) => node?.id);
  const center =
    sourceNodes.find((node) => node.id === input.centerId) || sourceNodes[0];
  const topology = {
    center: center ? toResourceNode(center) : { id: input.centerId, name: '', model_id: '', hop: 0, category: '' },
    nodes: sourceNodes.map(toResourceNode),
    links: [],
    truncated: false,
  } satisfies ApplicationResourceTopologyData;
  const root = resolveRootNode(topology);

  const grouped: Record<LayerKey, ApplicationTopologySourceNode[]> = {
    root: [],
    service: [],
    host: [],
    appService: [],
    infrastructure: [],
  };
  sourceNodes.forEach((node) => {
    const layer = resolveLayer(topology, toResourceNode(node), root);
    if (!layer) return;
    grouped[layer].push(node);
  });
  LAYER_KEYS.forEach((key) => {
    grouped[key].sort((left, right) => left.name.localeCompare(right.name, 'zh'));
  });

  const bands: ApplicationTopologyBand[] = [];
  const placed: ApplicationTopologyBandNode[] = [];
  let yCursor = 8;
  LAYER_KEYS.forEach((key) => {
    const members = grouped[key];
    const centered = key === 'root' && members.length <= 1;
    const layerColumns = centered ? 1 : columns;
    const rows = Math.max(1, Math.ceil(members.length / layerColumns));
    const height = bandPadY * 2 + rows * nodeHeight + Math.max(0, rows - 1) * gapY;
    const top = yCursor;
    members.forEach((node, index) => {
      const row = Math.floor(index / layerColumns);
      const col = index % layerColumns;
      const rowCount = centered ? 1 : Math.min(layerColumns, members.length - row * layerColumns);
      const rowWidth = rowCount * nodeWidth + Math.max(0, rowCount - 1) * gapX;
      const rowLeft = rail + padX + Math.max(0, (contentWidth - rowWidth) / 2);
      const alertCount = node.alert_count ?? null;
      placed.push({
        id: node.id,
        name: node.name || node.id,
        modelId: node.model_id,
        layer: key,
        tone: resolveApplicationTopologyTone(alertCount, node.max_level),
        alertCount,
        maxLevel: node.max_level ?? null,
        monitorId: node.monitor_id || '',
        badge: formatAlertBadge(alertCount),
        category: node.category || '',
        x: rowLeft + col * (nodeWidth + gapX),
        y: top + bandPadY + row * (nodeHeight + gapY),
      });
    });
    bands.push({
      key,
      top,
      height,
      empty: members.length === 0,
    });
    const isLast = key === LAYER_KEYS[LAYER_KEYS.length - 1];
    yCursor += height + (isLast ? 8 : layerGap);
  });

  const edges = buildApplicationTopologyEdges({
    links: input.links,
    nodes: placed,
    nodeWidth,
    nodeHeight,
    rowStride: nodeHeight + gapY,
  });

  return {
    width: laneWidth,
    height: Math.max(yCursor, 1),
    bands,
    nodes: placed,
    edges,
  };
}
