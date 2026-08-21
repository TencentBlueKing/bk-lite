import type { Dimension } from '@/app/monitor/types';

export interface AlertDimensionDisplayItem {
  key: string;
  label: string;
  value: string;
}

const formatDimensionValue = (value: unknown): string => {
  if (value == null || (typeof value === 'string' && !value.trim())) {
    return '--';
  }
  return String(value);
};

export const buildAlertDimensionDisplayItems = (
  metricDimensions: Dimension[] | undefined,
  alertDimensions: Record<string, unknown> | undefined
): AlertDimensionDisplayItem[] => {
  const values = alertDimensions || {};
  if (!Object.keys(values).length) {
    return [];
  }
  const definitions = metricDimensions || [];
  const definedNames = new Set(definitions.map(({ name }) => name));
  const definedItems = definitions.map(({ name, description }) => ({
    key: name,
    label: description?.trim() || name,
    value: formatDimensionValue(values[name])
  }));
  const extraItems = Object.keys(values)
    .filter((name) => !definedNames.has(name))
    .sort()
    .map((name) => ({
      key: name,
      label: name,
      value: formatDimensionValue(values[name])
    }));

  return [...definedItems, ...extraItems];
};
