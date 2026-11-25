import dayjs from 'dayjs';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import { coerceTopNNumericValue } from '@/app/ops-analysis/utils/topNData';

export const SCALAR_CALC_METHODS = [
  'count',
  'avg',
  'max',
  'min',
  'sum',
  'latest',
] as const;

export type ScalarCalcMethod = (typeof SCALAR_CALC_METHODS)[number];

export interface ScalarCalcConfig {
  method: ScalarCalcMethod;
  field?: string;
  timeField?: string;
}

export type ScalarReduction =
  | { status: 'value'; value: number }
  | { status: 'empty' }
  | { status: 'uncomputable' };

const METHOD_SET = new Set<string>(SCALAR_CALC_METHODS);

const cleanField = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
};

const buildScalarCalc = (
  method: ScalarCalcMethod,
  field: unknown,
  timeField: unknown,
): ScalarCalcConfig => {
  const calc: ScalarCalcConfig = { method };
  if (method !== 'count') {
    const cleanedField = cleanField(field);
    if (cleanedField) calc.field = cleanedField;
  }
  if (method === 'latest') {
    const cleanedTime = cleanField(timeField);
    if (cleanedTime) calc.timeField = cleanedTime;
  }
  return calc;
};

export const readScalarCalc = (value: unknown): ScalarCalcConfig | undefined => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  if (!METHOD_SET.has(String(record.method))) return undefined;
  return buildScalarCalc(record.method as ScalarCalcMethod, record.field, record.timeField);
};

export const scalarCalcFromForm = (input: {
  method?: unknown;
  field?: unknown;
  timeField?: unknown;
}): ScalarCalcConfig | undefined => {
  if (!METHOD_SET.has(String(input.method ?? ''))) return undefined;
  return buildScalarCalc(input.method as ScalarCalcMethod, input.field, input.timeField);
};

export const singleValueSourceReady = (valueConfig?: {
  dataSource?: unknown;
  selectedFields?: string[];
  scalarCalc?: unknown;
} | null): boolean => {
  if (valueConfig?.dataSource == null || valueConfig.dataSource === '') return false;
  if (readScalarCalc(valueConfig.scalarCalc)) return true;
  return Boolean(valueConfig.selectedFields?.length);
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const collectRecords = (
  raw: unknown,
): { kind: 'empty' } | { kind: 'records'; records: unknown[] } => {
  if (raw == null) return { kind: 'empty' };
  if (Array.isArray(raw)) {
    return raw.length === 0 ? { kind: 'empty' } : { kind: 'records', records: raw };
  }
  if (isRecord(raw)) {
    if (Array.isArray(raw.items)) {
      return raw.items.length === 0
        ? { kind: 'empty' }
        : { kind: 'records', records: raw.items };
    }
    if (Array.isArray(raw.data)) {
      return raw.data.length === 0
        ? { kind: 'empty' }
        : { kind: 'records', records: raw.data };
    }
    if (Object.keys(raw).length === 0) return { kind: 'empty' };
    return { kind: 'records', records: [raw] };
  }
  return { kind: 'records', records: [raw] };
};

const recordMeasure = (record: unknown, field?: string): number | null => {
  if (field) return coerceTopNNumericValue(getValueByPath(record, field));
  return coerceTopNNumericValue(record);
};

const readTimestamp = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text) return null;
  const parsed = dayjs(text);
  return parsed.isValid() ? parsed.valueOf() : null;
};

const reduceLatest = (
  records: unknown[],
  field: string | undefined,
  timeField: string | undefined,
): ScalarReduction => {
  if (!timeField) return { status: 'uncomputable' };
  let bestValue: number | null = null;
  let bestTime = Number.NEGATIVE_INFINITY;
  let bestIndex = -1;
  records.forEach((record, index) => {
    const time = readTimestamp(
      isRecord(record) || Array.isArray(record)
        ? getValueByPath(record, timeField)
        : undefined,
    );
    const measure = recordMeasure(record, field);
    if (time === null || measure === null) return;
    if (time > bestTime || (time === bestTime && index > bestIndex)) {
      bestTime = time;
      bestIndex = index;
      bestValue = measure;
    }
  });
  return bestValue === null
    ? { status: 'uncomputable' }
    : { status: 'value', value: bestValue };
};

const reduceNumbers = (
  records: unknown[],
  field: string | undefined,
  method: Exclude<ScalarCalcMethod, 'count' | 'latest'>,
): ScalarReduction => {
  const numbers: number[] = [];
  records.forEach((record) => {
    const measure = recordMeasure(record, field);
    if (measure !== null) numbers.push(measure);
  });
  if (numbers.length === 0) return { status: 'uncomputable' };
  if (method === 'max') {
    return { status: 'value', value: numbers.reduce((best, item) => Math.max(best, item)) };
  }
  if (method === 'min') {
    return { status: 'value', value: numbers.reduce((best, item) => Math.min(best, item)) };
  }
  const total = numbers.reduce((sum, item) => sum + item, 0);
  if (method === 'sum') return { status: 'value', value: total };
  return { status: 'value', value: total / numbers.length };
};

export const reduceScalarRecords = (
  raw: unknown,
  calc: ScalarCalcConfig,
): ScalarReduction => {
  const collected = collectRecords(raw);
  if (collected.kind === 'empty') {
    return calc.method === 'count'
      ? { status: 'value', value: 0 }
      : { status: 'empty' };
  }
  if (calc.method === 'count') {
    return { status: 'value', value: collected.records.length };
  }
  if (calc.method === 'latest') {
    return reduceLatest(collected.records, calc.field, calc.timeField);
  }
  return reduceNumbers(collected.records, calc.field, calc.method);
};
