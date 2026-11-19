export interface ChartBinding {
  source: 'explicit' | 'legacy' | 'none';
  dimensionField?: string;
  measureField?: string;
  missingField?: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const trim = (value: unknown): string => String(value ?? '').trim();

const collectRows = (sample: unknown): Record<string, unknown>[] => {
  if (Array.isArray(sample)) {
    return sample.filter(isRecord);
  }
  if (!isRecord(sample)) {
    return [];
  }
  if (Array.isArray(sample.items)) {
    return sample.items.filter(isRecord);
  }
  if (Array.isArray(sample.data)) {
    return sample.data.filter(isRecord);
  }
  const values = Object.values(sample);
  if (values.length > 0 && values.every(Array.isArray)) {
    return values.flat().filter(isRecord);
  }
  return [];
};

const rowKeys = (sample: unknown): string[] => {
  const keys: string[] = [];
  const seen = new Set<string>();
  collectRows(sample).forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      keys.push(key);
    });
  });
  return keys;
};

const resultIsEmpty = (raw: unknown): boolean => {
  if (raw == null) {
    return true;
  }
  if (Array.isArray(raw)) {
    return raw.length === 0;
  }
  if (!isRecord(raw)) {
    return false;
  }
  const values = Object.values(raw);
  return values.length === 0 || values.every((value) => Array.isArray(value) && value.length === 0);
};

const presentKeys = (raw: unknown): Set<string> => new Set(rowKeys(raw));

/**
 * 已选手动字段不在当前非空结果里时返回该字段。
 * 空结果不判断缺失。
 */
export const missingConfiguredField = (
  raw: unknown,
  configured: Array<string | undefined>,
): string | undefined => {
  const keys = configured.map((key) => trim(key)).filter(Boolean);
  if (keys.length === 0 || raw == null) {
    return undefined;
  }
  if (resultIsEmpty(raw)) {
    return undefined;
  }
  const present = presentKeys(raw);
  if (present.size === 0) {
    return undefined;
  }
  return keys.find((key) => !present.has(key));
};

const legacyBinding = (raw: unknown): ChartBinding | null => {
  const rows = collectRows(raw);
  const sample = rows[0];
  if (!sample) {
    return null;
  }
  if ('name' in sample && ('value' in sample || 'count' in sample)) {
    return {
      source: 'legacy',
      dimensionField: 'name',
      measureField: 'value' in sample ? 'value' : 'count',
    };
  }
  return null;
};

export const resolveChartBinding = (
  raw: unknown,
  mapping?: {
    dimensionField?: string;
    valueField?: string;
    valueFields?: string[];
    seriesField?: string;
  },
): ChartBinding => {
  const dimensionField = trim(mapping?.dimensionField);
  const listed = (mapping?.valueFields || []).map((key) => trim(key)).filter(Boolean);
  const valueField = trim(mapping?.valueField);
  const measureField = listed[0] || valueField;
  const seriesField = trim(mapping?.seriesField);
  const configured = [
    dimensionField,
    ...listed,
    ...(listed.length > 0 ? [] : [valueField]),
    seriesField,
  ].filter(Boolean);
  if (configured.length > 0) {
    return {
      source: 'explicit',
      dimensionField: dimensionField || undefined,
      measureField: measureField || undefined,
      missingField: missingConfiguredField(raw, configured),
    };
  }
  return legacyBinding(raw) || { source: 'none' };
};

export const chartFieldMissingMessage = (field: string): string =>
  `dashboard.chartFieldMissing:${field}`;

export const readChartFieldMissing = (message?: string): string | null => {
  const prefix = 'dashboard.chartFieldMissing:';
  if (!message?.startsWith(prefix)) {
    return null;
  }
  return message.slice(prefix.length) || null;
};
