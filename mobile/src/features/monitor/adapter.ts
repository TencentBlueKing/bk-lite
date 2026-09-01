import { apiGet, apiPost } from '@/api/request';
import type { MetricGroup, MetricRangeResult, MonitorInstance, MonitorMetric, MonitorObject, MonitorPlugin, MonitorRecentViewsConfig, MonitorRecentViewsResolution, PageResult } from './model';
import type { MonitorUnitListItem } from './unit-label';
import {
  buildDisplayMetricUnitIndex,
  displayFieldMetricNames,
  monitorCatalogItems,
  normalizeReportingStatusFilters,
} from './model';

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
}
function text(value: unknown) { return value === null || value === undefined ? '' : String(value); }
function number(value: unknown) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; }
function texts(value: unknown) { return Array.isArray(value) ? value.map(text).filter(Boolean) : []; }
function unwrap<T>(value: unknown): T {
  const data = record(value);
  if (typeof data.result !== 'boolean') return value as T;
  if (!data.result) throw new Error(text(data.message) || 'Server returned an error');
  return data.data as T;
}

const LEGACY_INSTANCE_LOOKUP_PAGE_SIZE = 100;
const LEGACY_INSTANCE_LOOKUP_MAX_PAGES = 20;

function mapMonitorInstance(value: unknown): MonitorInstance {
  const item = record(value);
  return {
    id: text(item.instance_id),
    name: text(item.instance_name || item.instance_id),
    idValues: texts(item.instance_id_values),
    status: text(item.status),
    lastReportedAt: Number.isFinite(Number(item.time)) && Number(item.time) > 0 ? Number(item.time) : null,
    interval: Number.isFinite(Number(item.interval)) && Number(item.interval) > 0 ? Number(item.interval) : null,
    facts: record(item.summary_facts),
    raw: item,
  };
}

export async function listMonitorObjects(signal?: AbortSignal): Promise<MonitorObject[]> {
  const raw = unwrap<unknown>(await apiGet('/monitor/api/monitor_object/', { add_instance_count: true }, { signal }));
  return (Array.isArray(raw) ? raw : []).map((value) => {
    const item = record(value);
    const type = record(item.type_info);
    return {
      id: number(item.id), name: text(item.name), displayName: text(item.display_name || item.name),
      description: text(item.description), icon: text(item.icon), order: number(item.order),
      level: text(item.level), visible: item.is_visible !== false, instanceCount: number(item.instance_count),
      instanceIdKeys: texts(item.instance_id_keys),
      displayFields: (Array.isArray(item.display_fields) ? item.display_fields : [])
        .map((field) => {
          const meta = record(field);
          const type = text(meta.type || 'metric') === 'field' ? 'field' as const : 'metric' as const;
          return {
            key: text(meta.column_key || meta.fact),
            name: text(meta.name || meta.title || meta.column_key),
            type,
            order: number(meta.sort_order),
            metrics: (Array.isArray(meta.metrics) ? meta.metrics : []).map((binding) => {
              const ref = record(binding);
              return {
                plugin: text(ref.plugin),
                metric: text(ref.metric),
                field: text(ref.field),
              };
            }).filter((binding) => binding.metric),
          };
        })
        .filter((field) => field.key || field.metrics.length > 0)
        .sort((left, right) => left.order - right.order),
      type: {
        id: text(type.id || item.type),
        name: text(type.name || item.type),
        displayName: text(item.display_type || type.name || item.type),
        order: number(type.order),
      },
    };
  }).filter((item) => item.id && item.type.id && item.visible);
}

export async function listMonitorInstances(
  objectId: number,
  page: number,
  keyword = '',
  options?: { status?: readonly string[]; signal?: AbortSignal },
): Promise<PageResult<MonitorInstance>> {
  if (!objectId) throw new Error('objectId is required');
  // apiGet 不会展开嵌套对象；服务端认 vm_params[status] / vm_params.status。
  const params: Record<string, string | number | boolean> = {
    page,
    page_size: 20,
    name: keyword.trim(),
    add_metrics: true,
  };
  const statusFilters = normalizeReportingStatusFilters(options?.status);
  if (statusFilters.length === 1) {
    params['vm_params[status]'] = statusFilters[0];
  }
  const response = await apiGet(`/monitor/api/monitor_instance/${objectId}/list/`, params, { signal: options?.signal });
  const raw = record(unwrap<unknown>(response));
  const results = Array.isArray(raw.results) ? raw.results : [];
  return {
    count: number(raw.count),
    items: results.map(mapMonitorInstance).filter((item) => item.id),
  };
}

/** 复用现有 list，按 instance_id 精确取回单条实例的真实状态与上报时间。 */
export async function getMonitorInstance(
  objectId: number,
  instanceId: string,
  hints: { addMetrics?: boolean } = {},
  signal?: AbortSignal,
): Promise<MonitorInstance | null> {
  if (!objectId || !instanceId) return null;

  const response = await apiGet(`/monitor/api/monitor_instance/${objectId}/list/`, {
    page: 1,
    page_size: 1,
    instance_id: instanceId,
    add_metrics: hints.addMetrics ?? false,
  }, { signal });
  const raw = record(unwrap<unknown>(response));
  const results = Array.isArray(raw.results) ? raw.results : [];
  const mapped = results.map(mapMonitorInstance);
  // 混合版本部署时，旧 Server 可能忽略 instance_id 并返回分页第一条。
  // 先拒绝错配，再做有界分页精确回退，兼容只有 ID 的存量最近访问记录。
  const exact = mapped.find((item) => item.id === instanceId);
  if (exact || mapped.length === 0) return exact || null;

  const seenLegacyIds = new Set<string>();
  for (let page = 1; page <= LEGACY_INSTANCE_LOOKUP_MAX_PAGES; page += 1) {
    const fallbackResponse = await apiGet(`/monitor/api/monitor_instance/${objectId}/list/`, {
      page,
      page_size: LEGACY_INSTANCE_LOOKUP_PAGE_SIZE,
      add_metrics: hints.addMetrics ?? false,
    }, { signal });
    const fallbackRaw = record(unwrap<unknown>(fallbackResponse));
    const fallbackResults = Array.isArray(fallbackRaw.results) ? fallbackRaw.results : [];
    const fallbackItems = fallbackResults.map(mapMonitorInstance);
    const fallbackExact = fallbackItems.find((item) => item.id === instanceId);
    if (fallbackExact) return fallbackExact;

    const pageIds = fallbackItems.map((item) => item.id).filter(Boolean);
    if (page > 1 && pageIds.length > 0 && pageIds.every((id) => seenLegacyIds.has(id))) {
      throw new Error('Legacy Server instance lookup repeated a pagination page');
    }
    pageIds.forEach((id) => seenLegacyIds.add(id));

    const count = number(fallbackRaw.count);
    if (fallbackResults.length === 0 || page * LEGACY_INSTANCE_LOOKUP_PAGE_SIZE >= count) return null;
  }
  throw new Error('Legacy Server instance lookup exceeded the safe pagination limit');
}

export async function listEffectivePlugins(objectId: number, instanceId: string, signal?: AbortSignal): Promise<MonitorPlugin[]> {
  const raw = unwrap<unknown>(await apiGet(`/monitor/api/monitor_instance/${objectId}/effective_plugins/`, { instance_id: instanceId }, { signal }));
  return (Array.isArray(raw) ? raw : []).map((value) => {
    const item = record(value);
    return {
      id: number(item.id),
      name: text(item.name),
      displayName: text(item.display_name || item.name),
      isPre: Boolean(item.is_pre),
      isCustom: Boolean(item.is_custom),
      status: text(item.status),
    };
  }).filter((item) => item.id).sort((a, b) => Number(!a.isPre) - Number(!b.isPre) || Number(a.isCustom) - Number(b.isCustom));
}

/** 与 Web viewList 一致：按 display_fields 绑定的指标名拉取 unit（含枚举选项 JSON）。 */
export async function listDisplayFieldMetrics(
  objectId: number,
  metricNames: readonly string[],
  signal?: AbortSignal,
): Promise<Array<{ name: string; unit: string; pluginName: string }>> {
  const names = [...new Set(metricNames.map((name) => name.trim()).filter(Boolean))];
  if (!objectId || !names.length) return [];
  const raw = unwrap<unknown>(await apiGet('/monitor/api/metrics/', {
    monitor_object_id: objectId,
    name_in: names.join(','),
    page: 1,
    page_size: Math.max(names.length, 20),
  }, { signal }));
  const data = record(raw);
  const items = Array.isArray(raw) ? raw : (Array.isArray(data.items) ? data.items : []);
  return items.map((value) => {
    const item = record(value);
    return {
      name: text(item.name),
      unit: text(item.unit),
      pluginName: text(item.monitor_plugin_name),
    };
  }).filter((item) => item.name);
}

export async function listMetricDefinition(objectId: number, pluginId: number, signal?: AbortSignal) {
  const [groupRaw, metricRaw] = await Promise.all([
    apiGet('/monitor/api/metrics_group/', { monitor_object_id: objectId, monitor_plugin_id: pluginId }, { signal }),
    apiGet('/monitor/api/metrics/', { monitor_object_id: objectId, monitor_plugin_id: pluginId }, { signal }),
  ]);
  const groups: MetricGroup[] = monitorCatalogItems(unwrap<unknown>(groupRaw)).map((value) => { const item = record(value); return { id: number(item.id), name: text(item.name), displayName: text(item.display_name || item.name), order: number(item.sort_order) }; }).filter((item) => item.id);
  const metrics: MonitorMetric[] = monitorCatalogItems(unwrap<unknown>(metricRaw)).map((value) => { const item = record(value); return {
    id: number(item.id), groupId: number(item.metric_group), name: text(item.name), displayName: text(item.display_name || item.name), description: text(item.display_description),
    query: text(item.query), unit: text(item.unit), instanceIdKeys: texts(item.instance_id_keys), order: number(item.sort_order),
  }; }).filter((item) => item.id && item.query);
  return { groups: groups.sort((a, b) => a.order - b.order), metrics: metrics.sort((a, b) => a.order - b.order) };
}

export async function queryMetricRange(
  monitorObjectId: number,
  metricId: number,
  instanceId: string,
  unit: string,
  rangeMinutes: number,
  collectionInterval?: number | null,
  signal?: AbortSignal,
): Promise<MetricRangeResult> {
  const end = Date.now(); const start = end - rangeMinutes * 60_000;
  const step = Math.max(Math.ceil(((end - start) / 1000) / 100), collectionInterval || 0, 1);
  const raw = record(unwrap<unknown>(await apiPost('/monitor/api/metrics_instance/query_by_metric_range/', {
    monitor_object_id: monitorObjectId,
    metric_id: metricId,
    instance_ids: [instanceId],
    source_unit: unit,
    card_budget: true,
    start,
    end,
    step,
    ...(collectionInterval ? { detect_gaps: true, collection_interval: collectionInterval } : {}),
  }, { signal })));
  const data = record(raw.data);
  const source = Object.keys(data).length ? data : raw;
  const gaps = (Array.isArray(source.gaps) ? source.gaps : []).flatMap((value) => {
    const item = record(value);
    const gapStart = Number(item.start);
    const gapEnd = Number(item.end);
    if (!Number.isFinite(gapStart) || !Number.isFinite(gapEnd) || gapEnd < gapStart) return [];
    return [{
      start: gapStart,
      end: gapEnd,
      duration: Number.isFinite(Number(item.duration)) ? Number(item.duration) : gapEnd - gapStart,
      series: (Array.isArray(item.series) ? item.series : []).map((entry) => {
        const row = record(entry);
        return {
          metric: Object.fromEntries(Object.entries(record(row.metric)).map(([key, val]) => [key, text(val)])),
          missing_points: Number.isFinite(Number(row.missing_points)) ? Number(row.missing_points) : undefined,
        };
      }),
    }];
  });
  return {
    unit: text(source.unit || unit),
    startMs: start,
    endMs: end,
    gaps,
    series: (Array.isArray(source.result) ? source.result : []).map((value) => { const item = record(value); return {
      metric: Object.fromEntries(Object.entries(record(item.metric)).map(([key, val]) => [key, text(val)])),
      values: (Array.isArray(item.values) ? item.values : []).filter(Array.isArray).flatMap((point) => {
        const timestamp = Number(point[0]);
        if (!Number.isFinite(timestamp)) return [];
        return [[timestamp, point[1] === null || point[1] === undefined ? null : text(point[1])] as [number, string | null]];
      }),
    }; }),
  };
}

let monitorUnitListCache: MonitorUnitListItem[] | null = null;
let monitorUnitListPromise: Promise<MonitorUnitListItem[]> | null = null;

export async function getMonitorUnitList(signal?: AbortSignal): Promise<MonitorUnitListItem[]> {
  if (monitorUnitListCache) return monitorUnitListCache;
  if (!monitorUnitListPromise) {
    monitorUnitListPromise = apiGet('/monitor/api/unit/list/', {}, { signal })
      .then((raw) => {
        const list = Array.isArray(unwrap<unknown>(raw)) ? unwrap<unknown[]>(raw) : [];
        monitorUnitListCache = list.map((value) => {
          const item = record(value);
          return {
            unit_id: text(item.unit_id),
            display_unit: text(item.display_unit),
          };
        }).filter((item) => item.unit_id);
        return monitorUnitListCache;
      })
      .catch((error) => {
        monitorUnitListPromise = null;
        throw error;
      });
  }
  return monitorUnitListPromise;
}

export async function resolveRecentViews(
  config: MonitorRecentViewsConfig,
  objects: readonly MonitorObject[],
  signal?: AbortSignal,
): Promise<MonitorRecentViewsResolution> {
  const objectMap = new Map(objects.map((object) => [object.id, object]));
  const unitCache = new Map<number, Map<string, string>>();
  const loadUnits = async (object: MonitorObject) => {
    const cached = unitCache.get(object.id);
    if (cached) return cached;
    try {
      const metrics = await listDisplayFieldMetrics(object.id, displayFieldMetricNames(object), signal);
      const index = buildDisplayMetricUnitIndex(metrics);
      unitCache.set(object.id, index);
      return index;
    } catch {
      const empty = new Map<string, string>();
      unitCache.set(object.id, empty);
      return empty;
    }
  };
  const settled = await Promise.allSettled(config.items.map(async (item) => {
    const object = objectMap.get(item.objectId);
    if (!object) return null;
    const [instance, metricUnits] = await Promise.all([
      getMonitorInstance(item.objectId, item.instanceId, { addMetrics: true }, signal),
      loadUnits(object),
    ]);
    if (!instance) return null;
    return { item, object, instance, metricUnits };
  }));
  const entries = settled.flatMap((result) => (
    result.status === 'fulfilled' && result.value ? [result.value] : []
  ));
  const failedItems = settled.flatMap((result, index) => (
    result.status === 'rejected' ? [config.items[index]] : []
  ));
  return {
    entries,
    requestedCount: config.items.length,
    failedCount: failedItems.length,
    failedItems,
  };
}
