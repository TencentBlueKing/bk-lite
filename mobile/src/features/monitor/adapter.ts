import { apiGet, apiPost } from '@/api/request';
import type { MetricGroup, MetricRangeResult, MonitorInstance, MonitorMetric, MonitorObject, MonitorPlugin, PageResult } from './model';

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

export async function listMonitorInstances(objectId: number, page: number, keyword = '', signal?: AbortSignal): Promise<PageResult<MonitorInstance>> {
  if (!objectId) throw new Error('objectId is required');
  const params = { page, page_size: 20, name: keyword, add_metrics: true };
  const response = keyword
    ? await apiPost(`/monitor/api/monitor_instance/${objectId}/search/`, params, { signal })
    : await apiGet(`/monitor/api/monitor_instance/${objectId}/list/`, params, { signal });
  const raw = record(unwrap<unknown>(response));
  const results = Array.isArray(raw.results) ? raw.results : [];
  return {
    count: number(raw.count),
    items: results.map((value) => {
      const item = record(value);
      return {
        id: text(item.instance_id), name: text(item.instance_name || item.instance_id), idValues: texts(item.instance_id_values),
        status: text(item.status), lastReportedAt: Number.isFinite(Number(item.time)) && Number(item.time) > 0 ? Number(item.time) : null,
        interval: Number.isFinite(Number(item.interval)) && Number(item.interval) > 0 ? Number(item.interval) : null,
        facts: record(item.summary_facts), raw: item,
      };
    }).filter((item) => item.id),
  };
}

/** 复用现有 list，按 instance_id 取回单条实例的真实状态与上报时间。 */
export async function getMonitorInstance(
  objectId: number,
  instanceId: string,
  hints: { name?: string; idValues?: string[] } = {},
  signal?: AbortSignal,
): Promise<MonitorInstance | null> {
  if (!objectId || !instanceId) return null;
  const keywords = [hints.name, ...(hints.idValues || [])]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
  const tried = new Set<string>();
  for (const keyword of keywords.length ? keywords : ['']) {
    if (tried.has(keyword)) continue;
    tried.add(keyword);
    const response = await apiGet(`/monitor/api/monitor_instance/${objectId}/list/`, {
      page: 1,
      page_size: 50,
      name: keyword,
      add_metrics: false,
    }, { signal });
    const raw = record(unwrap<unknown>(response));
    const results = Array.isArray(raw.results) ? raw.results : [];
    const found = results.map((value) => {
      const item = record(value);
      return {
        id: text(item.instance_id), name: text(item.instance_name || item.instance_id), idValues: texts(item.instance_id_values),
        status: text(item.status), lastReportedAt: Number.isFinite(Number(item.time)) && Number(item.time) > 0 ? Number(item.time) : null,
        interval: Number.isFinite(Number(item.interval)) && Number(item.interval) > 0 ? Number(item.interval) : null,
        facts: record(item.summary_facts), raw: item,
      };
    }).find((item) => item.id === instanceId);
    if (found) return found;
  }
  return null;
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

export async function listMetricDefinition(objectId: number, pluginId: number, signal?: AbortSignal) {
  const [groupRaw, metricRaw] = await Promise.all([
    apiGet('/monitor/api/metrics_group/', { monitor_object_id: objectId, monitor_plugin_id: pluginId }, { signal }),
    apiGet('/monitor/api/metrics/', { monitor_object_id: objectId, monitor_plugin_id: pluginId }, { signal }),
  ]);
  const groups: MetricGroup[] = (Array.isArray(unwrap<unknown>(groupRaw)) ? unwrap<unknown[]>(groupRaw) : []).map((value) => { const item = record(value); return { id: number(item.id), name: text(item.name), displayName: text(item.display_name || item.name), order: number(item.sort_order) }; }).filter((item) => item.id);
  const metrics: MonitorMetric[] = (Array.isArray(unwrap<unknown>(metricRaw)) ? unwrap<unknown[]>(metricRaw) : []).map((value) => { const item = record(value); return {
    id: number(item.id), groupId: number(item.metric_group), name: text(item.name), displayName: text(item.display_name || item.name), description: text(item.display_description),
    query: text(item.view_query || item.query), unit: text(item.unit), instanceIdKeys: texts(item.instance_id_keys), order: number(item.sort_order),
  }; }).filter((item) => item.id && item.query);
  return { groups: groups.sort((a, b) => a.order - b.order), metrics: metrics.sort((a, b) => a.order - b.order) };
}

export async function queryMetricRange(query: string, unit: string, rangeMinutes: number, collectionInterval?: number | null, signal?: AbortSignal): Promise<MetricRangeResult> {
  const end = Date.now(); const start = end - rangeMinutes * 60_000;
  const step = Math.max(Math.ceil(((end - start) / 1000) / 100), collectionInterval || 0, 1);
  const raw = record(unwrap<unknown>(await apiGet('/monitor/api/metrics_instance/query_range/', {
    query, source_unit: unit, query_budget: 'card', start, end, step,
    ...(collectionInterval ? { detect_gaps: true, collection_interval: collectionInterval } : {}),
  }, { signal })));
  const data = record(raw.data);
  const source = Object.keys(data).length ? data : raw;
  return {
    unit: text(source.unit || unit),
    series: (Array.isArray(source.result) ? source.result : []).map((value) => { const item = record(value); return {
      metric: Object.fromEntries(Object.entries(record(item.metric)).map(([key, val]) => [key, text(val)])),
      values: (Array.isArray(item.values) ? item.values : []).filter(Array.isArray).map((point) => [Number(point[0]), text(point[1])] as [number, string]),
    }; }),
  };
}
