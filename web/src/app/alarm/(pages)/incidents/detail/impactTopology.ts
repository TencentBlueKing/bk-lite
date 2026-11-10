import { BRAND } from '@/app/alarm/constants/colors';

export interface ImpactTopologyNode {
  inst_uuid: string;
  inst_name?: string;
  model_id?: string;
  model_name?: string;
  layer?: string;
  role?: string;
  found?: boolean;
}

export interface ImpactTopologyLink {
  src_inst_uuid: string;
  dst_inst_uuid: string;
  model_asst_id?: string;
  asst_id?: string;
  asst_name?: string;
  parent_inst_uuid?: string;
}

export interface ImpactTopologyPayload {
  relation_status?: string;
  message?: string;
  truncated?: boolean;
  nodes?: ImpactTopologyNode[];
  links?: ImpactTopologyLink[];
}

export interface ImpactAlertRef {
  id: number;
  title?: string;
  level?: string | number | null;
  resource_name?: string | null;
  resource_type?: string | null;
  monitor_objects?: Array<{
    cmdb_id?: string | null;
    resource_name?: string | null;
    resource_type?: string | null;
  }> | null;
}

export interface ImpactLevelRef {
  level_id: number;
  level_display_name?: string;
  level_name?: string;
  color?: string;
}

export interface ImpactCopy {
  bridge: string;
  unbound: string;
  alertCount: (count: number) => string;
  notPurchased: string;
  unavailable: string;
  truncated: string;
  unboundHint: string;
}

export const defaultImpactCopy: ImpactCopy = {
  bridge: '桥接',
  unbound: '未绑定 CMDB',
  alertCount: (count) => `${count} 条告警`,
  notPurchased: '未购买 CMDB，无法按配置关系展示影响拓扑',
  unavailable: '配置关系暂时查不到',
  truncated: '关系未展开',
  unboundHint: '这些告警没有绑定 CMDB 对象',
};

export interface ImpactGraphAlert {
  id: number;
  title: string;
}

export interface ImpactLinkedObject {
  id: string;
  label: string;
  alerts: ImpactGraphAlert[];
}

export interface ImpactGraphNode {
  id: string;
  kind: 'seed' | 'bridge' | 'unbound';
  label: string;
  detail: string;
  color: string | null;
  levelName: string;
  layer: string;
  alerts: ImpactGraphAlert[];
  linkedObjects: ImpactLinkedObject[];
  relations: string[];
  x: number;
  y: number;
}

export interface ImpactGraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface ImpactGraphModel {
  mode: 'empty' | 'not_purchased' | 'graph';
  message: string;
  hint: string;
  nodes: ImpactGraphNode[];
  edges: ImpactGraphEdge[];
  width: number;
  height: number;
}

const LAYER_ORDER = ['system', 'service', 'host', 'appService', 'infrastructure', 'none', 'unbound'];
export const IMPACT_NODE_WIDTH = 188;
export const IMPACT_NODE_HEIGHT = 64;
const GAP_X = 28;
const GAP_Y = 56;
const PAD = 28;

export function canonicalUuid(value: unknown): string {
  if (value == null) return '';
  return String(value).trim().toLowerCase();
}

export function collectSeedUuids(alerts: ImpactAlertRef[]): string[] {
  const seen = new Set<string>();
  const seeds: string[] = [];
  alerts.forEach((alert) => {
    (alert.monitor_objects || []).forEach((item) => {
      const uuid = canonicalUuid(item?.cmdb_id);
      if (!uuid || seen.has(uuid)) return;
      seen.add(uuid);
      seeds.push(uuid);
    });
  });
  return seeds;
}

export function buildImpactGraph(
  alerts: ImpactAlertRef[],
  payload: ImpactTopologyPayload | null,
  levels: ImpactLevelRef[] = [],
  levelColors: Record<string, string> = {},
  copy: ImpactCopy = defaultImpactCopy,
): ImpactGraphModel {
  if (alerts.length === 0) {
    return blank('empty', '');
  }
  if (payload?.relation_status === 'not_purchased') {
    return blank('not_purchased', payload.message || copy.notPurchased);
  }

  const degraded = !payload || payload.relation_status === 'unavailable';
  const truncated = !degraded && Boolean(payload?.truncated);
  const buckets = seedBuckets(alerts);
  const nodes: ImpactGraphNode[] = [];
  buckets.forEach((bucket) => {
    const apiNode = degraded ? undefined : apiNodeById(payload).get(bucket.id);
    const found = Boolean(apiNode && apiNode.found !== false);
    nodes.push({
      id: bucket.id,
      kind: 'seed',
      label: bucket.label || (found ? apiNode?.inst_name || '' : ''),
      detail: copy.alertCount(bucket.alerts.length),
      color: colorFor(bucket.levelId, levels, levelColors),
      levelName: levelName(bucket.levelId, levels),
      layer: found ? normalizeLayer(apiNode?.layer) : 'none',
      alerts: bucket.alerts.map((alert) => ({ id: alert.id, title: alert.title || '' })),
      linkedObjects: [],
      relations: [],
      x: 0,
      y: 0,
    });
  });

  if (!degraded && !truncated) {
    (payload?.nodes || []).forEach((apiNode) => {
      if (apiNode.role !== 'bridge') return;
      const id = canonicalUuid(apiNode.inst_uuid);
      if (!id || nodes.some((node) => node.id === id)) return;
      nodes.push({
        id,
        kind: 'bridge',
        label: apiNode.inst_name || apiNode.model_name || '',
        detail: copy.bridge,
        color: null,
        levelName: '',
        layer: normalizeLayer(apiNode.layer),
        alerts: [],
        linkedObjects: [],
        relations: [],
        x: 0,
        y: 0,
      });
    });
  }

  nodes.push(...unboundNodes(alerts, copy));
  const edges = !degraded && !truncated ? linksFor(payload, nodes) : [];
  attachRelations(nodes, edges);
  const box = layout(nodes);
  let hint = '';
  if (degraded) hint = payload?.message || copy.unavailable;
  else if (truncated) hint = copy.truncated;
  else if (buckets.size === 0 && nodes.some((node) => node.kind === 'unbound')) hint = copy.unboundHint;
  return {
    mode: 'graph',
    message: '',
    hint,
    nodes,
    edges,
    width: box.width,
    height: box.height,
  };
}

function blank(mode: ImpactGraphModel['mode'], message: string): ImpactGraphModel {
  return {
    mode,
    message,
    hint: '',
    nodes: [],
    edges: [],
    width: 0,
    height: 0,
  };
}

function apiNodeById(payload: ImpactTopologyPayload | null): Map<string, ImpactTopologyNode> {
  const found = new Map<string, ImpactTopologyNode>();
  (payload?.nodes || []).forEach((node) => {
    const id = canonicalUuid(node.inst_uuid);
    if (id) found.set(id, node);
  });
  return found;
}

interface SeedBucket {
  id: string;
  label: string;
  alerts: ImpactAlertRef[];
  levelId: number | null;
}

function seedBuckets(alerts: ImpactAlertRef[]): Map<string, SeedBucket> {
  const buckets = new Map<string, SeedBucket>();
  alerts.forEach((alert) => {
    const seen = new Set<string>();
    (alert.monitor_objects || []).forEach((item) => {
      const id = canonicalUuid(item?.cmdb_id);
      if (!id || seen.has(id)) return;
      seen.add(id);
      const current = buckets.get(id) || {
        id,
        label: '',
        alerts: [],
        levelId: null,
      };
      if (!current.label) {
        current.label = resourceLabel(item.resource_name, alert.title);
      }
      current.alerts.push(alert);
      const nextLevel = levelNumber(alert.level);
      if (nextLevel != null && (current.levelId == null || nextLevel < current.levelId)) {
        current.levelId = nextLevel;
      }
      buckets.set(id, current);
    });
  });
  return buckets;
}

function unboundNodes(alerts: ImpactAlertRef[], copy: ImpactCopy): ImpactGraphNode[] {
  const nodes: ImpactGraphNode[] = [];
  alerts.forEach((alert) => {
    const objects = alert.monitor_objects;
    if (!objects || objects.length === 0) {
      nodes.push(unboundNode(alert, 0, resourceLabel(alert.resource_name, alert.title), copy));
      return;
    }
    objects.forEach((item, index) => {
      if (canonicalUuid(item?.cmdb_id)) return;
      nodes.push(unboundNode(alert, index, resourceLabel(item.resource_name, alert.title), copy));
    });
  });
  return nodes;
}

function unboundNode(alert: ImpactAlertRef, index: number, label: string, copy: ImpactCopy): ImpactGraphNode {
  return {
    id: `unbound:${alert.id}:${index}`,
    kind: 'unbound',
    label: label || alert.title || '',
    detail: copy.unbound,
    color: null,
    levelName: '',
    layer: 'unbound',
    alerts: [{ id: alert.id, title: alert.title || '' }],
    linkedObjects: [],
    relations: [],
    x: 0,
    y: 0,
  };
}

function linksFor(payload: ImpactTopologyPayload | null, nodes: ImpactGraphNode[]): ImpactGraphEdge[] {
  const ids = new Set(nodes.map((node) => node.id));
  const edges: ImpactGraphEdge[] = [];
  const seen = new Set<string>();
  (payload?.links || []).forEach((link) => {
    const source = canonicalUuid(link.src_inst_uuid);
    const target = canonicalUuid(link.dst_inst_uuid);
    const id = `${source}|${target}|${link.model_asst_id || link.asst_id || ''}`;
    if (!source || !target || !ids.has(source) || !ids.has(target) || seen.has(id)) return;
    seen.add(id);
    edges.push({
      id,
      source,
      target,
      label: link.asst_name || '',
    });
  });
  return edges;
}

function attachRelations(nodes: ImpactGraphNode[], edges: ImpactGraphEdge[]) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  edges.forEach((edge) => {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) return;
    const text = [source.label, edge.label, target.label].filter(Boolean).join(' ');
    source.relations.push(text);
    if (text) target.relations.push(text);
  });
  nodes.forEach((node) => {
    if (node.kind !== 'bridge') return;
    const linked: ImpactLinkedObject[] = [];
    edges.forEach((edge) => {
      const otherId = edge.source === node.id ? edge.target : edge.target === node.id ? edge.source : '';
      const other = otherId ? byId.get(otherId) : undefined;
      if (!other || other.kind === 'bridge' || linked.some((item) => item.id === other.id)) return;
      linked.push({
        id: other.id,
        label: other.label,
        alerts: other.alerts.map((alert) => ({ ...alert })),
      });
    });
    node.linkedObjects = linked;
  });
}

function layout(nodes: ImpactGraphNode[]) {
  const groups = new Map<string, ImpactGraphNode[]>();
  nodes.forEach((node) => {
    const layer = LAYER_ORDER.includes(node.layer) ? node.layer : 'none';
    const row = groups.get(layer) || [];
    row.push(node);
    groups.set(layer, row);
  });
  const rows = LAYER_ORDER.filter((layer) => groups.has(layer));
  const rowWidth = (count: number) => count * IMPACT_NODE_WIDTH + Math.max(0, count - 1) * GAP_X;
  const contentWidth = rows.reduce((max, layer) => Math.max(max, rowWidth((groups.get(layer) || []).length)), 0);
  const width = PAD * 2 + contentWidth;
  rows.forEach((layer, rowIndex) => {
    const row = groups.get(layer) || [];
    const offset = PAD + (contentWidth - rowWidth(row.length)) / 2;
    row.forEach((node, index) => {
      node.x = offset + index * (IMPACT_NODE_WIDTH + GAP_X);
      node.y = PAD + rowIndex * (IMPACT_NODE_HEIGHT + GAP_Y);
    });
  });
  const height = Math.max(
    PAD * 2,
    PAD * 2 + rows.length * IMPACT_NODE_HEIGHT + Math.max(0, rows.length - 1) * GAP_Y,
  );
  return { width, height };
}

function resourceLabel(name?: string | null, title?: string | null): string {
  return name?.trim() || title?.trim() || '';
}

function levelNumber(level: ImpactAlertRef['level']): number | null {
  if (level == null || level === '') return null;
  const value = typeof level === 'number' ? level : Number(level);
  return Number.isFinite(value) ? value : null;
}

function colorFor(
  levelId: number | null,
  levels: ImpactLevelRef[],
  levelColors: Record<string, string>,
): string {
  if (levelId == null) return BRAND.LEVEL_FALLBACK_AMBER;
  return levelColors[String(levelId)]
    || levels.find((item) => item.level_id === levelId)?.color
    || BRAND.LEVEL_FALLBACK_AMBER;
}

function levelName(levelId: number | null, levels: ImpactLevelRef[]): string {
  if (levelId == null) return '';
  const level = levels.find((item) => item.level_id === levelId);
  return level?.level_display_name || level?.level_name || '';
}

function normalizeLayer(layer?: string): string {
  return layer && LAYER_ORDER.includes(layer) ? layer : 'none';
}
