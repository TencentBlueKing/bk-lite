export interface MultiValueItem {
  label: string;
  value: string;
}

export interface MultiValueValidationResult {
  isValid: boolean;
  errorMessage?: string;
  items: MultiValueItem[];
}

const normalizeScalar = (value: unknown): string | null => {
  if (value == null || value === '') return '--';
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }
  return null;
};

const extractMultiValueItems = (data: unknown): unknown => {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return data;

  const record = data as Record<string, unknown>;
  if (Object.prototype.hasOwnProperty.call(record, 'items')) {
    return record.items;
  }

  const nested = record.data;
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const nestedRecord = nested as Record<string, unknown>;
    if (Object.prototype.hasOwnProperty.call(nestedRecord, 'items')) {
      return nestedRecord.items;
    }
  }

  return data;
};

export const validateMultiValueData = (
  data: unknown,
  errorMessage: string,
): MultiValueValidationResult => {
  const extracted = extractMultiValueItems(data);
  if (!Array.isArray(extracted)) {
    return { isValid: false, errorMessage, items: [] };
  }

  const items: MultiValueItem[] = [];
  for (const entry of extracted) {
    if (
      entry == null ||
      typeof entry !== 'object' ||
      Array.isArray(entry) ||
      !Object.prototype.hasOwnProperty.call(entry, 'label') ||
      !Object.prototype.hasOwnProperty.call(entry, 'value')
    ) {
      return { isValid: false, errorMessage, items: [] };
    }
    const record = entry as Record<string, unknown>;
    const label = normalizeScalar(record.label);
    const value = normalizeScalar(record.value);
    if (label == null || value == null) {
      return { isValid: false, errorMessage, items: [] };
    }
    items.push({ label, value });
  }
  return { isValid: true, items };
};
