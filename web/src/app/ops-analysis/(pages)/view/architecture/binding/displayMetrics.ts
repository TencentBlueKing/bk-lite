import { readBinding } from './model';

export const ARCHITECTURE_METRIC_BATCH_SIZE = 50;

const FIELD_KEY_PREFIX = 'field::';

export interface MetricColumn {
  name: string;
  keys: string[];
}

export interface MetricCell {
  value: string | number | null;
  unit: string;
}

export interface DisplayMetricItem {
  inst_uuid: string;
  monitor_object_id: string;
  values: Record<string, MetricCell>;
}

export interface MetricObjectColumns {
  columns: MetricColumn[];
}

export interface MetricChoice {
  mode: 'custom';
  keys: string[];
}

export interface MetricCardLine {
  name: string;
  text: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object';

export function columnOptionValue(column: MetricColumn): string {
  return column.keys.join('\n');
}

export function readDisplayMetrics(value: unknown): MetricChoice | undefined {
  if (!isRecord(value) || value.mode !== 'custom' || !Array.isArray(value.keys)) return undefined;
  const keys = value.keys.filter((key): key is string => typeof key === 'string' && key.length > 0);
  if (!keys.length) return undefined;
  return { mode: 'custom', keys };
}

function metricColumns(columns: MetricColumn[]): MetricColumn[] {
  return columns
    .map((column) => ({
      name: column.name,
      keys: column.keys.filter((key) => key && !key.startsWith(FIELD_KEY_PREFIX)),
    }))
    .filter((column) => column.keys.length > 0);
}

export function visibleColumns(columns: MetricColumn[], choice: MetricChoice | undefined): MetricColumn[] {
  if (!choice) return [];
  const selected = new Set(choice.keys);
  return metricColumns(columns).filter((column) => column.keys.some((key) => selected.has(key)));
}

export function formatMetricText(cell: MetricCell | undefined): string {
  if (!cell || cell.value === null || cell.value === '') return '—';
  const unit = cell.unit ? ` ${cell.unit}` : '';
  return `${cell.value}${unit}`;
}

export function metricCardLines(
  columns: MetricColumn[],
  values: Record<string, MetricCell>,
  choice: MetricChoice | undefined,
): MetricCardLine[] {
  return visibleColumns(columns, choice).map((column) => {
    let cell: MetricCell | undefined;
    for (const key of column.keys) {
      const candidate = values[key];
      if (candidate && candidate.value !== null && candidate.value !== '') {
        cell = candidate;
        break;
      }
    }
    return { name: column.name, text: formatMetricText(cell) };
  });
}

function parseCell(value: unknown): MetricCell {
  if (!isRecord(value)) return { value: null, unit: '' };
  const unit = typeof value.unit === 'string' ? value.unit : '';
  const raw = value.value;
  if (typeof raw === 'number' && Number.isFinite(raw)) return { value: raw, unit };
  if (typeof raw === 'string' && raw !== '') return { value: raw, unit };
  return { value: null, unit };
}

function parseColumns(value: unknown): MetricColumn[] {
  if (!Array.isArray(value)) return [];
  const columns: MetricColumn[] = [];
  for (const entry of value) {
    if (!isRecord(entry) || !Array.isArray(entry.keys)) continue;
    const keys = entry.keys.filter((key): key is string => typeof key === 'string' && key.length > 0);
    if (!keys.length) continue;
    columns.push({
      name: typeof entry.name === 'string' ? entry.name : '',
      keys,
    });
  }
  return columns;
}

export function parseDisplayMetricsPayload(data: unknown): {
  objects: Record<string, MetricObjectColumns>;
  items: DisplayMetricItem[];
} {
  const objects: Record<string, MetricObjectColumns> = {};
  const items: DisplayMetricItem[] = [];
  if (!isRecord(data)) return { objects, items };
  if (isRecord(data.objects)) {
    for (const [objectId, entry] of Object.entries(data.objects)) {
      if (!isRecord(entry)) continue;
      objects[objectId] = { columns: parseColumns(entry.columns) };
    }
  }
  if (Array.isArray(data.items)) {
    for (const entry of data.items) {
      if (!isRecord(entry)) continue;
      const instUuid = typeof entry.inst_uuid === 'string' ? entry.inst_uuid : '';
      const monitorObjectId = typeof entry.monitor_object_id === 'string' ? entry.monitor_object_id : '';
      if (!instUuid || !monitorObjectId) continue;
      const values: Record<string, MetricCell> = {};
      if (isRecord(entry.values)) {
        for (const [key, cell] of Object.entries(entry.values)) {
          values[key] = parseCell(cell);
        }
      }
      items.push({ inst_uuid: instUuid, monitor_object_id: monitorObjectId, values });
    }
  }
  return { objects, items };
}

export function combineMetricBatches(
  batches: Array<{ uuids: string[]; ok: boolean; data?: unknown }>,
  previous: Record<string, DisplayMetricItem>,
): { byUuid: Record<string, DisplayMetricItem>; objects: Record<string, MetricObjectColumns>; failed: boolean } {
  const byUuid: Record<string, DisplayMetricItem> = {};
  const objects: Record<string, MetricObjectColumns> = {};
  let failed = false;
  for (const batch of batches) {
    if (!batch.ok) {
      failed = true;
      for (const uuid of batch.uuids) {
        const kept = previous[uuid];
        if (kept) byUuid[uuid] = kept;
      }
      continue;
    }
    const parsed = parseDisplayMetricsPayload(batch.data);
    Object.assign(objects, parsed.objects);
    const returned = new Set(parsed.items.map((item) => item.inst_uuid));
    for (const item of parsed.items) {
      if (batch.uuids.includes(item.inst_uuid)) byUuid[item.inst_uuid] = item;
    }
    for (const uuid of batch.uuids) {
      if (!returned.has(uuid)) delete byUuid[uuid];
    }
  }
  return { byUuid, objects, failed };
}

interface MetricNodeRef {
  id: string;
  instUuid: string;
  choice: MetricChoice | undefined;
}

function nodeRefs(views: unknown): MetricNodeRef[] {
  const refs: MetricNodeRef[] = [];
  const viewList = Array.isArray(views) ? views : [];
  for (const view of viewList) {
    if (!isRecord(view) || !Array.isArray(view.items)) continue;
    for (const entry of view.items) {
      if (!isRecord(entry) || typeof entry.id !== 'string') continue;
      const binding = readBinding(entry.bkBinding);
      if (!binding) continue;
      refs.push({
        id: entry.id,
        instUuid: binding.inst_uuid,
        choice: readDisplayMetrics(entry.bkDisplayMetrics),
      });
    }
  }
  return refs;
}

export function findNodeMetricChoice(views: unknown, id: string): MetricChoice | undefined {
  return nodeRefs(views).find((node) => node.id === id)?.choice;
}

export function collectMetricUuids(views: unknown): string[] {
  const found = nodeRefs(views)
    .filter((node) => Boolean(node.choice?.keys.length))
    .map((node) => node.instUuid);
  return Array.from(new Set(found)).sort();
}

export function buildNodeMetricCards(
  views: unknown,
  byUuid: Record<string, DisplayMetricItem>,
  objects: Record<string, MetricObjectColumns>,
): Record<string, { lines: MetricCardLine[] }> {
  const next: Record<string, { lines: MetricCardLine[] }> = {};
  for (const node of nodeRefs(views)) {
    if (!node.choice) continue;
    const item = byUuid[node.instUuid];
    if (!item) continue;
    const columns = objects[item.monitor_object_id]?.columns ?? [];
    const lines = metricCardLines(columns, item.values, node.choice);
    if (!lines.length) continue;
    next[node.id] = { lines };
  }
  return next;
}
