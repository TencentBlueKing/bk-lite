import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';

export type FieldRole = 'dimension' | 'measure' | 'identity';

export interface DeclaredField {
  key: string;
  title?: string;
  value_type?: ResponseFieldDefinition['value_type'] | string;
  role?: FieldRole;
  modes?: string[];
}

export interface ChartBinding {
  source: 'explicit' | 'role' | 'legacy' | 'none';
  dimensionField?: string;
  measureField?: string;
  identityField?: string;
  missingField?: string;
  keepBlankLabel: boolean;
}

const PROTOCOL_KEYS = new Set([
  'structure',
  'status',
  'unit',
  'aggregation',
  'items',
  'count',
  'page',
  'page_size',
  'series',
  'query_object',
  'unbound_instance_ids',
  'fields',
  'column_fields',
  'data',
]);

const ROLES = new Set<FieldRole>(['dimension', 'measure', 'identity']);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const trim = (value: unknown): string => String(value ?? '').trim();

export const readDeclaredFields = (raw: unknown): DeclaredField[] | null => {
  if (!isRecord(raw) || !Array.isArray(raw.fields)) {
    return null;
  }
  const fields: DeclaredField[] = [];
  raw.fields.forEach((item) => {
    if (!isRecord(item)) {
      return;
    }
    const key = trim(item.key);
    if (!key) {
      return;
    }
    const role = trim(item.role);
    const modes = Array.isArray(item.modes)
      ? item.modes.map((mode) => trim(mode)).filter(Boolean)
      : undefined;
    fields.push({
      key,
      title: trim(item.title) || undefined,
      value_type: trim(item.value_type) || undefined,
      role: ROLES.has(role as FieldRole) ? (role as FieldRole) : undefined,
      modes: modes && modes.length > 0 ? modes : undefined,
    });
  });
  return fields;
};

export const schemaDeclaresModes = (
  fields: Array<Pick<DeclaredField, 'modes'>> = [],
): boolean => fields.some((field) => (field.modes || []).length > 0);

export const fieldAppliesToMode = (
  field: Pick<DeclaredField, 'modes'>,
  mode?: string,
): boolean => {
  const modes = (field.modes || []).map((item) => item.trim()).filter(Boolean);
  if (modes.length === 0) {
    return true;
  }
  const current = trim(mode);
  return Boolean(current) && modes.includes(current);
};

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

const scalarKeys = (sample: unknown): string[] => {
  if (!isRecord(sample) || collectRows(sample).length > 0) {
    return [];
  }
  if (sample.structure === 'series' || sample.structure === 'category' || sample.structure === 'table') {
    return [];
  }
  return Object.keys(sample).filter((key) => !PROTOCOL_KEYS.has(key));
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
  const structure = raw.structure;
  const status = raw.status;
  if (structure === 'category' || structure === 'table') {
    return !Array.isArray(raw.items) || raw.items.length === 0;
  }
  if (structure === 'series') {
    if (!isRecord(raw.series)) {
      return true;
    }
    return !Object.values(raw.series).some((points) => Array.isArray(points) && points.length > 0);
  }
  if (structure === 'value') {
    return status === 'empty' || status === 'missing';
  }
  if (status === 'empty' || status === 'missing') {
    return true;
  }
  return false;
};

const presentKeys = (raw: unknown): Set<string> => {
  const rows = collectRows(raw);
  if (rows.length > 0) {
    return new Set(rowKeys(raw));
  }
  if (isRecord(raw) && raw.structure === 'value') {
    return new Set(scalarKeys(raw));
  }
  return new Set(rowKeys(raw));
};

/**
 * 已配置字段不在当前结果里时返回该字段。
 * 空结果且没有权威 fields 时不判断缺失；fields 声明了结果却没有该键，空结果也算缺失。
 */
export const missingConfiguredField = (
  raw: unknown,
  configured: Array<string | undefined>,
): string | undefined => {
  const keys = configured.map((key) => trim(key)).filter(Boolean);
  if (keys.length === 0 || raw == null) {
    return undefined;
  }
  const declared = readDeclaredFields(raw);
  if (declared) {
    const known = new Set(declared.map((field) => field.key));
    return keys.find((key) => !known.has(key));
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

const firstRole = (fields: DeclaredField[], role: FieldRole): string | undefined =>
  fields.find((field) => field.role === role)?.key;

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
      keepBlankLabel: false,
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
  const declared = readDeclaredFields(raw) || [];
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
      identityField: firstRole(declared, 'identity'),
      missingField: missingConfiguredField(raw, configured),
      keepBlankLabel: true,
    };
  }
  if (declared.some((field) => field.role)) {
    return {
      source: 'role',
      dimensionField: firstRole(declared, 'dimension'),
      measureField: firstRole(declared, 'measure'),
      identityField: firstRole(declared, 'identity'),
      keepBlankLabel: true,
    };
  }
  return legacyBinding(raw) || { source: 'none', keepBlankLabel: false };
};

export const measureKeyFromFields = (raw: unknown): string | undefined => {
  const declared = readDeclaredFields(raw);
  if (!declared) {
    return undefined;
  }
  return firstRole(declared, 'measure');
};

export const candidateFields = (
  schemaFields: ResponseFieldDefinition[] = [],
  previewRawData?: unknown,
  mode?: string,
): DeclaredField[] => {
  const declared = readDeclaredFields(previewRawData);
  const schemaByKey = new Map(schemaFields.map((field) => [field.key, field]));
  if (declared) {
    return declared.map((field) => {
      const schema = schemaByKey.get(field.key);
      return {
        ...field,
        title: field.title || schema?.title || field.key,
        value_type: field.value_type || schema?.value_type,
      };
    });
  }
  const concrete = rowKeys(previewRawData).length > 0
    ? rowKeys(previewRawData)
    : scalarKeys(previewRawData);
  const scoped = schemaFields.filter((field) => fieldAppliesToMode(field, mode));
  const legacy = !schemaDeclaresModes(schemaFields);
  if (concrete.length > 0) {
    const keys = legacy
      ? [...schemaFields.map((field) => field.key), ...concrete]
      : concrete;
    const seen = new Set<string>();
    return keys.flatMap((key) => {
      const trimmed = trim(key);
      if (!trimmed || seen.has(trimmed) || PROTOCOL_KEYS.has(trimmed)) {
        return [];
      }
      seen.add(trimmed);
      const schema = schemaByKey.get(trimmed);
      return [{
        key: trimmed,
        title: schema?.title || trimmed,
        value_type: schema?.value_type,
        role: schema?.role,
        modes: schema?.modes,
      }];
    });
  }
  return (legacy ? schemaFields : scoped).flatMap((field) => {
    const key = trim(field.key);
    if (!key) {
      return [];
    }
    return [{
      key,
      title: field.title || key,
      value_type: field.value_type,
      role: field.role,
      modes: field.modes,
    }];
  });
};

export const delegatesGenericChart = (raw: unknown): boolean => {
  if (!isRecord(raw)) {
    return false;
  }
  return raw.structure === 'category'
    || raw.structure === 'series'
    || raw.structure === 'value'
    || raw.structure === 'table'
    || Array.isArray(raw.fields);
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
