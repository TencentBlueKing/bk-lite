export const MONITOR_PAGE_SIZE = 20;
export const MAX_RECENT_VIEWS = 20;
export const RECENT_VIEW_SUMMARY_LIMIT = 3;

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

/** Server 的指标目录已分页；兼容历史裸数组响应，避免详情误判为未配置指标。 */
export function monitorCatalogItems(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value !== 'object' || value === null) return [];
  const items = (value as Record<string, unknown>).items;
  return Array.isArray(items) ? items : [];
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
  values: Array<[number, string | null]>;
}

export interface MetricRangeResult {
  unit: string;
  series: MetricSeries[];
}

export interface PageResult<T> {
  count: number;
  items: T[];
}

export interface MonitorRecentViewItem {
  objectId: number;
  instanceId: string;
  viewedAt: string;
}

export interface MonitorRecentViewsConfig {
  items: MonitorRecentViewItem[];
}

export interface ResolvedMonitorRecentView {
  item: MonitorRecentViewItem;
  object: MonitorObject;
  instance: MonitorInstance;
  /** 摘要枚举指标 unit 索引；缺失时回落原始值 */
  metricUnits?: Map<string, string>;
}

export function normalizeRecentViews(value: unknown): MonitorRecentViewsConfig {
  const source = typeof value === 'object' && value !== null ? value as { items?: unknown } : {};
  const items = (Array.isArray(source.items) ? source.items : []).flatMap((raw) => {
    if (typeof raw !== 'object' || raw === null) return [];
    const row = raw as Record<string, unknown>;
    const objectId = Number(row.object_id ?? row.objectId);
    const instanceId = String(row.instance_id ?? row.instanceId ?? '').trim();
    const viewedAt = String(row.viewed_at ?? row.viewedAt ?? '');
    if (!Number.isFinite(objectId) || objectId <= 0 || !instanceId) return [];
    return [{ objectId, instanceId, viewedAt }];
  }).sort((left, right) => new Date(right.viewedAt || 0).getTime() - new Date(left.viewedAt || 0).getTime())
    .slice(0, MAX_RECENT_VIEWS);
  return { items };
}

export function formatRecentViewTime(
  value: string,
  preferences: { locale: string; timezone: string },
  labels: { justNow: string; minutes: string; hours: string; yesterday: string },
  nowValue = Date.now(),
): string {
  const viewedAt = new Date(value).getTime();
  if (!Number.isFinite(viewedAt)) return '';
  const deltaMs = Math.max(0, nowValue - viewedAt);
  const deltaMinutes = Math.floor(deltaMs / 60_000);
  if (deltaMinutes < 1) return labels.justNow;
  if (deltaMinutes < 60) return labels.minutes.replace('{count}', String(deltaMinutes));
  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return labels.hours.replace('{count}', String(deltaHours));
  const locale = preferences.locale.toLowerCase().startsWith('zh') ? 'zh-Hans' : 'en';
  const timezone = preferences.timezone || 'Asia/Shanghai';
  const accountDay = (timestamp: number) => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric', month: '2-digit', day: '2-digit', timeZone: timezone,
    }).formatToParts(timestamp);
    const part = (type: Intl.DateTimeFormatPartTypes) => Number(
      parts.find((item) => item.type === type)?.value,
    );
    return Date.UTC(part('year'), part('month') - 1, part('day'));
  };
  if (accountDay(viewedAt) === accountDay(nowValue) - 86_400_000) return labels.yesterday;
  const viewedDate = new Date(viewedAt);
  return new Intl.DateTimeFormat(locale, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: timezone,
  }).format(viewedDate);
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

/** 与 Web viewList 上报状态列一致：仅 normal，其余均视为 unavailable。 */
export function resolveMonitorReportingStatus(status: string): 'normal' | 'unavailable' | '' {
  if (!status) return '';
  return status === 'normal' ? 'normal' : 'unavailable';
}

export type MonitorReportingStatusFilter = 'normal' | 'unavailable';

/** 与 Web 表头筛选一致：仅单选 status 时生效；双选/空选等同不过滤。 */
export function normalizeReportingStatusFilters(
  statuses: readonly string[] | undefined,
): MonitorReportingStatusFilter[] {
  const unique = Array.from(new Set(
    (statuses || []).filter((item): item is MonitorReportingStatusFilter => (
      item === 'normal' || item === 'unavailable'
    )),
  ));
  return unique.length === 1 ? unique : [];
}

/** 从 storage_instance_key / instance_id 提取 list 查询用的名称 hint。 */
export function parseMonitorInstanceLookupHints(instanceId: string) {
  const trimmed = instanceId.trim();
  if (!trimmed) return { name: '', idValues: [] as string[] };
  const tupleMatch = /^\((.*)\)$/.exec(trimmed);
  if (tupleMatch) {
    const parts = tupleMatch[1]
      .split(',')
      .map((part) => part.trim().replace(/^['"]|['"]$/g, ''))
      .filter(Boolean);
    return { name: parts[0] || '', idValues: parts };
  }
  return { name: trimmed, idValues: [trimmed] };
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

/** 与 Web `isStringArray` 一致：unit 为枚举选项 JSON 数组时视为枚举指标。 */
export function isEnumMetricUnit(unit: string): boolean {
  if (!unit || typeof unit !== 'string') return false;
  try {
    return Array.isArray(JSON.parse(unit));
  } catch {
    return false;
  }
}

/** 与 Web `getEnumValue` 一致：用指标 unit 中的选项表把原始值映射成可读名。 */
export function resolveEnumMetricLabel(unit: string, value: unknown): string | null {
  if (!isEnumMetricUnit(unit) || value === undefined || value === null || value === '') return null;
  try {
    const options = JSON.parse(unit) as Array<{ id?: unknown; name?: unknown }>;
    if (!Array.isArray(options)) return null;
    const numericId = Number(value);
    const match = options.find((item) => {
      if (item?.id === value) return true;
      if (!Number.isFinite(numericId)) return false;
      return Number(item?.id) === numericId;
    });
    if (match?.name === undefined || match?.name === null || match?.name === '') return null;
    return String(match.name);
  } catch {
    return null;
  }
}

export function displayMetricUnitKey(plugin: string, metric: string) {
  return plugin ? `${plugin}::${metric}` : metric;
}

/** 摘要列要用的指标名（去重），供 `name_in` 拉取枚举 unit。 */
export function displayFieldMetricNames(object: MonitorObject): string[] {
  const names = new Set<string>();
  object.displayFields.forEach((field) => {
    field.metrics.forEach((binding) => {
      if (binding.metric) names.add(binding.metric);
    });
  });
  return Array.from(names);
}

export function buildDisplayMetricUnitIndex(
  metrics: ReadonlyArray<{ name: string; unit: string; pluginName?: string }>,
): Map<string, string> {
  const index = new Map<string, string>();
  metrics.forEach((metric) => {
    if (!metric.name) return;
    if (metric.pluginName) index.set(displayMetricUnitKey(metric.pluginName, metric.name), metric.unit);
    if (!index.has(metric.name)) index.set(metric.name, metric.unit);
  });
  return index;
}

function lookupMetricUnit(
  unitIndex: Map<string, string> | undefined,
  binding: MonitorDisplayBinding,
) {
  if (!unitIndex) return undefined;
  return unitIndex.get(displayMetricUnitKey(binding.plugin, binding.metric))
    ?? unitIndex.get(binding.metric);
}

const INTEGER_METRIC_UNITS = new Set(['counts']);
const HIDDEN_DISPLAY_UNITS = new Set(['counts', 'none', 'short']);
const RAW_VALUE_METRICS = new Set(['cluster_pod_count', 'cluster_node_count']);

/** 与 Web formatMetricValue/getEnumValue 一致：计数不补零，其余普通数值保留两位。 */
export function formatMonitorTableMetricValue(
  value: unknown,
  unit = '',
  metricName = '',
): string {
  const numericValue = Number(value);
  if (Number.isNaN(numericValue) || RAW_VALUE_METRICS.has(metricName)) return String(value);
  return INTEGER_METRIC_UNITS.has(unit) ? String(numericValue) : numericValue.toFixed(2);
}

function visibleDisplayUnit(unit: string) {
  return HIDDEN_DISPLAY_UNITS.has(unit) || isEnumMetricUnit(unit) ? '' : unit;
}

function formatDisplayValue(
  raw: unknown,
  metricUnit?: string,
  metricName = '',
  formatNumeric = true,
): string | null {
  if (raw === undefined || raw === null || raw === '') return null;
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const cell = raw as Record<string, unknown>;
    if (cell.value === undefined || cell.value === null || cell.value === '') return null;
    if (metricUnit) {
      const label = resolveEnumMetricLabel(metricUnit, cell.value);
      if (label !== null) return label;
    }
    const displayUnit = cell.unit === undefined || cell.unit === null ? '' : String(cell.unit);
    const value = formatNumeric
      ? formatMonitorTableMetricValue(cell.value, displayUnit || metricUnit || '', metricName)
      : String(cell.value);
    const unit = visibleDisplayUnit(displayUnit);
    return unit ? `${value}${unit}` : value;
  }
  if (metricUnit) {
    const label = resolveEnumMetricLabel(metricUnit, raw);
    if (label !== null) return label;
  }
  return formatNumeric
    ? formatMonitorTableMetricValue(raw, metricUnit || '', metricName)
    : String(raw);
}

/** 按 Web resolveCell 规则取列值：绑定顺序首个有值；兼容 column_key / fact 回退。 */
export function resolveDisplayFieldValue(
  field: MonitorDisplayField,
  instance: MonitorInstance,
  metricUnits?: Map<string, string>,
) {
  for (const binding of field.metrics || []) {
    const key = displayFieldKey(
      binding.plugin,
      binding.metric,
      field.type === 'field' ? binding.field : undefined,
    );
    const raw = readInstanceField(instance, key);
    const metricUnit = lookupMetricUnit(metricUnits, binding);
    if (field.type === 'field') {
      if (raw != null && raw !== '') {
        const formatted = formatDisplayValue(raw, metricUnit, binding.metric, false);
        if (formatted !== null) return formatted;
      }
      continue;
    }
    const formatted = formatDisplayValue(raw, metricUnit, binding.metric);
    if (formatted !== null) return formatted;
  }
  return formatDisplayValue(
    readInstanceField(instance, field.key),
    undefined,
    field.metrics?.[0]?.metric,
    field.type !== 'field',
  );
}

export function instanceSummaryEntries(
  object: MonitorObject,
  instance: MonitorInstance,
  limit = 4,
  metricUnits?: Map<string, string>,
) {
  return object.displayFields
    .map((field) => ({ label: field.name, value: resolveDisplayFieldValue(field, instance, metricUnits) }))
    .filter((entry) => entry.value !== null)
    .slice(0, limit)
    .map((entry) => ({ label: entry.label, value: entry.value as string }));
}

/** 列表按元数据顺序输出 display_fields；传入 limit 时仅供紧凑场景使用。 */
export function instanceListSummaryEntries(
  object: MonitorObject,
  instance: MonitorInstance,
  limit?: number,
  metricUnits?: Map<string, string>,
) {
  const fields = limit === undefined ? object.displayFields : object.displayFields.slice(0, limit);
  return fields.map((field) => ({
    label: field.name,
    value: resolveDisplayFieldValue(field, instance, metricUnits),
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
    .flatMap(([timestamp, value]) => {
      const nextTimestamp = Number(timestamp);
      const nextValue = value === null || value === '' ? Number.NaN : Number(value);
      return Number.isFinite(nextTimestamp) && Number.isFinite(nextValue)
        ? [[nextTimestamp, nextValue] as const]
        : [];
    })
    .sort((left, right) => left[0] - right[0]);
}

export function metricSeriesPoints(result: MetricRangeResult) {
  return result.series.map((series) => ({
    labels: series.metric,
    points: series.values
      .flatMap(([timestamp, value]) => {
        const nextTimestamp = Number(timestamp);
        if (!Number.isFinite(nextTimestamp)) return [];
        if (value === null || value === '') return [[nextTimestamp, null] as const];
        const nextValue = Number(value);
        return [[nextTimestamp, Number.isFinite(nextValue) ? nextValue : null] as const];
      })
      .sort((left, right) => left[0] - right[0]),
  })).filter((series) => series.points.some((point) => point[1] !== null));
}
