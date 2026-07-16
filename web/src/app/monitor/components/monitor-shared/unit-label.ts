interface MonitorUnitListItem {
  unit_id: string;
  display_unit: string;
}

const VACANT_UNITS = ['short', 'none', 'counts'];

export const isSerializedStringArray = (input: unknown): input is string => {
  try {
    if (typeof input !== 'string') {
      return false;
    }
    const parsed = JSON.parse(input);
    return Array.isArray(parsed);
  } catch {
    return false;
  }
};

export const resolveMonitorUnitLabel = (
  value: unknown,
  displayUnit?: string,
  unitList: MonitorUnitListItem[] = [],
): string => {
  if (
    !value ||
    VACANT_UNITS.includes(value as string) ||
    isSerializedStringArray(value)
  ) {
    return '';
  }

  let unit = unitList.find((item) => item.unit_id === value);
  if (displayUnit) {
    unit = {
      unit_id: String(value),
      display_unit: displayUnit,
    };
  }

  const resolvedDisplayUnit = unit?.display_unit;
  return VACANT_UNITS.includes(resolvedDisplayUnit || '')
    ? ''
    : resolvedDisplayUnit || value?.toString() || '';
};
