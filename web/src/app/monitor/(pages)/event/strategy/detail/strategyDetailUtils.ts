import {
  CascaderItem,
  GroupedUnitList,
  MetricItem,
  SegmentedItem,
  UnitListItem
} from '@/app/monitor/types';
import { isStringArray } from '@/app/monitor/utils/common';
import { MetricExpressionMode } from './formulaExpressionUtils';

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
): string | null => {
  const validUnits = getValidThresholdUnitOptions(unitList);
  if (!validUnits.length) {
    // 契约:单位表未就绪时,绝不硬塞默认单位
    return null;
  }
  const unitIds = new Set(validUnits.map((item) => item.unit_id));

  if (unit && unitIds.has(unit)) {
    return unit;
  }

  return FORMULA_DEFAULT_RESULT_UNIT;
};

export const getCalculationUnitOnMetricRowsChange = ({
  previousMode,
  nextMode,
  currentCalculationUnit,
  unitList,
}: {
  previousMode: MetricExpressionMode;
  nextMode: MetricExpressionMode;
  currentCalculationUnit: string | null;
  unitList: UnitListItem[];
}): string | null => {
  if (nextMode !== 'formula') {
    return currentCalculationUnit;
  }

  // 单位表未就绪:
  //  - 首次进入 formula 时返回 null,让 UI 提示用户重选
  //  - 已在 formula 模式时保留用户已选值,避免在 unitList 抖动时被覆盖
  if (!getValidThresholdUnitOptions(unitList).length) {
    return previousMode === 'formula' ? currentCalculationUnit : null;
  }

  if (previousMode !== 'formula') {
    return FORMULA_DEFAULT_RESULT_UNIT;
  }

  return resolveFormulaResultUnit(currentCalculationUnit, unitList);
};

interface EnumOption {
  id: number;
  name: string;
  color?: string;
}

// 内部 JSON 解析:对脏数据(非 JSON / 非数组 / 缺 id/name / id 非法)统一兜底成空数组,
// 避免渲染层因为 key=NaN 或 name=[object Object] 抛错。
const parseEnumOptions = (input: string): EnumOption[] => {
  try {
    const parsed: unknown = JSON.parse(input);
    if (!Array.isArray(parsed)) return [];
    const out: EnumOption[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const idNum = Number((item as { id: unknown }).id);
      const name = (item as { name: unknown }).name;
      if (!Number.isFinite(idNum)) continue;
      if (typeof name !== 'string' || !name) continue;
      const color = (item as { color?: unknown }).color;
      out.push({
        id: idNum,
        name,
        ...(typeof color === 'string' ? { color } : {})
      });
    }
    return out;
  } catch {
    return [];
  }
};

export const getMetricThresholdEnumState = ({
  isFormulaMode,
  metricUnit,
}: {
  isFormulaMode: boolean;
  metricUnit: string | null;
}): {
  isEnumMetric: boolean;
  enumOptions: EnumOption[];
} => {
  // 公式模式:阈值永远用数字,即使 metricUnit 形态上是枚举也忽略
  if (isFormulaMode || !metricUnit || !isStringArray(metricUnit)) {
    return {
      isEnumMetric: false,
      enumOptions: []
    };
  }

  const options = parseEnumOptions(metricUnit);
  return {
    isEnumMetric: options.length > 0,
    enumOptions: options
  };
};

export const shouldShowThresholdUnitSelector = ({
  isFormulaMode,
  isEnumMetric
}: {
  isFormulaMode: boolean;
  isEnumMetric: boolean;
}): boolean => !isFormulaMode && !isEnumMetric;

export const getThresholdUnitOptions = ({
  unitList,
  metricUnit,
  isEnumMetric,
}: {
  unitList: UnitListItem[];
  metricUnit: string | null;
  isEnumMetric: boolean;
}): UnitListItem[] => {
  if (isEnumMetric || !metricUnit) return [];

  const validUnits = getValidThresholdUnitOptions(unitList);
  const baseUnit = validUnits.find((item) => item.unit_id === metricUnit);
  if (!baseUnit) return [];

  if (baseUnit.system === null) {
    return validUnits.filter((item) => item.unit_id === baseUnit.unit_id);
  }

  return validUnits.filter((item) => item.system === baseUnit.system);
};

export const resolveThresholdUnit = ({
  thresholdUnit,
  calculationUnit,
  unitList,
}: {
  thresholdUnit: string | null | undefined;
  calculationUnit: string | null | undefined;
  unitList: UnitListItem[];
}): string | null => {
  // 单位表尚未加载时保留接口中的历史值，避免初始化过程误覆盖。
  if (!unitList.length) return thresholdUnit || calculationUnit || null;
  if (!calculationUnit) return thresholdUnit || null;

  const options = getThresholdUnitOptions({
    unitList,
    metricUnit: calculationUnit,
    isEnumMetric: false,
  });
  if (thresholdUnit && options.some((item) => item.unit_id === thresholdUnit)) {
    return thresholdUnit;
  }
  return options.some((item) => item.unit_id === calculationUnit)
    ? calculationUnit
    : null;
};

export const getThresholdUnitOnCalculationUnitChange = resolveThresholdUnit;

// 把 groupedUnitList (按 category 分组) 转为 Cascader 选项;
// 一级 value = category 名,二级 value = unit_id,二级为叶子节点需 children=[] 以满足 CascaderItem 递归类型。
// 单位表规模小 (<100),即便 O(N×M) 也可接受。
export const buildMetricUnitCascaderOptions = (
  groupedUnitList: GroupedUnitList[]
): CascaderItem[] =>
  groupedUnitList
    .map((group) => ({
      label: group.label,
      value: group.label,
      children: (group.children || [])
        .filter((item) => !INVALID_THRESHOLD_UNIT_IDS.has(item.value))
        .map((item) => ({
          label: item.label,
          value: item.value,
          children: []
        }))
    }))
    .filter((group) => group.children.length > 0);

export const resolveMetricDisplayUnit = (
  unit: string | null | undefined,
  unitList: UnitListItem[]
): string => {
  if (!unit || INVALID_THRESHOLD_UNIT_IDS.has(unit) || isStringArray(unit)) {
    return '';
  }

  return unitList.find((item) => item.unit_id === unit)?.display_unit || '';
};

export const buildMetricSelectOption = (
  metric: MetricItem,
  unitList: UnitListItem[]
): { label: string; value: string } => {
  const displayName = metric.display_name || metric.name;
  const displayUnit = resolveMetricDisplayUnit(metric.unit, unitList);
  return {
    label: displayUnit ? `${displayName}（${displayUnit}）` : displayName,
    value: metric.name
  };
};

// 现有 page.tsx 的 filterInvalidUnit 逻辑上提到 utils(行为完全一致,签名兼容)
export const filterInvalidCalculationUnit = (
  unit: string | null | undefined
): string | null => {
  if (!unit || unit === 'none' || unit === 'short' || isStringArray(unit)) {
    return null;
  }
  return unit;
};

export const restoreCalculationUnitState = (
  unit: string | null | undefined
): string | null => filterInvalidCalculationUnit(unit);

export const resolveEffectiveCalculationUnit = ({
  isFormulaMode,
  unit,
  unitList
}: {
  isFormulaMode: boolean;
  unit: string | null | undefined;
  unitList: UnitListItem[];
}): string | null => {
  if (isFormulaMode) {
    return resolveFormulaResultUnit(unit, unitList);
  }

  const normalizedUnit = filterInvalidCalculationUnit(unit);
  if (!normalizedUnit) return null;

  return getValidThresholdUnitOptions(unitList).some(
    (item) => item.unit_id === normalizedUnit
  )
    ? normalizedUnit
    : null;
};

// 公式 → 单指标 retract:返回新值;否则返回 undefined 表示「无变化」
export const getReverseModeCalculationUnit = ({
  previousMode,
  nextMode,
  primaryMetricUnit,
}: {
  previousMode: MetricExpressionMode;
  nextMode: MetricExpressionMode;
  primaryMetricUnit: string | null | undefined;
}): string | null | undefined => {
  if (previousMode === 'formula' && nextMode !== 'formula') {
    return filterInvalidCalculationUnit(primaryMetricUnit);
  }
  return undefined;
};
