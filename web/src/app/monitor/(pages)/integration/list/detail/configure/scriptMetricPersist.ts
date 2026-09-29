import {
  BusinessMetricItem,
  cleanDisplayTags,
  cleanMeasurementName,
  collectReservedScriptTagKeys,
  isHiddenPlatformDimensionKey,
  isReservedScriptTagKey,
  isSelfMetricName
} from './scriptMetricsParser';

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

interface TranslateFn {
  (
    key: string,
    defaultValue?: string,
    options?: Record<string, unknown>
  ): string;
}

interface RequestConfig {
  suppressErrorNotification?: boolean;
}

export interface PersistScriptMetricsClient {
  get: (url: string, config?: { params?: Record<string, unknown> } & RequestConfig) => Promise<unknown>;
  post: (url: string, data?: unknown, config?: RequestConfig) => Promise<unknown>;
  patch: (url: string, data?: unknown, config?: RequestConfig) => Promise<unknown>;
  del?: (url: string, config?: RequestConfig) => Promise<unknown>;
  t: TranslateFn;
}

export interface CatalogMetricRef {
  id: number;
  name: string;
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

/** 目录已有的无单位叶子，Confirm / 去编辑必须回传 unit_id 而不是展示文案。 */
export const DEFAULT_CATALOG_UNIT_ID = 'none';
/** 目录默认分组名，优先复用已有「无分组」/ Default / Base。 */
export const DEFAULT_CATALOG_GROUP_NAMES = ['无分组', 'Default', 'default', 'Base'];

export interface CatalogMetricGroupOption {
  id?: number;
  name?: string;
  display_name?: string;
}

export const catalogGroupLabel = (group?: CatalogMetricGroupOption | null): string =>
  String(group?.display_name || group?.name || '').trim();

export const resolveDefaultCatalogGroupId = (
  groups: CatalogMetricGroupOption[] = []
): number | null => {
  const valid = groups.filter(
    (group): group is CatalogMetricGroupOption & { id: number } =>
      typeof group.id === 'number' && Number.isFinite(group.id) && group.id > 0
  );
  if (!valid.length) {
    return null;
  }
  for (const name of DEFAULT_CATALOG_GROUP_NAMES) {
    const target = name.toLowerCase();
    const matched = valid.find(
      (group) => catalogGroupLabel(group).toLowerCase() === target
    );
    if (matched) {
      return matched.id;
    }
  }
  return valid[0].id;
};

export const resolveDefaultCatalogUnitPath = (
  options: Array<{ value?: string; children?: Array<{ value: string }> }> = [],
  unitId: string = DEFAULT_CATALOG_UNIT_ID
): string[] | undefined => {
  for (const group of options) {
    const children = group.children || [];
    if (!children.length && group.value && String(group.value) === unitId) {
      return [String(group.value)];
    }
    const child = children.find((item) => item.value === unitId);
    if (child && group.value) {
      return [String(group.value), String(child.value)];
    }
  }
  return undefined;
};

export const resolvePersistCatalogUnitId = (unit: unknown): string =>
  resolveCatalogUnitId(unit) || DEFAULT_CATALOG_UNIT_ID;

export const createCatalogMetricGroup = async ({
  post,
  objectId,
  pluginId,
  name
}: {
  post: PersistScriptMetricsClient['post'];
  objectId: string | number;
  pluginId: string | number;
  name: string;
}): Promise<CatalogMetricGroupOption & { id: number }> => {
  const trimmed = String(name || '').trim();
  if (!trimmed) {
    throw new Error('group name required');
  }
  const created = asRecord(
    await post(
      '/monitor/api/metrics_group/',
      {
        monitor_object: Number(objectId),
        monitor_plugin: Number(pluginId),
        name: trimmed
      },
      SILENT_REQ
    )
  );
  const id = typeof created?.id === 'number' ? created.id : Number(created?.id);
  if (!id) {
    throw new Error('group create failed');
  }
  return {
    id,
    name: String(created?.name || trimmed),
    display_name: String(created?.display_name || created?.name || trimmed)
  };
};

export interface ScriptUnitCascaderOption {
  label: string;
  value: string;
  searchText?: string;
  children?: ScriptUnitCascaderOption[];
}

const PERCENT_UNIT_IDS = new Set(['percent', 'percentunit']);

/**
 * 表格单位下拉用短名（如 W），避免「Other / Watts (W)」撑满窄列。
 * percent / percentunit 保留量纲区分；none 保持目录原名。
 */
export const shortenScriptUnitLabel = (item: {
  unitId: string;
  label?: string;
  displayUnit?: string;
}): string => {
  const unitId = String(item.unitId || '').trim();
  const label = String(item.label || '').trim();
  const displayUnit = String(item.displayUnit || '').trim();
  if (!unitId || unitId === DEFAULT_CATALOG_UNIT_ID) {
    return label || DEFAULT_CATALOG_UNIT_ID;
  }
  if (PERCENT_UNIT_IDS.has(unitId)) {
    return label || unitId;
  }
  if (displayUnit) {
    return displayUnit;
  }
  const wrapped = label.match(/\(([^)]+)\)\s*$/);
  if (wrapped?.[1]?.trim()) {
    return wrapped[1].trim();
  }
  return label || unitId;
};

/** Cascader 分组用类目名，叶子 value 必须是 unit_id。展示名缩短，none 钉在最前。 */
export const buildUnitCascaderOptions = (
  grouped: Array<{
    label?: string;
    children?: Array<{
      label?: string;
      value?: string;
      unit_id?: string;
      unit?: string;
      display_unit?: string;
    }>;
  }> = []
): ScriptUnitCascaderOption[] => {
  let noneOption: ScriptUnitCascaderOption | null = null;
  const groups: ScriptUnitCascaderOption[] = [];
  grouped.forEach((group) => {
    const children: ScriptUnitCascaderOption[] = [];
    (group.children || []).forEach((item) => {
      const unitId = String(item.unit_id || item.value || '').trim();
      if (!unitId) return;
      const rawLabel = String(item.label || '').trim();
      const displayUnit = String(item.unit || item.display_unit || '').trim();
      const option: ScriptUnitCascaderOption = {
        label: shortenScriptUnitLabel({
          unitId,
          label: rawLabel,
          displayUnit
        }),
        value: unitId,
        searchText: [rawLabel, displayUnit, unitId, group.label]
          .filter(Boolean)
          .join(' ')
      };
      if (unitId === DEFAULT_CATALOG_UNIT_ID) {
        noneOption = option;
        return;
      }
      children.push(option);
    });
    if (children.length && group.label) {
      groups.push({
        label: String(group.label),
        value: String(group.label),
        searchText: String(group.label),
        children
      });
    }
  });
  return noneOption ? [noneOption, ...groups] : groups;
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
  reservedTagKeys: item.reservedTagKeys || collectReservedScriptTagKeys(item.tags),
  metric_group: draft?.metric_group ?? null,
  unit: resolveCatalogUnitId(draft?.unit),
  description: resolveCatalogDescription(draft?.description)
});

export const collectReservedTagViolations = (
  metrics: BusinessMetricItem[]
): string[] => {
  const found: string[] = [];
  const mark = (key: string) => {
    if (key && !found.includes(key)) {
      found.push(key);
    }
  };
  metrics.forEach((item) => {
    (item.reservedTagKeys || []).forEach(mark);
    Object.keys(item.tags || {}).forEach((key) => {
      if (isHiddenPlatformDimensionKey(key)) {
        return;
      }
      if (isReservedScriptTagKey(key)) {
        mark(key);
      }
    });
  });
  return found;
};

export const formatReservedTagRenameMessage = (
  keys: string[],
  t: TranslateFn
): string => {
  const uniqueKeys = keys.filter(Boolean);
  const rename = t('monitor.integrations.reservedTagRename', '保留字段，请换名');
  if (!uniqueKeys.length) {
    return rename;
  }
  const joined = uniqueKeys.join(', ');
  const detailed = t(
    'monitor.integrations.reservedTagRenameDetail',
    '保留字段，请换名：{keys}',
    { keys: joined }
  );
  return detailed.includes('{keys}') ? `${rename}：${joined}` : detailed;
};

export const formatDimensionTagSummary = (
  tags?: Record<string, string>
): string =>
  Object.entries(cleanDisplayTags(tags) || {})
    .map(([key, value]) => `${key}=${value}`)
    .join(' ');

const toStdoutMetricName = (name: string): string =>
  cleanMeasurementName(String(name || '').trim());

/** 确认只落库勾选的业务指标，并带上分组 / 单位 / 描述。自监控指标不可勾选。 */
export const pickSelectedBusinessMetrics = (
  items: BusinessMetricItem[],
  selected: Record<string, boolean>,
  catalogByKey: Record<string, ScriptMetricCatalogDraft> = {}
): BusinessMetricItem[] =>
  items
    .filter((item) => !isSelfMetricName(item.name))
    .filter((item) => selected[item.key] !== false)
    .map((item) =>
      applyCatalogDraft(
        { ...item, name: toStdoutMetricName(item.name) },
        catalogByKey[item.key]
      )
    );

/** 重新调试：刷新采样值，保留仍存在指标的勾选/分组/单位/描述，消失的视为未勾选。 */
export const mergeRetainedTrialMetricState = ({
  nextMetrics,
  prevSelected,
  prevCatalog
}: {
  nextMetrics: BusinessMetricItem[];
  prevSelected: Record<string, boolean>;
  prevCatalog: Record<string, ScriptMetricCatalogDraft>;
}): {
  selected: Record<string, boolean>;
  catalog: Record<string, ScriptMetricCatalogDraft>;
} => {
  const selected: Record<string, boolean> = {};
  const catalog: Record<string, ScriptMetricCatalogDraft> = {};
  nextMetrics.forEach((item) => {
    if (!item?.key || isSelfMetricName(item.name)) {
      return;
    }
    selected[item.key] = Object.prototype.hasOwnProperty.call(
      prevSelected,
      item.key
    )
      ? Boolean(prevSelected[item.key])
      : true;
    if (prevCatalog[item.key]) {
      catalog[item.key] = { ...prevCatalog[item.key] };
    }
  });
  return { selected, catalog };
};

export const excludeSelfMonitorMetrics = (
  metrics: BusinessMetricItem[]
): BusinessMetricItem[] =>
  metrics.filter((item) => item?.name && !isSelfMetricName(item.name));

export const applyDefaultCatalogDrafts = (
  metrics: BusinessMetricItem[],
  catalogByKey: Record<string, ScriptMetricCatalogDraft>,
  defaultGroupId?: number | null,
  defaultUnitPath?: string[]
): { catalog: Record<string, ScriptMetricCatalogDraft>; changed: boolean } => {
  const next = { ...catalogByKey };
  let changed = false;
  metrics.forEach((item) => {
    if (!item?.key || isSelfMetricName(item.name)) {
      return;
    }
    const draft = { ...(next[item.key] || {}) };
    let patched = false;
    if (draft.metric_group == null && defaultGroupId) {
      draft.metric_group = defaultGroupId;
      patched = true;
    }
    if (
      (draft.unit == null || (Array.isArray(draft.unit) && !draft.unit.length)) &&
      defaultUnitPath
    ) {
      draft.unit = defaultUnitPath;
      patched = true;
    }
    if (patched) {
      next[item.key] = draft;
      changed = true;
    }
  });
  return { catalog: changed ? next : catalogByKey, changed };
};

export const applyStdoutMetricNames = (
  metrics: BusinessMetricItem[]
): BusinessMetricItem[] =>
  excludeSelfMonitorMetrics(metrics).map((item) => ({
    ...item,
    name: toStdoutMetricName(item.name)
  }));

export const CATALOG_METRIC_PAGE_SIZE = 100;

const toCatalogMetricRefs = (
  items: Array<{ id?: number; name?: string }>
): CatalogMetricRef[] => {
  const refs: CatalogMetricRef[] = [];
  items.forEach((item) => {
    if (item?.name && typeof item.id === 'number') {
      refs.push({ id: item.id, name: item.name });
    }
  });
  return refs;
};

export const listPluginCatalogMetrics = async ({
  pluginId,
  objectId,
  client
}: {
  pluginId: string | number;
  objectId: string | number;
  client: Pick<PersistScriptMetricsClient, 'get'>;
}): Promise<CatalogMetricRef[]> => {
  const pageSize = CATALOG_METRIC_PAGE_SIZE;
  const refs: CatalogMetricRef[] = [];
  let page = 1;
  while (true) {
    const existingRes = await client.get('/monitor/api/metrics/', {
      params: {
        monitor_object_id: objectId,
        monitor_plugin_id: pluginId,
        page,
        page_size: pageSize
      },
      ...SILENT_REQ
    });
    if (Array.isArray(existingRes) && page === 1) {
      return toCatalogMetricRefs(
        existingRes as Array<{ id?: number; name?: string }>
      );
    }
    const batch = extractCatalogItems<{ id?: number; name?: string }>(
      existingRes
    );
    refs.push(...toCatalogMetricRefs(batch));
    const countRaw = asRecord(existingRes)?.count;
    if (!batch.length || batch.length < pageSize) {
      break;
    }
    if (typeof countRaw === 'number' && refs.length >= countRaw) {
      break;
    }
    page += 1;
  }
  return refs;
};

/** 硬覆盖：删除当前勾选集合之外的旧业务指标，永不删除自监控。 */
export const planScriptMetricHardSyncDeletes = (
  existing: CatalogMetricRef[],
  checked: BusinessMetricItem[]
): CatalogMetricRef[] => {
  const keep = new Set(
    applyStdoutMetricNames(checked)
      .map((item) => item.name)
      .filter(Boolean)
  );
  return existing.filter((item) => {
    if (!item?.name || typeof item.id !== 'number') {
      return false;
    }
    if (isSelfMetricName(item.name)) {
      return false;
    }
    return !keep.has(item.name);
  });
};

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
  unit: resolvePersistCatalogUnitId(item.unit),
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
  unit: resolvePersistCatalogUnitId(item.unit),
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
  client,
  staleDeletes = []
}: {
  pluginId: string | number;
  objectId: string | number;
  metrics: BusinessMetricItem[];
  client: PersistScriptMetricsClient;
  staleDeletes?: CatalogMetricRef[];
}): Promise<void> => {
  const persistableMetrics = applyStdoutMetricNames(metrics);
  if (!persistableMetrics.length && !staleDeletes.length) {
    return;
  }
  const { get, post, patch, del, t } = client;
  const reservedKeys = collectReservedTagViolations(persistableMetrics);
  if (reservedKeys.length) {
    throw new Error(formatReservedTagRenameMessage(reservedKeys, t));
  }
  try {
    const deletable = staleDeletes.filter(
      (item) => item?.id && item?.name && !isSelfMetricName(item.name)
    );
    if (deletable.length) {
      if (!del) {
        throw new Error(t('common.operationFailed'));
      }
      const deleteResults = await Promise.allSettled(
        deletable.map((item) =>
          del(`/monitor/api/metrics/${item.id}/`, SILENT_REQ)
        )
      );
      const deleteRejected = deleteResults.find(
        (result): result is PromiseRejectedResult => result.status === 'rejected'
      );
      if (deleteRejected) {
        throw deleteRejected.reason;
      }
    }

    if (!persistableMetrics.length) {
      return;
    }

    const groupRes = await get('/monitor/api/metrics_group/', {
      params: {
        monitor_object_id: objectId,
        monitor_plugin_id: pluginId,
        page: 1,
        page_size: 100
      },
      ...SILENT_REQ
    });
    const groups = extractCatalogItems<CatalogMetricGroupOption>(groupRes);
    let fallbackGroupId = resolveDefaultCatalogGroupId(groups) ?? undefined;
    if (!fallbackGroupId) {
      fallbackGroupId = (
        await createCatalogMetricGroup({
          post,
          objectId,
          pluginId,
          name: 'Base'
        })
      ).id;
    }
    if (!fallbackGroupId) {
      throw new Error(t('common.operationFailed'));
    }

    const existing = await listPluginCatalogMetrics({
      pluginId,
      objectId,
      client
    });
    const existingByName = new Map<string, number>();
    existing.forEach((item) => {
      if (!existingByName.has(item.name)) {
        existingByName.set(item.name, item.id);
      }
    });

    const uniqueMetrics = uniqueMetricsByName(persistableMetrics);
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
