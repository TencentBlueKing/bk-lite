export interface MonitorUnitListItem {
  unit_id: string;
  display_unit: string;
}

const VACANT_UNITS = ['short', 'none', 'counts'];

/** Align with Web `findUnitNameById` in `web/src/app/monitor/hooks/useUnitTransform.ts`. */
export function resolveMonitorUnitLabel(
  value: unknown,
  displayUnit?: string,
  unitList: readonly MonitorUnitListItem[] = [],
): string {
  if (!value || VACANT_UNITS.includes(String(value)) || isSerializedStringArray(value)) {
    return '';
  }

  let display = unitList.find((item) => item.unit_id === value)?.display_unit;
  if (displayUnit) {
    display = displayUnit;
  }
  if (display && VACANT_UNITS.includes(display)) {
    return '';
  }
  return display || String(value) || '';
}

function isSerializedStringArray(input: unknown): input is string {
  try {
    if (typeof input !== 'string') return false;
    const parsed: unknown = JSON.parse(input);
    return Array.isArray(parsed);
  } catch {
    return false;
  }
}
