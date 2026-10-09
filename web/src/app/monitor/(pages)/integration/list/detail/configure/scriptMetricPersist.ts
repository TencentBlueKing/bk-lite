import {
  BusinessMetricItem,
  cleanMeasurementName,
  collectReservedScriptTagKeys,
  isHiddenPlatformDimensionKey,
  isReservedScriptMetricId,
  isReservedScriptTagKey,
  isSelfMetricName,
  keepStoredTags
} from './scriptMetricsParser';

export type ScriptMetricPersistMode = 'add' | 'overwrite';
export const SCRIPT_METRIC_PERSIST_MODE_ADD: ScriptMetricPersistMode = 'add';
export const SCRIPT_METRIC_PERSIST_MODE_OVERWRITE: ScriptMetricPersistMode =
  'overwrite';

export interface ScriptMetricCatalogDraft {
  metric_group?: number | null;
  unit?: Array<string | number> | string;
  description?: string;
  data_type?: string;
  editedGroup?: boolean;
  editedUnit?: boolean;
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
  metric_group?: number;
  unit?: string;
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
  t: TranslateFn;
}

export interface CatalogMetricRef {
  id: number;
  name: string;
  display_name?: string;
  metric_group?: number | null;
  unit?: string;
  data_type?: string;
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

/** 目录已有的无单位叶子，确认写入必须回传 unit_id 而不是展示文案。 */
export const DEFAULT_CATALOG_UNIT_ID = 'none';
/** 目录默认分组名，优先复用已有「无分组」/ Default / Base。 */
export const DEFAULT_CATALOG_GROUP_NAMES = ['无分组', 'Default', 'default', 'Base'];

export interface CatalogMetricGroupOption {
  id?: number;
  name?: string;
  display_name?: string;
  monitor_plugin?: string | number | null;
  is_pre?: boolean;
}

export const catalogGroupLabel = (group?: CatalogMetricGroupOption | null): string =>
  String(group?.display_name || group?.name || '').trim();

/** 同名分组只保留一条：当前插件优先，其次是本页指标正在引用的 id。 */
export const dedupeCatalogMetricGroups = <T extends CatalogMetricGroupOption>(
  groups: T[] = [],
  options?: {
    preferredPluginId?: string | number | null;
    preferredIds?: Array<string | number | null | undefined>;
  }
): { groups: T[]; idAlias: Map<string, string> } => {
  const preferredPlugin =
    options?.preferredPluginId != null && String(options.preferredPluginId) !== ''
      ? String(options.preferredPluginId)
      : '';
  const preferredIds = new Set(
    (options?.preferredIds || [])
      .filter((id) => id != null && String(id) !== '')
      .map((id) => String(id))
  );
  const idAlias = new Map<string, string>();
  const kept = new Map<string, T>();

  const rank = (group: CatalogMetricGroupOption) => {
    const pluginId =
      group.monitor_plugin != null ? String(group.monitor_plugin) : '';
    if (preferredPlugin && pluginId === preferredPlugin) return 0;
    const id = group.id != null ? String(group.id) : '';
    if (id && preferredIds.has(id)) return 1;
    return 2;
  };

  const retarget = (fromId: string, toId: string) => {
    if (!fromId || fromId === toId) return;
    idAlias.set(fromId, toId);
    idAlias.forEach((target, source) => {
      if (target === fromId) idAlias.set(source, toId);
    });
  };

  groups.forEach((group) => {
    const idNum = typeof group.id === 'number' ? group.id : Number(group.id);
    if (!Number.isFinite(idNum) || idNum <= 0) return;
    const id = String(idNum);
    const nameKey = String(group.name || catalogGroupLabel(group) || '')
      .trim()
      .toLowerCase();
    const key = nameKey || `id:${id}`;
    const normalized = { ...group, id: idNum } as T;
    const current = kept.get(key);
    if (!current) {
      kept.set(key, normalized);
      return;
    }
    const currentId = String(current.id);
    if (rank(normalized) < rank(current)) {
      kept.set(key, normalized);
      retarget(currentId, id);
      return;
    }
    if (currentId !== id) retarget(id, currentId);
  });

  return { groups: Array.from(kept.values()), idAlias };
};

export const canonicalCatalogGroupId = (
  groupId: unknown,
  idAlias: Map<string, string>
): number | null => {
  const raw = groupId != null ? String(groupId) : '';
  if (!raw) return null;
  const resolved = idAlias.get(raw) || raw;
  const numeric = Number(resolved);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
};

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

/** 按指标 ID 后缀猜测目录单位；与指标页同一套 unit_id。 */
export const guessCatalogUnitId = (metricName: string): string => {
  const lower = String(metricName || '').toLowerCase();
  if (lower.endsWith('_bytes')) {
    return 'bytes';
  }
  if (lower.endsWith('_percent') || lower.endsWith('_pct')) {
    return 'percent';
  }
  if (lower.endsWith('_seconds')) {
    return 's';
  }
  if (lower.endsWith('_ms')) {
    return 'ms';
  }
  return DEFAULT_CATALOG_UNIT_ID;
};

export const resolveGuessedCatalogUnitPath = (
  metricName: string,
  options: Array<{ value?: string; children?: Array<{ value: string }> }> = []
): string[] | undefined => {
  const guessed = guessCatalogUnitId(metricName);
  return (
    resolveDefaultCatalogUnitPath(options, guessed) ||
    resolveDefaultCatalogUnitPath(options, DEFAULT_CATALOG_UNIT_ID)
  );
};

/** 调试采样一律按指标页「数字」类型落库。 */
export const inferCatalogDataType = (): ScriptMetricRegisterPayload['data_type'] =>
  'Number';

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
    display_name: String(created?.display_name || created?.name || trimmed),
    monitor_plugin:
      (created?.monitor_plugin as string | number | null | undefined) ??
      Number(pluginId),
    is_pre: false
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
  description: resolveCatalogDescription(draft?.description),
  data_type: draft?.data_type || item.data_type,
  editedGroup: Boolean(draft?.editedGroup),
  editedUnit: Boolean(draft?.editedUnit)
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

export const collectReservedMetricIdViolations = (
  metrics: BusinessMetricItem[]
): string[] => {
  const found: string[] = [];
  metrics.forEach((item) => {
    const name = cleanMeasurementName(String(item?.name || '').trim());
    if (name && isReservedScriptMetricId(name) && !found.includes(name)) {
      found.push(name);
    }
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

export const formatReservedMetricIdMessage = (
  keys: string[],
  t: TranslateFn
): string => {
  const uniqueKeys = keys.filter(Boolean);
  const rename = t(
    'monitor.integrations.reservedMetricId',
    '指标 ID 与保留字段冲突，请更换'
  );
  if (!uniqueKeys.length) {
    return rename;
  }
  const joined = uniqueKeys.join(', ');
  const detailed = t(
    'monitor.integrations.reservedMetricIdDetail',
    '指标 ID 与保留字段冲突：{keys}',
    { keys: joined }
  );
  return detailed.includes('{keys}') ? `${rename}：${joined}` : detailed;
};

const toStdoutMetricName = (name: string): string =>
  cleanMeasurementName(String(name || '').trim());

const collectStoredDimensionNames = (item: BusinessMetricItem): string[] => {
  const names: string[] = [];
  const add = (tags?: Record<string, string>) => {
    Object.keys(keepStoredTags(tags) || {}).forEach((key) => {
      if (!names.includes(key)) {
        names.push(key);
      }
    });
  };
  add(item.tags);
  item.samples?.forEach((sample) => add(sample.tags));
  return names;
};

/** 确认只落库勾选的业务指标（按短名一行），并带上分组 / 单位 / 描述。自监控指标不可勾选。 */
export const pickSelectedBusinessMetrics = (
  items: BusinessMetricItem[],
  selected: Record<string, boolean>,
  catalogByKey: Record<string, ScriptMetricCatalogDraft> = {}
): BusinessMetricItem[] =>
  items
    .filter((item) => !isSelfMetricName(item.name))
    .filter((item) => !isReservedScriptMetricId(item.name))
    .filter((item) => selected[item.key] !== false)
    .map((item) =>
      applyCatalogDraft(
        { ...item, name: toStdoutMetricName(item.name) },
        catalogByKey[item.key]
      )
    );

/** 重新调试：按指标短名刷新采样值，保留仍存在指标的勾选/分组/单位/描述，消失的视为未勾选。 */
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
    selected[item.key] = isReservedScriptMetricId(item.name)
      ? false
      : Object.prototype.hasOwnProperty.call(prevSelected, item.key)
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

const isCatalogEnumType = (dataType?: string): boolean =>
  String(dataType || '').toLowerCase() === 'enum';

const sameCatalogUnit = (
  current: ScriptMetricCatalogDraft['unit'],
  nextPath: string[]
): boolean => {
  if (!Array.isArray(current) || current.length !== nextPath.length) {
    return false;
  }
  return current.every((part, index) => String(part) === nextPath[index]);
};

export const applyDefaultCatalogDrafts = (
  metrics: BusinessMetricItem[],
  catalogByKey: Record<string, ScriptMetricCatalogDraft>,
  defaultGroupId?: number | null,
  unitOptions: Array<{ value?: string; children?: Array<{ value: string }> }> = [],
  existingByName: Map<string, CatalogMetricRef> = new Map()
): { catalog: Record<string, ScriptMetricCatalogDraft>; changed: boolean } => {
  const next = { ...catalogByKey };
  let changed = false;
  metrics.forEach((item) => {
    if (!item?.key || isSelfMetricName(item.name)) {
      return;
    }
    const existing = existingByName.get(toStdoutMetricName(item.name));
    const draft = { ...(next[item.key] || {}) };
    let patched = false;
    if (existing) {
      if (existing.data_type && draft.data_type !== existing.data_type) {
        draft.data_type = existing.data_type;
        patched = true;
      }
      if (!draft.editedGroup && existing.metric_group) {
        const groupId = Number(existing.metric_group);
        if (Number.isFinite(groupId) && groupId > 0 && draft.metric_group !== groupId) {
          draft.metric_group = groupId;
          patched = true;
        }
      }
      if (!draft.editedUnit) {
        if (isCatalogEnumType(existing.data_type)) {
          if (draft.unit != null) {
            draft.unit = undefined;
            patched = true;
          }
        } else {
          const unitId = String(existing.unit || '').trim() || DEFAULT_CATALOG_UNIT_ID;
          const catalogPath = resolveDefaultCatalogUnitPath(unitOptions, unitId);
          if (catalogPath && !sameCatalogUnit(draft.unit, catalogPath)) {
            draft.unit = catalogPath;
            patched = true;
          }
        }
      }
    } else {
      if (draft.metric_group == null && defaultGroupId) {
        draft.metric_group = defaultGroupId;
        patched = true;
      }
      if (
        !draft.editedUnit &&
        (draft.unit == null || (Array.isArray(draft.unit) && !draft.unit.length))
      ) {
        const guessedPath = resolveGuessedCatalogUnitPath(item.name, unitOptions);
        if (guessedPath) {
          draft.unit = guessedPath;
          patched = true;
        }
      }
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
/** 与后端 `METRIC_BATCH_UPDATE_MAX_SIZE` 对齐。 */
export const METRIC_BATCH_UPDATE_MAX_SIZE = 100;

const toCatalogMetricRefs = (
  items: Array<{
    id?: number;
    name?: string;
    display_name?: string;
    metric_group?: number | string | null;
    unit?: string;
    data_type?: string;
  }>
): CatalogMetricRef[] => {
  const refs: CatalogMetricRef[] = [];
  items.forEach((item) => {
    if (item?.name && typeof item.id === 'number') {
      const displayName = String(item.display_name || '').trim();
      const groupId = Number(item.metric_group);
      refs.push({
        id: item.id,
        name: item.name,
        ...(displayName ? { display_name: displayName } : {}),
        ...(Number.isFinite(groupId) && groupId > 0
          ? { metric_group: groupId }
          : {}),
        ...(typeof item.unit === 'string' ? { unit: item.unit } : {}),
        ...(typeof item.data_type === 'string'
          ? { data_type: item.data_type }
          : {})
      });
    }
  });
  return refs;
};

export const catalogMetricsByName = (
  refs: CatalogMetricRef[]
): Map<string, CatalogMetricRef> => {
  const map = new Map<string, CatalogMetricRef>();
  refs.forEach((item) => {
    const name = String(item.name || '').trim();
    if (name && !map.has(name)) {
      map.set(name, item);
    }
  });
  return map;
};

export const catalogMetricRefLabel = (item: CatalogMetricRef): string => {
  const displayName = String(item.display_name || '').trim();
  const name = String(item.name || '').trim();
  if (displayName && name && displayName !== name) {
    return `${displayName} (${name})`;
  }
  return displayName || name;
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

export const findDuplicateDisplayNames = (
  metrics: Array<{ name?: string; display_name?: string }>,
  existing: CatalogMetricRef[] = []
): string[] => {
  const existingByDisplay = new Map<string, string>();
  existing.forEach((item) => {
    const metricId = String(item.name || '').trim();
    const label = String(item.display_name || item.name || '')
      .trim()
      .toLowerCase();
    if (label && metricId && !existingByDisplay.has(label)) {
      existingByDisplay.set(label, metricId);
    }
  });
  const found: string[] = [];
  const seenInBatch = new Map<string, string>();
  metrics.forEach((item) => {
    const metricId = String(item.name || '').trim();
    const display = String(item.display_name || item.name || '').trim();
    if (!display || !metricId) {
      return;
    }
    const key = display.toLowerCase();
    const existingName = existingByDisplay.get(key);
    if (existingName && existingName !== metricId && !found.includes(display)) {
      found.push(display);
    }
    const batchName = seenInBatch.get(key);
    if (batchName && batchName !== metricId && !found.includes(display)) {
      found.push(display);
    }
    if (!seenInBatch.has(key)) {
      seenInBatch.set(key, metricId);
    }
  });
  return found;
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
  data_type: inferCatalogDataType(),
  description: resolveCatalogDescription(item.description),
  dimensions: collectStoredDimensionNames(item).map((key) => ({
    name: key,
    description: key
  }))
});

export const buildScriptMetricCatalogUpdatePayload = (
  item: BusinessMetricItem,
  existing?: CatalogMetricRef | null
): ScriptMetricCatalogUpdatePayload | null => {
  const payload: ScriptMetricCatalogUpdatePayload = {};
  const nextGroup = resolveCatalogMetricGroupId(item.metric_group, 0);
  const existingGroup = Number(existing?.metric_group);
  if (
    item.editedGroup &&
    nextGroup > 0 &&
    (!Number.isFinite(existingGroup) || existingGroup !== nextGroup)
  ) {
    payload.metric_group = nextGroup;
  }
  if (
    item.editedUnit &&
    !isCatalogEnumType(existing?.data_type || item.data_type)
  ) {
    const nextUnit = resolveCatalogUnitId(item.unit);
    const existingUnit = String(existing?.unit || '').trim();
    const sameUnit =
      !nextUnit ||
      nextUnit === existingUnit ||
      (nextUnit === DEFAULT_CATALOG_UNIT_ID &&
        (!existingUnit || existingUnit === DEFAULT_CATALOG_UNIT_ID));
    if (!sameUnit) {
      payload.unit = nextUnit;
    }
  }
  return Object.keys(payload).length ? payload : null;
};

/** 确认按指标短名各提交一次；解析已按名合并，此处再去重。 */
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
  mode = SCRIPT_METRIC_PERSIST_MODE_ADD,
  staleDeletes = []
}: {
  pluginId: string | number;
  objectId: string | number;
  metrics: BusinessMetricItem[];
  client: PersistScriptMetricsClient;
  mode?: ScriptMetricPersistMode;
  staleDeletes?: CatalogMetricRef[];
}): Promise<void> => {
  const persistableMetrics = applyStdoutMetricNames(metrics);
  const overwriteDeletes =
    mode === SCRIPT_METRIC_PERSIST_MODE_OVERWRITE ? staleDeletes : [];
  if (!persistableMetrics.length && !overwriteDeletes.length) {
    return;
  }
  const { get, post, patch, t } = client;
  const reservedMetricIds = collectReservedMetricIdViolations(persistableMetrics);
  if (reservedMetricIds.length) {
    throw new Error(formatReservedMetricIdMessage(reservedMetricIds, t));
  }
  const reservedKeys = collectReservedTagViolations(persistableMetrics);
  if (reservedKeys.length) {
    throw new Error(formatReservedTagRenameMessage(reservedKeys, t));
  }
  try {
    const deletable = overwriteDeletes.filter(
      (item) => item?.id && item?.name && !isSelfMetricName(item.name)
    );
    if (deletable.length) {
      const ids = deletable.map((item) => item.id);
      for (let offset = 0; offset < ids.length; offset += CATALOG_METRIC_PAGE_SIZE) {
        await post(
          '/monitor/api/metrics/batch_delete/',
          {
            ids: ids.slice(offset, offset + CATALOG_METRIC_PAGE_SIZE),
            monitor_plugin: Number(pluginId)
          },
          SILENT_REQ
        );
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
    const existingByName = new Map<string, CatalogMetricRef>();
    existing.forEach((item) => {
      if (!existingByName.has(item.name)) {
        existingByName.set(item.name, item);
      }
    });

    const uniqueMetrics = uniqueMetricsByName(persistableMetrics);
    if (!uniqueMetrics.length) {
      return;
    }

    const results = await Promise.allSettled(
      uniqueMetrics.map((item) => {
        const existingRow = existingByName.get(item.name);
        if (existingRow?.id) {
          const patchPayload = buildScriptMetricCatalogUpdatePayload(
            item,
            existingRow
          );
          if (!patchPayload) {
            return Promise.resolve();
          }
          return patch(
            `/monitor/api/metrics/${existingRow.id}/`,
            patchPayload,
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
