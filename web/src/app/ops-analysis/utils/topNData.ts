import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

export interface TopNItem {
  name: string;
  value: number | null;
  source?: Record<string, unknown>;
  /** 标量拆行时的字段名，供链接读取这一行的值。数组排名不写。 */
  field?: string;
}

export interface TopNScalarField {
  field: string;
  label?: string;
}

export interface TopNBarConfig {
  barMode?: string;
  barMax?: number;
  gaugeMax?: number;
}

const isTopNRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const DECIMAL_NUMBER_PATTERN =
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

export const unwrapTopNData = (data: unknown): unknown[] => {
  if (Array.isArray(data)) {
    return data;
  }

  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;
    if (Array.isArray(record.items)) {
      return record.items;
    }
    if (Array.isArray(record.data)) {
      return record.data;
    }
  }

  return [];
};

export const coerceTopNNumericValue = (raw: unknown): number | null => {
  if (typeof raw === 'boolean' || raw === null || raw === undefined || raw === '') {
    return null;
  }

  if (typeof raw === 'number') {
    return Number.isFinite(raw) ? raw : null;
  }

  if (typeof raw !== 'string') {
    return null;
  }

  const normalized = raw.trim();
  if (!DECIMAL_NUMBER_PATTERN.test(normalized)) {
    return null;
  }

  const numericValue = Number(normalized);
  return Number.isFinite(numericValue) ? numericValue : null;
};

const toTopNName = (raw: unknown): string => {
  if (raw === undefined || raw === null) {
    return '';
  }
  return String(raw).trim();
};

export const normalizeTopNScalarFields = (
  fields?: Array<{ field?: string; label?: string } | null> | null,
): TopNScalarField[] => {
  const normalized: TopNScalarField[] = [];
  (fields || []).forEach((item) => {
    const field = String(item?.field || '').trim();
    if (!field) {
      return;
    }
    const label = String(item?.label || '').trim();
    normalized.push(label ? { field, label } : { field });
  });
  return normalized;
};

const isListEnvelope = (value: Record<string, unknown>) =>
  Array.isArray(value.items) || Array.isArray(value.data);

/** 标量拆行只认单个对象。数组，以及 items/data 列表包装，仍走原来的排名。 */
export const isScalarTopNObject = (value: unknown): value is Record<string, unknown> =>
  isTopNRecord(value) && !isListEnvelope(value);

const positiveFinite = (value: unknown): number | undefined => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return undefined;
  }
  return value;
};

const buildScalarTopNItems = (
  record: Record<string, unknown>,
  fields: TopNScalarField[],
): TopNItem[] => fields.map((item) => ({
  name: item.label || item.field,
  value: coerceTopNNumericValue(getValueByPath(record, item.field)),
  source: record,
  field: item.field,
}));

export const buildTopNItems = (
  data: unknown,
  labelField?: string,
  valueField?: string,
  options?: { scalarFields?: Array<{ field?: string; label?: string } | null> | null },
): TopNItem[] => {
  const scalarFields = normalizeTopNScalarFields(options?.scalarFields);
  if (scalarFields.length > 0 && isScalarTopNObject(data)) {
    return buildScalarTopNItems(data, scalarFields);
  }

  const rows = unwrapTopNData(data);
  if (rows.length === 0) {
    return [];
  }

  const items = rows
    .map((row, index) => {
      const name = toTopNName(getValueByPath(row, labelField));
      if (!name) {
        return null;
      }

      return {
        index,
        item: {
          name,
          value: coerceTopNNumericValue(getValueByPath(row, valueField)),
          ...(isTopNRecord(row) ? { source: row } : {}),
        },
      };
    })
    .filter((entry): entry is { index: number; item: TopNItem } => entry !== null);

  // 排名图按数值从大到小。空值靠后，相同数值保持原顺序。
  items.sort((left, right) => {
    const leftValue = left.item.value;
    const rightValue = right.item.value;
    const leftMissing = leftValue === null;
    const rightMissing = rightValue === null;
    if (leftMissing !== rightMissing) {
      return leftMissing ? 1 : -1;
    }
    if (
      leftValue !== null
      && rightValue !== null
      && leftValue !== rightValue
    ) {
      return rightValue - leftValue;
    }
    return left.index - right.index;
  });

  return items.map((entry) => entry.item);
};

export const resolveTopNMaxValue = (items: TopNItem[]): number => {
  const numericValues = items
    .map((item) => item.value)
    .filter((value): value is number => value !== null && Number.isFinite(value));

  return numericValues.length > 0 ? Math.max(...numericValues) : 0;
};

export const resolveTopNBarPercent = (
  value: number | null,
  maxValue: number,
  mode: 'relative' | 'absolute' = 'relative',
): number => {
  if (value === null || value <= 0 || maxValue <= 0) {
    return 0;
  }
  const scaled = mode === 'absolute' ? Math.min(value, maxValue) : value;
  return (scaled / maxValue) * 100;
};

const RELATIVE_TOPN_BAR_FLOOR = 2;

export const resolveConfiguredTopNBarPercent = (
  value: number | null,
  items: TopNItem[],
  config?: TopNBarConfig,
): number => {
  if (config?.barMode === 'absolute') {
    const maxValue = positiveFinite(config.barMax) ?? positiveFinite(config.gaugeMax) ?? 0;
    return resolveTopNBarPercent(value, maxValue, 'absolute');
  }
  const percent = resolveTopNBarPercent(value, resolveTopNMaxValue(items));
  if (percent > 0 && percent < RELATIVE_TOPN_BAR_FLOOR) {
    return RELATIVE_TOPN_BAR_FLOOR;
  }
  return percent;
};

export const validateTopNPayload = (
  data: unknown,
  options?: {
    labelField?: string;
    valueField?: string;
    scalarFields?: Array<{ field?: string; label?: string } | null> | null;
  },
): boolean => {
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return true;
  }

  const scalarFields = normalizeTopNScalarFields(options?.scalarFields);
  if (scalarFields.length > 0 && isScalarTopNObject(data)) {
    return buildTopNItems(data, options?.labelField, options?.valueField, { scalarFields }).length > 0;
  }

  if (!Array.isArray(data)) {
    return false;
  }

  return buildTopNItems(data, options?.labelField, options?.valueField).length > 0;
};
