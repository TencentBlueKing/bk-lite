import { SegmentedItem, UnitListItem } from '@/app/monitor/types';

export const FORMULA_DEFAULT_RESULT_UNIT = 'percent';

const INVALID_THRESHOLD_UNIT_IDS = new Set(['none', 'short']);

export const resolveInitialMetricPluginId = ({
  type,
  pluginList,
  policyCollectType,
}: {
  type: string;
  pluginList: SegmentedItem[];
  policyCollectType?: string | number | null;
}): string | number | undefined => {
  if (!pluginList.length) return undefined;
  if (!['add', 'builtIn'].includes(type) && policyCollectType) {
    const matched = pluginList.find(
      (item) => String(item.value) === String(policyCollectType)
    );
    if (matched) return matched.value;
  }
  return pluginList[0]?.value;
};

export const getValidThresholdUnitOptions = (
  unitList: UnitListItem[]
): UnitListItem[] =>
  unitList.filter((item) => !INVALID_THRESHOLD_UNIT_IDS.has(item.unit_id));

export const resolveFormulaResultUnit = (
  unit: string | null | undefined,
  unitList: UnitListItem[]
): string => {
  const validUnits = getValidThresholdUnitOptions(unitList);
  const unitIds = new Set(validUnits.map((item) => item.unit_id));

  if (unit && unitIds.has(unit)) {
    return unit;
  }

  return FORMULA_DEFAULT_RESULT_UNIT;
};

export const getThresholdUnitFilterBase = ({
  isFormulaMode,
  formulaResultUnit,
  selectedMetricUnit,
}: {
  isFormulaMode: boolean;
  formulaResultUnit: string | null;
  selectedMetricUnit: string | null;
}): string | null => {
  if (isFormulaMode) {
    return formulaResultUnit || FORMULA_DEFAULT_RESULT_UNIT;
  }
  return selectedMetricUnit;
};

export const getThresholdUnitOptions = ({
  unitList,
  unitFilterBase,
  isEnumMetric,
}: {
  unitList: UnitListItem[];
  unitFilterBase: string | null;
  isEnumMetric: boolean;
}): UnitListItem[] => {
  if (isEnumMetric || !unitFilterBase) return [];

  const validUnits = getValidThresholdUnitOptions(unitList);
  const baseUnit = validUnits.find((item) => item.unit_id === unitFilterBase);
  if (!baseUnit) return [];

  if (baseUnit.system === null) {
    return validUnits.filter((item) => item.unit_id === baseUnit.unit_id);
  }

  return validUnits.filter((item) => item.system === baseUnit.system);
};
