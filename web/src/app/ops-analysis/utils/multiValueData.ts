export interface MultiValueItem {
  label: string;
  value: string;
}

export interface MultiValueValidationResult {
  isValid: boolean;
  errorMessage?: string;
  items: MultiValueItem[];
}

export interface MultiValueFieldMapping {
  labelField?: string;
  valueField?: string;
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
  if (Array.isArray(nested)) {
    return nested;
  }
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const nestedRecord = nested as Record<string, unknown>;
    if (Object.prototype.hasOwnProperty.call(nestedRecord, 'items')) {
      return nestedRecord.items;
    }
  }

  return data;
};

const hasExplicitMultiValueMapping = (mapping?: MultiValueFieldMapping) =>
  Boolean(mapping?.labelField?.trim() || mapping?.valueField?.trim());

export const validateMultiValueData = (
  data: unknown,
  errorMessage: string,
  mapping?: MultiValueFieldMapping,
): MultiValueValidationResult => {
  const extracted = extractMultiValueItems(data);
  if (!Array.isArray(extracted)) {
    return { isValid: false, errorMessage, items: [] };
  }

  const labelField = mapping?.labelField?.trim();
  const valueField = mapping?.valueField?.trim();
  const explicit = hasExplicitMultiValueMapping(mapping);
  const items: MultiValueItem[] = [];
  for (const entry of extracted) {
    if (entry == null || typeof entry !== 'object' || Array.isArray(entry)) {
      return { isValid: false, errorMessage, items: [] };
    }
    const record = entry as Record<string, unknown>;
    if (explicit) {
      const label = normalizeScalar(labelField ? record[labelField] : undefined);
      const value = normalizeScalar(valueField ? record[valueField] : undefined);
      if (label == null || value == null) {
        return { isValid: false, errorMessage, items: [] };
      }
      items.push({ label, value });
      continue;
    }
    if (!Object.prototype.hasOwnProperty.call(record, 'value')) {
      return { isValid: false, errorMessage, items: [] };
    }
    const labelKey = Object.prototype.hasOwnProperty.call(record, 'label')
      ? 'label'
      : Object.prototype.hasOwnProperty.call(record, 'name')
        ? 'name'
        : null;
    if (!labelKey) {
      return { isValid: false, errorMessage, items: [] };
    }
    const label = normalizeScalar(record[labelKey]);
    const value = normalizeScalar(record.value);
    if (label == null || value == null) {
      return { isValid: false, errorMessage, items: [] };
    }
    items.push({ label, value });
  }
  return { isValid: true, items };
};
