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

/**
 * 单位选择器展示名（级联 / 下拉）。
 * percent/percentunit 的 display_unit 同为 %，名称未标注量纲时补全，避免无法区分 0–100 与 0.0–1.0。
 */
export const getMonitorUnitSelectLabel = (option: {
  unit_id: string;
  unit_name?: string;
  display_unit?: string;
}): string => {
  if (option.unit_id === 'percent') {
    return option.unit_name?.includes('0-100')
      ? option.unit_name
      : 'percent (0-100)';
  }
  if (option.unit_id === 'percentunit') {
    return option.unit_name?.includes('0.0-1.0')
      ? option.unit_name
      : 'percentunit (0.0-1.0)';
  }
  return option.unit_name || option.display_unit || option.unit_id;
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
