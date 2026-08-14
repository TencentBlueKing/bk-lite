import {
  formatUnit,
  isAutoScalingUnitId,
} from '@/app/ops-analysis/utils/unitFormat';
import {
  getColorByThreshold,
  isFiniteNumber,
  type ThresholdColorConfig,
} from '@/app/ops-analysis/utils/thresholdUtils';
import {
  applyValueMapping,
  type ValueMapping,
} from '@/app/ops-analysis/utils/valueMapping';

export interface ChartValueFormatConfig {
  unit?: string;
  unitId?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
  valueMappings?: ValueMapping[];
  thresholdColors?: ThresholdColorConfig[];
}

const trimText = (value?: string) => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
};

export const hasValueFormatConfigured = (
  config?: ChartValueFormatConfig,
): boolean => {
  if (!config) return false;
  return (
    Boolean(trimText(config.unitId)) ||
    Boolean(trimText(config.unit)) ||
    isFiniteNumber(config.conversionFactor) ||
    isFiniteNumber(config.decimalPlaces)
  );
};

const resolveUnitId = (config?: ChartValueFormatConfig): string | undefined => {
  const unitId = trimText(config?.unitId);
  if (unitId) return unitId;
  const unit = trimText(config?.unit);
  return unit;
};

const formatOptions = (config?: ChartValueFormatConfig) => ({
  decimals: isFiniteNumber(config?.decimalPlaces)
    ? config.decimalPlaces
    : undefined,
  conversionFactor: isFiniteNumber(config?.conversionFactor)
    ? config.conversionFactor
    : undefined,
});

export const formatVisibleChartValue = (
  value: number | string | null | undefined,
  config?: ChartValueFormatConfig,
): string => {
  if (!hasValueFormatConfigured(config)) {
    if (value === null || value === undefined || value === '') return '--';
    return String(value);
  }
  return formatUnit(value, resolveUnitId(config), formatOptions(config)).text;
};

export const formatLineBarAxisTick = (
  value: number,
  config?: ChartValueFormatConfig,
): string => {
  if (!hasValueFormatConfigured(config)) {
    return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toString();
  }
  const formatted = formatUnit(value, resolveUnitId(config), formatOptions(config));
  if (isAutoScalingUnitId(resolveUnitId(config))) {
    return formatted.text;
  }
  return formatted.value;
};

export const getLineBarYAxisName = (
  config?: ChartValueFormatConfig,
): string | undefined => {
  if (!hasValueFormatConfigured(config)) return undefined;
  const unitId = resolveUnitId(config);
  if (isAutoScalingUnitId(unitId)) return undefined;
  const formatted = formatUnit(1, unitId, formatOptions(config));
  return formatted.suffix || undefined;
};

export const resolveMultiValueRowDisplay = (
  rawValue: string,
  config?: ChartValueFormatConfig,
  defaultColor: string = '#000000',
): { text: string; color: string } => {
  const mapping = applyValueMapping(rawValue, config?.valueMappings);
  const numericValue = parseFloat(rawValue);
  const hasNumericValue = Number.isFinite(numericValue);
  const thresholdColor =
    hasNumericValue && config?.thresholdColors?.length
      ? getColorByThreshold(numericValue, config.thresholdColors, defaultColor)
      : defaultColor;

  if (mapping?.text !== undefined) {
    return {
      text: mapping.text,
      color: mapping.color || thresholdColor,
    };
  }

  const text = hasValueFormatConfigured(config)
    ? formatVisibleChartValue(hasNumericValue ? numericValue : rawValue, config)
    : rawValue;

  return {
    text,
    color: mapping?.color || thresholdColor,
  };
};
