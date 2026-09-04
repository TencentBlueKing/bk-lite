import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

export type NodeGraphIdentityMode = 'ip' | 'service';

export interface NodeGraphMapping {
  identityMode?: NodeGraphIdentityMode;
  sourceField?: string;
  targetField?: string;
  valueField?: string;
  targetPortField?: string;
  maxEdges?: number;
}

export interface NodeGraphNode {
  id: string;
  inbound: number;
  outbound: number;
}

export interface NodeGraphEdge {
  source: string;
  target: string;
  value: number;
}

export interface NodeGraphModel {
  nodes: NodeGraphNode[];
  edges: NodeGraphEdge[];
}

export const DEFAULT_NODE_GRAPH_MAX_EDGES = 100;
export const NODE_GRAPH_PARALLEL_OFFSET_STEP = 16;

const unwrapRows = (data: unknown): unknown[] => {
  if (Array.isArray(data)) {
    return data;
  }
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;
    for (const key of ['items', 'data', 'list'] as const) {
      if (Array.isArray(record[key])) {
        return record[key] as unknown[];
      }
    }
  }
  return [];
};

const cellText = (row: unknown, field?: string): string => {
  const raw = getValueByPath(row, field);
  if (raw === undefined || raw === null) {
    return '';
  }
  return String(raw).trim();
};

const cellNumber = (row: unknown, field?: string): number | null => {
  const raw = getValueByPath(row, field);
  const value = typeof raw === 'number' ? raw : Number(raw);
  return Number.isFinite(value) ? value : null;
};

export const toNodeGraphMapping = (config?: {
  nodeGraphIdentityMode?: NodeGraphIdentityMode;
  nodeGraphSourceField?: string;
  nodeGraphTargetField?: string;
  nodeGraphValueField?: string;
  nodeGraphTargetPortField?: string;
  maxEdges?: number;
}): NodeGraphMapping => ({
  identityMode: config?.nodeGraphIdentityMode,
  sourceField: config?.nodeGraphSourceField,
  targetField: config?.nodeGraphTargetField,
  valueField: config?.nodeGraphValueField,
  targetPortField: config?.nodeGraphTargetPortField,
  maxEdges: config?.maxEdges,
});

export const isNodeGraphMappingComplete = (
  config?: NodeGraphMapping,
): boolean => {
  if (!config?.sourceField?.trim() || !config?.targetField?.trim() || !config?.valueField?.trim()) {
    return false;
  }
  if ((config.identityMode || 'ip') === 'service' && !config.targetPortField?.trim()) {
    return false;
  }
  return true;
};

const resolveEndpoint = (
  row: unknown,
  field: string,
  portField?: string,
): string => {
  const base = cellText(row, field);
  if (!base) {
    return '';
  }
  if (!portField) {
    return base;
  }
  const port = cellText(row, portField);
  if (!port) {
    return '';
  }
  return `${base}:${port}`;
};

export const buildNodeGraph = (
  data: unknown,
  config?: NodeGraphMapping,
): NodeGraphModel => {
  if (!isNodeGraphMappingComplete(config) || !config) {
    return { nodes: [], edges: [] };
  }

  const identityMode = config.identityMode || 'ip';
  const sourceField = config.sourceField!.trim();
  const targetField = config.targetField!.trim();
  const valueField = config.valueField!.trim();
  const targetPortField =
    identityMode === 'service' ? config.targetPortField?.trim() : undefined;
  const maxEdges =
    Number.isFinite(config.maxEdges) && (config.maxEdges as number) > 0
      ? Math.floor(config.maxEdges as number)
      : DEFAULT_NODE_GRAPH_MAX_EDGES;

  const totals = new Map<string, number>();
  for (const row of unwrapRows(data)) {
    const source = resolveEndpoint(row, sourceField);
    const target = resolveEndpoint(row, targetField, targetPortField);
    const value = cellNumber(row, valueField);
    if (!source || !target || source === target || value === null) {
      continue;
    }
    const key = `${source}\0${target}`;
    totals.set(key, (totals.get(key) || 0) + value);
  }

  const edges = Array.from(totals.entries())
    .map(([key, value]) => {
      const [source, target] = key.split('\0');
      return { source, target, value };
    })
    .sort((left, right) => right.value - left.value)
    .slice(0, maxEdges);

  const nodeStats = new Map<string, NodeGraphNode>();
  const touch = (id: string): NodeGraphNode => {
    const existing = nodeStats.get(id);
    if (existing) {
      return existing;
    }
    const created = { id, inbound: 0, outbound: 0 };
    nodeStats.set(id, created);
    return created;
  };

  for (const edge of edges) {
    touch(edge.source).outbound += edge.value;
    touch(edge.target).inbound += edge.value;
  }

  return {
    nodes: Array.from(nodeStats.values()),
    edges,
  };
};

export const NODE_GRAPH_SOURCE_ID_PREFIX = 'source:';
export const NODE_GRAPH_TARGET_ID_PREFIX = 'target:';
export const NODE_GRAPH_NODE_WIDTH = 148;
export const NODE_GRAPH_NODE_HEIGHT = 28;

export type NodeGraphRole = 'source' | 'target';

export interface NodeGraphPlacedNode extends NodeGraphNode {
  graphId: string;
  label: string;
  role: NodeGraphRole;
  x: number;
  y: number;
}

export interface NodeGraphPlacedEdge extends NodeGraphEdge {
  source: string;
  target: string;
}

export interface NodeGraphBipartiteLayout {
  nodes: NodeGraphPlacedNode[];
  edges: NodeGraphPlacedEdge[];
}

const uniqueSorted = (
  ids: string[],
  weight: (id: string) => number,
): string[] =>
  Array.from(new Set(ids)).sort((left, right) => {
    const delta = weight(right) - weight(left);
    return delta !== 0 ? delta : left.localeCompare(right);
  });

const columnY = (index: number, count: number, height: number, padding: number, nodeHeight: number) => {
  if (count <= 1) {
    return Math.max(padding, (height - nodeHeight) / 2);
  }
  const usable = Math.max(height - padding * 2 - nodeHeight, nodeHeight);
  return padding + (index / (count - 1)) * usable;
};

export const layoutNodeGraphBipartite = (
  model: NodeGraphModel,
  width: number,
  height: number,
  options?: { nodeWidth?: number; nodeHeight?: number; padding?: number },
): NodeGraphBipartiteLayout => {
  if (model.edges.length === 0) {
    return { nodes: [], edges: [] };
  }

  const nodeWidth = options?.nodeWidth ?? NODE_GRAPH_NODE_WIDTH;
  const nodeHeight = options?.nodeHeight ?? NODE_GRAPH_NODE_HEIGHT;
  const padding = options?.padding ?? 28;
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const sourceIds = uniqueSorted(
    model.edges.map((edge) => edge.source),
    (id) => nodeById.get(id)?.outbound || 0,
  );
  const targetIds = uniqueSorted(
    model.edges.map((edge) => edge.target),
    (id) => nodeById.get(id)?.inbound || 0,
  );
  const columnCount = Math.max(sourceIds.length, targetIds.length, 1);
  const rowGap = 10;
  const contentHeight = padding * 2 + columnCount * nodeHeight + Math.max(columnCount - 1, 0) * rowGap;
  const layoutHeight = Math.max(height, contentHeight);
  const leftX = padding;
  const rightX = Math.max(padding, width - padding - nodeWidth);

  const place = (ids: string[], role: NodeGraphRole, x: number): NodeGraphPlacedNode[] =>
    ids.map((id, index) => {
      const stats = nodeById.get(id) || { id, inbound: 0, outbound: 0 };
      return {
        ...stats,
        graphId: `${role}:${id}`,
        label: id,
        role,
        x,
        y: columnY(index, ids.length, layoutHeight, padding, nodeHeight),
      };
    });

  return {
    nodes: [...place(sourceIds, 'source', leftX), ...place(targetIds, 'target', rightX)],
    edges: model.edges.map((edge) => ({
      ...edge,
      source: `${NODE_GRAPH_SOURCE_ID_PREFIX}${edge.source}`,
      target: `${NODE_GRAPH_TARGET_ID_PREFIX}${edge.target}`,
    })),
  };
};

export const assignNodeGraphParallelOffsets = <T extends { source: string; target: string }>(
  edges: T[],
  step = NODE_GRAPH_PARALLEL_OFFSET_STEP,
): Array<T & { parallelOffset: number }> => {
  const pairCount = new Map<string, number>();
  const pairIndex = new Map<string, number>();
  const pairKey = (source: string, target: string) =>
    [source, target].sort().join('\0');

  for (const edge of edges) {
    const key = pairKey(edge.source, edge.target);
    pairCount.set(key, (pairCount.get(key) || 0) + 1);
  }

  return edges.map((edge) => {
    const key = pairKey(edge.source, edge.target);
    const total = pairCount.get(key) || 1;
    const index = pairIndex.get(key) || 0;
    pairIndex.set(key, index + 1);
    return {
      ...edge,
      parallelOffset: total <= 1 ? 0 : (index - (total - 1) / 2) * step,
    };
  });
};
