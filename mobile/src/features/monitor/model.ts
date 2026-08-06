export const MONITOR_PAGE_SIZE = 20;
export const INSTANCE_LIST_SUMMARY_LIMIT = 3;

const DISPLAY_FIELD_KEY_SEP = '::';
const FIELD_DISPLAY_KEY_PREFIX = 'field';

export interface MonitorObjectType {
  id: string;
  name: string;
  displayName: string;
  order: number;
}

export interface MonitorDisplayBinding {
  plugin: string;
  metric: string;
  field: string;
}

export interface MonitorDisplayField {
  key: string;
  name: string;
  type: 'metric' | 'field';
  metrics: MonitorDisplayBinding[];
  order: number;
}

export interface MonitorObject {
  id: number;
  name: string;
  displayName: string;
  description: string;
  icon: string;
  order: number;
  level: string;
  visible: boolean;
  instanceCount: number;
  instanceIdKeys: string[];
  displayFields: MonitorDisplayField[];
  type: MonitorObjectType;
}

export interface MonitorInstance {
  id: string;
  name: string;
  idValues: string[];
  status: string;
  lastReportedAt: number | null;
  interval: number | null;
  facts: Record<string, unknown>;
  raw: Record<string, unknown>;
}

export interface MonitorPlugin {
  id: number;
  name: string;
  displayName: string;
  isPre: boolean;
  isCustom: boolean;
  status: string;
}

export interface MetricGroup {
  id: number;
  name: string;
  displayName: string;
  order: number;
}

export interface MonitorMetric {
  id: number;
  groupId: number;
  name: string;
  displayName: string;
  description: string;
  query: string;
  unit: string;
  instanceIdKeys: string[];
  order: number;
}

export interface MetricSeries {
  metric: Record<string, string>;
  values: Array<[number, string]>;
}

export interface MetricRangeResult {
  unit: string;
  series: MetricSeries[];
}

export interface PageResult<T> {
  count: number;
  items: T[];
}

export function monitorRequestErrorKind(error: unknown): 'forbidden' | 'missing' | 'error' {
  if (!(error instanceof Error)) return 'error';
  if (/API Error:\s*403\b/.test(error.message)) return 'forbidden';
  if (/API Error:\s*404\b/.test(error.message)) return 'missing';
  return 'error';
}

export function groupMonitorObjects(objects: readonly MonitorObject[]) {
  const grouped = new Map<string, { type: MonitorObjectType; objects: MonitorObject[] }>();
  for (const object of objects.filter((item) => item.visible)) {
    const current = grouped.get(object.type.id) || { type: object.type, objects: [] };
    current.objects.push(object);
    grouped.set(object.type.id, current);
  }
  return Array.from(grouped.values())
    .map((group) => ({ ...group, objects: group.objects.sort((a, b) => a.order - b.order) }))
    .sort((a, b) => a.type.order - b.type.order);
}

/** 与对象树同序的扁平列表，供侧滑邻接切换。 */
export function orderedMonitorObjects(objects: readonly MonitorObject[]) {
  return groupMonitorObjects(objects).flatMap((group) => group.objects);
}

export function sortMonitorInstances(instances: readonly MonitorInstance[]) {
  return [...instances].sort((left, right) => {
    const leftRank = left.status === 'normal' ? 1 : 0;
    const rightRank = right.status === 'normal' ? 1 : 0;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return (right.lastReportedAt || 0) - (left.lastReportedAt || 0);
  });
}

/** 与 Web / 服务端 display_field_key 保持一致。 */
export function displayFieldKey(plugin = '', metric = '', field?: string) {
  if (field) {
    return `${FIELD_DISPLAY_KEY_PREFIX}${DISPLAY_FIELD_KEY_SEP}${plugin}${DISPLAY_FIELD_KEY_SEP}${metric}${DISPLAY_FIELD_KEY_SEP}${field}`;
  }
  return plugin ? `${plugin}${DISPLAY_FIELD_KEY_SEP}${metric}` : metric;
}

function readInstanceField(instance: MonitorInstance, key: string) {
  if (!key) return undefined;
  if (Object.prototype.hasOwnProperty.call(instance.raw, key)) return instance.raw[key];
  if (Object.prototype.hasOwnProperty.call(instance.facts, key)) return instance.facts[key];
  return undefined;
}

function formatDisplayValue(raw: unknown): string | null {
  if (raw === undefined || raw === null || raw === '') return null;
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const cell = raw as Record<string, unknown>;
    if (cell.value === undefined || cell.value === null || cell.value === '') return null;
    const value = String(cell.value);
    const unit = cell.unit === undefined || cell.unit === null ? '' : String(cell.unit);
    return unit ? `${value}${unit}` : value;
  }
  return String(raw);
}

/** 按 Web resolveCell 规则取列值：绑定顺序首个有值；兼容 column_key / fact 回退。 */
export function resolveDisplayFieldValue(field: MonitorDisplayField, instance: MonitorInstance) {
  for (const binding of field.metrics || []) {
    const key = displayFieldKey(
      binding.plugin,
      binding.metric,
      field.type === 'field' ? binding.field : undefined,
    );
    const formatted = formatDisplayValue(readInstanceField(instance, key));
    if (formatted !== null) return formatted;
  }
  return formatDisplayValue(readInstanceField(instance, field.key));
}

export function instanceSummaryEntries(
  object: MonitorObject,
  instance: MonitorInstance,
  limit = 4,
) {
  return object.displayFields
    .map((field) => ({ label: field.name, value: resolveDisplayFieldValue(field, instance) }))
    .filter((entry) => entry.value !== null)
    .slice(0, limit)
    .map((entry) => ({ label: entry.label, value: entry.value as string }));
}

/** 列表按元数据顺序取前 N 条摘要列；空值保留为 null，由界面显示为 `--`。 */
export function instanceListSummaryEntries(
  object: MonitorObject,
  instance: MonitorInstance,
  limit = INSTANCE_LIST_SUMMARY_LIMIT,
) {
  return object.displayFields.slice(0, limit).map((field) => ({
    label: field.name,
    value: resolveDisplayFieldValue(field, instance),
  }));
}

export function buildMetricQuery(metric: MonitorMetric, idValues: string[]) {
  const merged = new Map<string, Set<string>>();
  metric.instanceIdKeys.forEach((key, index) => {
    const value = idValues[index];
    if (!key || value === undefined) return;
    const values = merged.get(key) || new Set<string>();
    values.add(value);
    merged.set(key, values);
  });
  const escape = (value: string) => value
    .replace(/[\\^$.*+?()[\]{}|]/g, '\\$&')
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"');
  const labels = Array.from(merged.entries())
    .map(([key, values]) => `${key}=~"${Array.from(values).map(escape).join('|')}"`)
    .join(',');
  return metric.query.replace(/__\$labels__/g, labels);
}

export function metricPoints(result: MetricRangeResult) {
  return result.series.flatMap((series) => series.values)
    .map(([timestamp, value]) => [Number(timestamp), Number(value)] as const)
    .filter((point) => Number.isFinite(point[0]) && Number.isFinite(point[1]))
    .sort((left, right) => left[0] - right[0]);
}

export function metricSeriesPoints(result: MetricRangeResult) {
  return result.series.map((series) => ({
    labels: series.metric,
    points: series.values
      .map(([timestamp, value]) => [Number(timestamp), Number(value)] as const)
      .filter((point) => Number.isFinite(point[0]) && Number.isFinite(point[1]))
      .sort((left, right) => left[0] - right[0]),
  })).filter((series) => series.points.length > 0);
}
