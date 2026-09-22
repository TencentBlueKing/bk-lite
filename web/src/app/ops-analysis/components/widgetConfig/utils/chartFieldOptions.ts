import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import { unwrapTopNData } from '@/app/ops-analysis/utils/topNData';

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

export const buildTopNFieldSelectOptions = (
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

  unwrapTopNData(previewRawData).forEach((row) => {
    if (!isPlainRecord(row)) {
      return;
    }
    Object.keys(row).forEach((key) => {
      appendOption(key);
    });
  });

  return Array.from(optionMap.values());
};
