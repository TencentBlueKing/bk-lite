import { BusinessMetricItem } from './scriptMetricsParser';

export interface ScriptMetricCatalogDraft {
  metric_group?: number | null;
  unit?: Array<string | number> | string;
  description?: string;
}

export interface ScriptMetricRegisterPayload {
  monitor_object: number;
  monitor_plugin: number;
  metric_group: number;
  name: string;
  display_name: string;
  query: string;
  unit: string;
  data_type: 'Number';
  description: string;
  dimensions: Array<{ name: string; description: string }>;
}

export interface ScriptMetricCatalogUpdatePayload {
  metric_group: number;
  unit: string;
  description: string;
}

type TranslateFn = (
  key: string,
  defaultValue?: string,
  options?: Record<string, unknown>
) => string;

type RequestConfig = { suppressErrorNotification?: boolean };

export interface PersistScriptMetricsClient {
  get: (url: string, config?: { params?: Record<string, unknown> } & RequestConfig) => Promise<unknown>;
  post: (url: string, data?: unknown, config?: RequestConfig) => Promise<unknown>;
  patch: (url: string, data?: unknown, config?: RequestConfig) => Promise<unknown>;
  t: TranslateFn;
}

const SILENT_REQ = { suppressErrorNotification: true } as const;

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

export const extractCatalogItems = <T>(response: unknown): T[] => {
  if (Array.isArray(response)) {
    return response as T[];
  }
  const items = asRecord(response)?.items;
  return Array.isArray(items) ? (items as T[]) : [];
};

/** Cascader 叶子为 unit_id；已解析的字符串原样回传。 */
export const resolveCatalogUnitId = (unit: unknown): string => {
  if (Array.isArray(unit)) {
    if (!unit.length) {
      return '';
    }
    const leaf = unit[unit.length - 1];
    return leaf == null ? '' : String(leaf);
  }
  if (typeof unit === 'string') {
    return unit;
  }
  if (typeof unit === 'number' && Number.isFinite(unit)) {
    return String(unit);
  }
  return '';
};

export const resolveCatalogMetricGroupId = (
  metricGroup: unknown,
  fallbackGroupId: number
): number => {
  if (typeof metricGroup === 'number' && Number.isFinite(metricGroup) && metricGroup > 0) {
    return metricGroup;
  }
  if (typeof metricGroup === 'string' && /^\d+$/.test(metricGroup.trim())) {
    const parsed = Number(metricGroup.trim());
    return parsed > 0 ? parsed : fallbackGroupId;
  }
  return fallbackGroupId;
};

export const resolveCatalogDescription = (description: unknown): string =>
  typeof description === 'string' ? description : '';

export const applyCatalogDraft = (
  item: BusinessMetricItem,
  draft?: ScriptMetricCatalogDraft
): BusinessMetricItem => ({
  ...item,
  metric_group: draft?.metric_group ?? null,
  unit: resolveCatalogUnitId(draft?.unit),
  description: resolveCatalogDescription(draft?.description)
});

export const formatDimensionTagSummary = (
  tags?: Record<string, string>
): string =>
  Object.entries(tags || {})
    .map(([key, value]) => `${key}=${value}`)
    .join(' ');

/** 确认只落库勾选行，并带上分组 / 单位 / 描述。 */
export const pickSelectedBusinessMetrics = (
  items: BusinessMetricItem[],
  selected: Record<string, boolean>,
  catalogByKey: Record<string, ScriptMetricCatalogDraft> = {}
): BusinessMetricItem[] =>
  items
    .filter((item) => selected[item.key] !== false)
    .map((item) => applyCatalogDraft(item, catalogByKey[item.key]));

export const buildScriptMetricRegisterPayload = (
  item: BusinessMetricItem,
  targetObjectId: string | number,
  targetPluginId: string | number,
  fallbackGroupId: number
): ScriptMetricRegisterPayload => ({
  monitor_object: Number(targetObjectId),
  monitor_plugin: Number(targetPluginId),
  metric_group: resolveCatalogMetricGroupId(item.metric_group, fallbackGroupId),
  name: item.name,
  display_name: item.name,
  query: `${item.name}{__$labels__}`,
  unit: resolveCatalogUnitId(item.unit),
  data_type: 'Number',
  description: resolveCatalogDescription(item.description),
  dimensions: Object.keys(item.tags || {}).map((key) => ({
    name: key,
    description: key
  }))
});

export const buildScriptMetricCatalogUpdatePayload = (
  item: BusinessMetricItem,
  fallbackGroupId: number
): ScriptMetricCatalogUpdatePayload => ({
  metric_group: resolveCatalogMetricGroupId(item.metric_group, fallbackGroupId),
  unit: resolveCatalogUnitId(item.unit),
  description: resolveCatalogDescription(item.description)
});

const uniqueMetricsByName = (metrics: BusinessMetricItem[]): BusinessMetricItem[] => {
  const seen = new Set<string>();
  const unique: BusinessMetricItem[] = [];
  metrics.forEach((item) => {
    if (!item?.name || seen.has(item.name)) {
      return;
    }
    seen.add(item.name);
    unique.push(item);
  });
  return unique;
};

const readErrorMessage = (error: unknown, t: TranslateFn): string => {
  const record = asRecord(error);
  const response = asRecord(record?.response);
  const data = asRecord(response?.data);
  const message =
    (typeof data?.message === 'string' && data.message) ||
    (typeof record?.message === 'string' && record.message) ||
    t('common.operationFailed');
  return message;
};

export const persistScriptMetrics = async ({
  pluginId,
  objectId,
  metrics,
  client
}: {
  pluginId: string | number;
  objectId: string | number;
  metrics: BusinessMetricItem[];
  client: PersistScriptMetricsClient;
}): Promise<void> => {
  if (!metrics.length) {
    return;
  }
  const { get, post, patch, t } = client;
  try {
    const groupRes = await get('/monitor/api/metrics_group/', {
      params: {
        monitor_object_id: objectId,
        monitor_plugin_id: pluginId,
        page: 1,
        page_size: 100
      },
      ...SILENT_REQ
    });
    const groups = extractCatalogItems<{ id?: number }>(groupRes);
    let fallbackGroupId = groups[0]?.id;
    if (!fallbackGroupId) {
      const createdGroup = asRecord(
        await post(
          '/monitor/api/metrics_group/',
          {
            monitor_object: Number(objectId),
            monitor_plugin: Number(pluginId),
            name: 'Base',
            description: '基础指标'
          },
          SILENT_REQ
        )
      );
      fallbackGroupId =
        typeof createdGroup?.id === 'number' ? createdGroup.id : Number(createdGroup?.id);
    }
    if (!fallbackGroupId) {
      throw new Error(t('common.operationFailed'));
    }

    const existingRes = await get('/monitor/api/metrics/', {
      params: {
        monitor_object_id: objectId,
        monitor_plugin_id: pluginId,
        page: 1,
        page_size: 100
      },
      ...SILENT_REQ
    });
    const existingByName = new Map<string, number>();
    extractCatalogItems<{ id?: number; name?: string }>(existingRes).forEach((item) => {
      if (item?.name && typeof item.id === 'number' && !existingByName.has(item.name)) {
        existingByName.set(item.name, item.id);
      }
    });

    const uniqueMetrics = uniqueMetricsByName(metrics);
    if (!uniqueMetrics.length) {
      return;
    }

    const results = await Promise.allSettled(
      uniqueMetrics.map((item) => {
        const existingId = existingByName.get(item.name);
        if (existingId) {
          return patch(
            `/monitor/api/metrics/${existingId}/`,
            buildScriptMetricCatalogUpdatePayload(item, fallbackGroupId),
            SILENT_REQ
          );
        }
        return post(
          '/monitor/api/metrics/',
          buildScriptMetricRegisterPayload(item, objectId, pluginId, fallbackGroupId),
          SILENT_REQ
        );
      })
    );
    const rejected = results.find(
      (result): result is PromiseRejectedResult => result.status === 'rejected'
    );
    if (rejected) {
      throw rejected.reason;
    }
  } catch (error: unknown) {
    throw new Error(
      t(
        'monitor.integrations.scriptMetricsPersistFailed',
        '指标保存失败：{error}',
        {
          error: readErrorMessage(error, t)
        }
      )
    );
  }
};
