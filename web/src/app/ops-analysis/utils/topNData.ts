import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

export interface TopNItem {
  name: string;
  value: number | null;
}

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

export const buildTopNItems = (
  data: unknown,
  labelField?: string,
  valueField?: string,
): TopNItem[] => {
  const rows = unwrapTopNData(data);
  if (rows.length === 0) {
    return [];
  }

  return rows
    .map((row) => {
      const name = toTopNName(getValueByPath(row, labelField));
      if (!name) {
        return null;
      }

      return {
        name,
        value: coerceTopNNumericValue(getValueByPath(row, valueField)),
      };
    })
    .filter((item): item is TopNItem => item !== null);
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
): number => {
  if (value === null || value <= 0 || maxValue <= 0) {
    return 0;
  }
  return (value / maxValue) * 100;
};
