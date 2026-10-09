import { HandledRequestError } from '@/utils/request';
import { MetricItem } from '@/app/monitor/types';
import { isSelfMetricName } from '../configure/scriptMetricsParser';
import { resolveCatalogUnitId } from '../configure/scriptMetricPersist';

/** 脚本插件隐藏并在合并时原样保留的平台维度。前后端同内容。 */
export const PRESERVED_METRIC_DIMENSION_KEYS = [
  'instance_id',
  'agent_id',
  'plugin_id',
  'instance_type',
  'collect_type',
  'config_id',
  'config_type',
  'host',
  'script',
  'bklite_script_reserved_keys'
] as const;

const PRESERVED_METRIC_DIMENSION_KEY_SET = new Set(
  PRESERVED_METRIC_DIMENSION_KEYS.map((key) => key.toLowerCase())
);
const PRESERVED_METRIC_DIMENSION_PREFIX = 'bklite_script_';

export const isPreservedMetricDimensionName = (name: string): boolean => {
  const text = String(name || '').trim();
  if (!text) {
    return false;
  }
  const lower = text.toLowerCase();
  return (
    PRESERVED_METRIC_DIMENSION_KEY_SET.has(lower) ||
    lower.startsWith(PRESERVED_METRIC_DIMENSION_PREFIX)
  );
};

export const METRIC_INLINE_EDIT_FIELDS = [
  'display_name',
  'metric_group',
  'unit',
  'data_type',
  'description',
  'dimensions'
] as const;

export type MetricInlineEditField = (typeof METRIC_INLINE_EDIT_FIELDS)[number];

export interface MetricInlineDraft {
  display_name: string;
  metric_group: number;
  unit: string;
  data_type: string;
  description: string;
  dimensions: string[];
}

export interface MetricInlineItemError {
  id: number;
  name: string;
  field?: string | null;
  message: string;
  code?: string;
}

export interface MetricBatchUpdateItem {
  id: number;
  display_name?: string;
  metric_group?: number;
  unit?: string;
  data_type?: string;
  description?: string;
  dimensions?: string[];
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const hasBkliteScriptMetricPrefix = (name: string): boolean => {
  const lower = String(name || '').toLowerCase();
  return (
    lower.startsWith('bklite_script_') || lower.startsWith('bklite_script.')
  );
};

export const isMetricInlineReadonly = (
  metric: {
    id?: unknown;
    is_pre?: unknown;
    name?: unknown;
  },
  isScriptPlugin: boolean
): boolean => {
  if (metric.is_pre === true) {
    return true;
  }
  const name = String(metric.name || '');
  if (isScriptPlugin) {
    return isSelfMetricName(name);
  }
  return hasBkliteScriptMetricPrefix(name);
};

export const catalogEditableDimensionNames = (
  dims?: Array<{ name?: string }> | null,
  isScriptPlugin = false
): string[] =>
  (dims || [])
    .map((item) => String(item?.name || '').trim())
    .filter((name) => {
      if (!name) {
        return false;
      }
      return !(isScriptPlugin && isPreservedMetricDimensionName(name));
    });

export const normalizeInlineDimensionNames = (names: string[] | undefined): string[] =>
  (names || []).map((name) => String(name || '').trim()).filter(Boolean);

export const findInlineDimensionIssue = (
  names: string[] | undefined,
  isScriptPlugin = false
): { code: 'reserved' | 'duplicate'; name: string } | null => {
  const seen = new Set<string>();
  for (const name of normalizeInlineDimensionNames(names)) {
    const lower = name.toLowerCase();
    if (isScriptPlugin && isPreservedMetricDimensionName(name)) {
      return { code: 'reserved', name };
    }
    if (seen.has(lower)) {
      return { code: 'duplicate', name };
    }
    seen.add(lower);
  }
  return null;
};

const sameDimensionNames = (left: string[], right: string[]): boolean =>
  left.length === right.length && left.every((name, index) => name === right[index]);

export const snapshotMetricInlineDraft = (
  metric: MetricItem,
  isScriptPlugin = false
): MetricInlineDraft => {
  const dataType =
    String(metric.data_type || 'Number') === 'Enum' ? 'Enum' : 'Number';
  const rawUnit = String(metric.unit || '');
  return {
    display_name: String(metric.display_name || metric.name || '').trim(),
    metric_group: Number(metric.metric_group) || 0,
    unit:
      dataType === 'Enum'
        ? rawUnit
        : resolveCatalogUnitId(rawUnit) || rawUnit,
    data_type: dataType,
    description: String(
      (typeof metric.description === 'string' ? metric.description : '') ||
        metric.display_description ||
        ''
    ),
    dimensions: catalogEditableDimensionNames(
      metric.dimensions,
      isScriptPlugin
    )
  };
};

export const normalizeMetricInlineDraft = (
  draft: MetricInlineDraft
): MetricInlineDraft => ({
  display_name: String(draft.display_name || '').trim(),
  metric_group: Number(draft.metric_group) || 0,
  unit: String(draft.unit || ''),
  data_type: draft.data_type === 'Enum' ? 'Enum' : 'Number',
  description: draft.description == null ? '' : String(draft.description),
  dimensions: normalizeInlineDimensionNames(draft.dimensions)
});

export const isInlineFieldDirty = (
  draft: MetricInlineDraft | undefined,
  baseline: MetricInlineDraft | undefined,
  field: MetricInlineEditField
): boolean => {
  if (!draft || !baseline) {
    return false;
  }
  const next = normalizeMetricInlineDraft(draft);
  const prev = normalizeMetricInlineDraft(baseline);
  if (
    field === 'unit' &&
    next.data_type === 'Enum' &&
    prev.data_type === 'Enum'
  ) {
    return false;
  }
  if (field === 'dimensions') {
    return !sameDimensionNames(next.dimensions, prev.dimensions);
  }
  return next[field] !== prev[field];
};

export const countDirtyInlineFields = (
  drafts: Record<number, MetricInlineDraft>,
  baseline: Record<number, MetricInlineDraft>,
  readonlyIds?: Set<number>
): number => {
  let count = 0;
  Object.keys(drafts).forEach((key) => {
    const id = Number(key);
    if (readonlyIds?.has(id) || !baseline[id]) {
      return;
    }
    METRIC_INLINE_EDIT_FIELDS.forEach((field) => {
      if (isInlineFieldDirty(drafts[id], baseline[id], field)) {
        count += 1;
      }
    });
  });
  return count;
};

export const buildMetricBatchUpdateItem = (
  id: number,
  draft: MetricInlineDraft,
  baseline: MetricInlineDraft
): MetricBatchUpdateItem | null => {
  const next = normalizeMetricInlineDraft(draft);
  const prev = normalizeMetricInlineDraft(baseline);
  const item: MetricBatchUpdateItem = { id };
  let changed = false;
  if (next.display_name !== prev.display_name) {
    item.display_name = next.display_name;
    changed = true;
  }
  if (next.metric_group !== prev.metric_group) {
    item.metric_group = next.metric_group;
    changed = true;
  }
  if (next.data_type !== prev.data_type) {
    item.data_type = next.data_type;
    changed = true;
  }
  if (next.data_type !== 'Enum' && next.unit !== prev.unit) {
    item.unit = next.unit || 'none';
    changed = true;
  } else if (
    next.data_type === 'Number' &&
    prev.data_type === 'Enum' &&
    item.data_type === 'Number'
  ) {
    item.unit = next.unit || 'none';
    changed = true;
  }
  if (next.description !== prev.description) {
    item.description = next.description;
    changed = true;
  }
  if (!sameDimensionNames(next.dimensions, prev.dimensions)) {
    item.dimensions = next.dimensions;
    changed = true;
  }
  return changed ? item : null;
};

export const collectDirtyBatchItems = (
  drafts: Record<number, MetricInlineDraft>,
  baseline: Record<number, MetricInlineDraft>,
  readonlyIds?: Set<number>
): MetricBatchUpdateItem[] => {
  const items: MetricBatchUpdateItem[] = [];
  Object.keys(drafts).forEach((key) => {
    const id = Number(key);
    if (!Number.isFinite(id) || id <= 0 || readonlyIds?.has(id) || !baseline[id]) {
      return;
    }
    const item = buildMetricBatchUpdateItem(id, drafts[id], baseline[id]);
    if (item) {
      items.push(item);
    }
  });
  return items;
};

export const applySuccessfulItemsToBaseline = (
  baseline: Record<number, MetricInlineDraft>,
  drafts: Record<number, MetricInlineDraft>,
  ids: number[]
): Record<number, MetricInlineDraft> => {
  const next = { ...baseline };
  ids.forEach((id) => {
    if (drafts[id]) {
      next[id] = normalizeMetricInlineDraft(drafts[id]);
    }
  });
  return next;
};

export const chunkMetricBatchItems = <T>(
  items: T[],
  size: number
): T[][] => {
  const chunks: T[][] = [];
  for (let offset = 0; offset < items.length; offset += size) {
    chunks.push(items.slice(offset, offset + size));
  }
  return chunks;
};

const parseErrorEntry = (value: unknown): MetricInlineItemError | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = Number(record.id);
  if (!Number.isFinite(id) || id <= 0) {
    return null;
  }
  const message = String(record.message || record.detail || '').trim();
  if (!message) {
    return null;
  }
  return {
    id,
    name: String(record.name || ''),
    field:
      record.field == null || record.field === ''
        ? null
        : String(record.field),
    message,
    code: record.code == null ? undefined : String(record.code)
  };
};

const extractErrorsList = (payload: Record<string, unknown> | null): unknown => {
  if (!payload) {
    return null;
  }
  const data = asRecord(payload.data);
  if (Array.isArray(payload.errors)) {
    return payload.errors;
  }
  if (data && Array.isArray(data.errors)) {
    return data.errors;
  }
  return null;
};

export const parseMetricBatchUpdateErrors = (
  error: unknown
): MetricInlineItemError[] => {
  const fromHandled =
    error instanceof HandledRequestError ? asRecord(error.payload) : null;
  const record = asRecord(error);
  const payload =
    fromHandled ||
    asRecord(record?.payload) ||
    asRecord(asRecord(record?.response)?.data) ||
    record;
  const list = extractErrorsList(payload);
  if (!Array.isArray(list)) {
    return [];
  }
  return list
    .map((item) => parseErrorEntry(item))
    .filter((item): item is MetricInlineItemError => Boolean(item));
};

export const fieldErrorMessage = (
  errors: MetricInlineItemError[] | undefined,
  field: MetricInlineEditField | 'id'
): string => {
  if (!errors?.length) {
    return '';
  }
  const matched = errors.find((item) => item.field === field);
  if (matched) {
    return matched.message;
  }
  if (field === 'display_name') {
    const rowLevel = errors.find((item) => !item.field);
    return rowLevel?.message || '';
  }
  return '';
};

export const groupErrorsByMetricId = (
  errors: MetricInlineItemError[]
): Record<number, MetricInlineItemError[]> => {
  const grouped: Record<number, MetricInlineItemError[]> = {};
  errors.forEach((item) => {
    grouped[item.id] = [...(grouped[item.id] || []), item];
  });
  return grouped;
};
