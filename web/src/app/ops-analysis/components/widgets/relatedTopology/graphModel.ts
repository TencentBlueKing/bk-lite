import type {
  RelatedTopologyGraphEdge,
  RelatedTopologyGraphModel,
  RelatedTopologyGraphNode,
  RelatedTopologyResponse,
  RelatedTopologyTreeNode,
} from './types';
import { RELATED_TOPOLOGY_VISUAL } from './visual';

const HORIZONTAL_GAP = RELATED_TOPOLOGY_VISUAL.columnGap;
const MIN_VERTICAL_GAP = RELATED_TOPOLOGY_VISUAL.rowGap;
const NODE_VERTICAL_GAP = RELATED_TOPOLOGY_VISUAL.rowGap;
const ASSOCIATION_TYPE_NAME: Record<string, string> = {
  belong: '属于',
  group: '组成',
  run: '运行于',
  install_on: '安装于',
  contains: '包含',
  connect: '关联',
};

export function resolveAssociationLabel(
  asstName?: string | null,
  asstId?: string | null,
): string {
  const named = String(asstName || '').trim();
  if (named) {
    return named;
  }
  const id = String(asstId || '').trim();
  return ASSOCIATION_TYPE_NAME[id] || id;
}

export function formatAlertBadgeText(
  count: number | null | undefined,
): string | null {
  if (count == null || count <= 0) {
    return null;
  }
  return count > 99 ? '99+' : String(count);
}

export const ALERT_CARD_STROKE_WIDTH = 1;

export function alertBadgeFill(maxLevel: string | null | undefined): string {
  const normalized = String(maxLevel || '').toLowerCase();
  if (
    normalized === 'critical' ||
    normalized === 'error' ||
    normalized === '0' ||
    normalized === '1'
  ) {
    return 'var(--color-fail)';
  }
  return 'var(--color-warning)';
}

export function alertCardStroke(
  alertCount: number | null | undefined,
  maxLevel: string | null | undefined,
): { stroke: string; strokeWidth: number } | null {
  if (!formatAlertBadgeText(alertCount)) {
    return null;
  }
  return {
    stroke: alertBadgeFill(maxLevel),
    strokeWidth: ALERT_CARD_STROKE_WIDTH,
  };
}

export function isEmptyRelatedTopology(
  payload: RelatedTopologyResponse | null | undefined,
): boolean {
  if (!payload) {
    return true;
  }
  const srcChildren = asTree(payload.src_result)?.children?.length ?? 0;
  const dstChildren = asTree(payload.dst_result)?.children?.length ?? 0;
  return srcChildren === 0 && dstChildren === 0;
}

export function buildRelatedTopologyGraph(
  payload: RelatedTopologyResponse,
): RelatedTopologyGraphModel {
  const centerId = String(payload.center_inst_uuid || '');
  const nodes = new Map<string, RelatedTopologyGraphNode>();
  const edges: RelatedTopologyGraphEdge[] = [];
  const srcRoot = asTree(payload.src_result);
  const dstRoot = asTree(payload.dst_result);

  const ensureNode = (treeNode: RelatedTopologyTreeNode): string | null => {
    const id = String(treeNode.inst_uuid || '');
    if (!id) {
      return null;
    }
    const existing = nodes.get(id);
    if (existing) {
      return id;
    }
    nodes.set(id, {
      id,
      name: String(treeNode.inst_name || id),
      modelId: String(treeNode.model_id || ''),
      modelName: String(treeNode.model_name || '').trim() || String(treeNode.model_id || ''),
      isCenter: id === centerId,
      monitorId: String(treeNode.monitor_id || ''),
      alertCount:
        treeNode.alert_count === undefined ? null : treeNode.alert_count,
      maxLevel: treeNode.max_level ?? null,
      x: 0,
      y: 0,
    });
    return id;
  };

  const walk = (
    treeNode: RelatedTopologyTreeNode | null,
    depth: number,
    direction: -1 | 1,
    parentId: string | null,
  ) => {
    if (!treeNode) {
      return;
    }
    const id = ensureNode(treeNode);
    if (!id) {
      return;
    }
    const node = nodes.get(id);
    if (node && (id !== centerId || depth === 0)) {
      node.x = direction * HORIZONTAL_GAP * depth;
    }
    if (parentId && parentId !== id) {
      const edgeId = `${parentId}->${id}:${direction}:${edges.length}`;
      edges.push({
        id: edgeId,
        source: direction === -1 ? parentId : id,
        target: direction === -1 ? id : parentId,
        label: resolveAssociationLabel(treeNode.asst_name, treeNode.asst_id),
      });
    }
    (treeNode.children || []).forEach((child) =>
      walk(child, depth + 1, direction, id),
    );
  };

  if (srcRoot) {
    walk(srcRoot, 0, -1, null);
  }
  if (dstRoot) {
    walk(dstRoot, 0, 1, null);
  }

  const positioned = layoutColumns(Array.from(nodes.values()), centerId);
  return {
    centerId,
    empty: isEmptyRelatedTopology(payload),
    nodes: positioned,
    edges,
  };
}

function asTree(
  value: RelatedTopologyResponse['src_result'],
): RelatedTopologyTreeNode | null {
  if (!value || typeof value !== 'object' || !('inst_uuid' in value) || !value.inst_uuid) {
    return null;
  }
  return value;
}

function layoutColumns(
  nodes: RelatedTopologyGraphNode[],
  centerId: string,
): RelatedTopologyGraphNode[] {
  const columns = new Map<number, RelatedTopologyGraphNode[]>();
  nodes.forEach((node) => {
    const column = node.id === centerId ? 0 : Math.round(node.x / HORIZONTAL_GAP);
    const list = columns.get(column) || [];
    list.push(node);
    columns.set(column, list);
  });

  columns.forEach((columnNodes, column) => {
    const gap = Math.max(MIN_VERTICAL_GAP, NODE_VERTICAL_GAP);
    const totalHeight = (columnNodes.length - 1) * gap;
    const startY = -totalHeight / 2;
    columnNodes.forEach((node, index) => {
      node.x = column * HORIZONTAL_GAP;
      node.y = startY + index * gap;
    });
  });

  const center = nodes.find((node) => node.id === centerId);
  if (center) {
    center.x = 0;
    center.y = 0;
  }
  return nodes;
}
