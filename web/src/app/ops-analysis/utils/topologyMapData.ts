import { DagreLayout } from '@antv/layout';

export type TopologyMapLineStyle = 'solid' | 'dashed';
export type TopologyMapConnectionType = 'none' | 'single' | 'double';

export interface TopologyMapNode {
  id: string;
  instance_id: string | number;
  instance_name: string;
  model_name: string;
  subtitle?: string;
  alert_count: number;
  alert_level?: string;
}

export interface TopologyMapEdge {
  source: string;
  target: string;
  label?: string;
  line_style: TopologyMapLineStyle;
  connection_type: TopologyMapConnectionType;
}

export interface TopologyMapPayload {
  nodes: TopologyMapNode[];
  edges: TopologyMapEdge[];
}

export interface PositionedTopologyMapNode extends TopologyMapNode {
  x: number;
  y: number;
}

export interface TopologyMapLayoutResult {
  nodes: PositionedTopologyMapNode[];
  edges: TopologyMapEdge[];
}

export type TopologyMapParseResult =
  | { ok: true; data: TopologyMapPayload }
  | { ok: false; error: string };

const NODE_WIDTH = 210;
const NODE_HEIGHT = 78;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const nonEmptyText = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  return text || null;
};

export const parseTopologyMapPayload = (
  value: unknown,
): TopologyMapParseResult => {
  if (!isRecord(value) || !Array.isArray(value.nodes) || !Array.isArray(value.edges)) {
    return { ok: false, error: '数据结构不符：关系拓扑期望 nodes 与 edges 数组' };
  }

  const nodes: TopologyMapNode[] = [];
  const nodeIds = new Set<string>();
  for (let index = 0; index < value.nodes.length; index += 1) {
    const raw = value.nodes[index];
    if (!isRecord(raw)) {
      return { ok: false, error: `关系拓扑第 ${index + 1} 个节点格式错误` };
    }
    const id = nonEmptyText(raw.id);
    const instanceName = nonEmptyText(raw.instance_name);
    const modelName = nonEmptyText(raw.model_name);
    const instanceId = raw.instance_id;
    if (
      !id ||
      instanceName === null ||
      modelName === null ||
      !(
        (typeof instanceId === 'string' && instanceId.trim()) ||
        (typeof instanceId === 'number' && Number.isFinite(instanceId))
      )
    ) {
      return { ok: false, error: `关系拓扑第 ${index + 1} 个节点缺少有效 identity 或展示字段` };
    }
    if (nodeIds.has(id)) {
      return { ok: false, error: `关系拓扑节点 id 重复：${id}` };
    }
    if (
      typeof raw.alert_count !== 'number' ||
      !Number.isInteger(raw.alert_count) ||
      raw.alert_count < 0
    ) {
      return { ok: false, error: `关系拓扑节点 ${id} 的 alert_count 必须是非负整数` };
    }
    if (raw.alert_level !== undefined && typeof raw.alert_level !== 'string') {
      return { ok: false, error: `关系拓扑节点 ${id} 的 alert_level 必须是字符串` };
    }
    nodeIds.add(id);
    const subtitle = nonEmptyText(raw.subtitle);
    nodes.push({
      id,
      instance_id: typeof instanceId === 'string' ? instanceId.trim() : instanceId,
      instance_name: instanceName,
      model_name: modelName,
      alert_count: raw.alert_count,
      ...(subtitle ? { subtitle } : {}),
      ...(typeof raw.alert_level === 'string'
        ? { alert_level: raw.alert_level.trim() }
        : {}),
    });
  }

  const edges: TopologyMapEdge[] = [];
  const directedPairs = new Set<string>();
  for (let index = 0; index < value.edges.length; index += 1) {
    const raw = value.edges[index];
    if (!isRecord(raw)) {
      return { ok: false, error: `关系拓扑第 ${index + 1} 条边格式错误` };
    }
    const source = nonEmptyText(raw.source);
    const target = nonEmptyText(raw.target);
    if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) {
      return { ok: false, error: `关系拓扑第 ${index + 1} 条边的 source 或 target 无效` };
    }
    const lineStyle = raw.line_style ?? 'solid';
    const connectionType = raw.connection_type ?? 'none';
    if (lineStyle !== 'solid' && lineStyle !== 'dashed') {
      return { ok: false, error: `关系拓扑第 ${index + 1} 条边的 line_style 无效` };
    }
    if (
      connectionType !== 'none' &&
      connectionType !== 'single' &&
      connectionType !== 'double'
    ) {
      return { ok: false, error: `关系拓扑第 ${index + 1} 条边的 connection_type 无效` };
    }
    const pairKey = JSON.stringify([source, target]);
    if (directedPairs.has(pairKey)) {
      return { ok: false, error: `关系拓扑 source + target 重复：${source} → ${target}` };
    }
    directedPairs.add(pairKey);
    const label = nonEmptyText(raw.label);
    edges.push({
      source,
      target,
      line_style: lineStyle,
      connection_type: connectionType,
      ...(label ? { label } : {}),
    });
  }

  return { ok: true, data: { nodes, edges } };
};

export const isEmptyTopologyMapPayload = (value: unknown): boolean => {
  const parsed = parseTopologyMapPayload(value);
  return parsed.ok && parsed.data.nodes.length === 0;
};

export const layoutTopologyMap = async (
  payload: TopologyMapPayload,
): Promise<TopologyMapLayoutResult> => {
  if (payload.nodes.length === 0) return { nodes: [], edges: payload.edges };
  const layout = new DagreLayout({
    rankdir: 'LR',
    nodesep: 72,
    edgesep: 24,
    ranksep: 120,
    nodeSize: [NODE_WIDTH, NODE_HEIGHT],
  });
  await layout.execute({
    nodes: payload.nodes.map((item) => ({ id: item.id })),
    edges: payload.edges.map((item, index) => ({
      id: `topology-map-edge-${index}`,
      source: item.source,
      target: item.target,
    })),
  });
  const positions = new Map<string, { x: number; y: number }>();
  layout.forEachNode((item) => {
    positions.set(String(item.id), { x: item.x, y: item.y });
  });
  return {
    nodes: payload.nodes.map((item) => ({
      ...item,
      ...(positions.get(item.id) ?? { x: 0, y: 0 }),
    })),
    edges: payload.edges,
  };
};

export const TOPOLOGY_MAP_NODE_SIZE = {
  width: NODE_WIDTH,
  height: NODE_HEIGHT,
} as const;
