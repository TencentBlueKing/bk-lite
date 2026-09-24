import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';

export interface WidgetFieldSelectOption {
  label: string;
  value: string;
}

const isPlainRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const formatFieldOptionLabel = (key: string, title?: string) => {
  const normalizedKey = key.trim();
  const normalizedTitle = (title || '').trim();

  if (!normalizedTitle || normalizedTitle === normalizedKey) {
    return normalizedKey;
  }

  return `${normalizedKey} (${normalizedTitle})`;
};

const collectSampleRows = (sample: unknown): unknown[] => {
  if (Array.isArray(sample)) {
    return sample;
  }
  if (!isPlainRecord(sample)) {
    return [];
  }
  if (Array.isArray(sample.items)) {
    return sample.items;
  }
  if (Array.isArray(sample.data)) {
    return sample.data;
  }
  const values = Object.values(sample);
  if (values.length > 0 && values.every(Array.isArray)) {
    return values.flat();
  }
  return [];
};

export const collectSampleFieldKeys = (sample: unknown): string[] => {
  const keys: string[] = [];
  const seen = new Set<string>();
  collectSampleRows(sample).forEach((row) => {
    if (!isPlainRecord(row)) {
      return;
    }
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

export const buildRoleFieldOptions = (
  schemaFields: ResponseFieldDefinition[] = [],
  previewRawData?: unknown,
): WidgetFieldSelectOption[] => {
  const optionMap = new Map<string, WidgetFieldSelectOption>();

  const appendOption = (key: string, title?: string) => {
    const normalizedKey = key.trim();
    if (!normalizedKey || optionMap.has(normalizedKey)) {
      return;
    }
    optionMap.set(normalizedKey, {
      label: formatFieldOptionLabel(normalizedKey, title),
      value: normalizedKey,
    });
  };

  schemaFields.forEach((field) => {
    appendOption(field.key, field.title);
  });

  collectSampleFieldKeys(previewRawData).forEach((key) => {
    appendOption(key);
  });

  return Array.from(optionMap.values());
};

export const dropRoleValueMissingFrom = (
  value: string | undefined,
  allowed: ReadonlySet<string>,
): string | undefined => {
  const trimmed = value?.trim();
  if (!trimmed || !allowed.has(trimmed)) {
    return undefined;
  }
  return trimmed;
};
