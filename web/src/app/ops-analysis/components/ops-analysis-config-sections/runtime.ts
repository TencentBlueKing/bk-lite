import type {
  FormatOptions,
  SpecialMatch,
  ThresholdColorConfig,
  UnitCategory,
  UnitFormatResult,
  ValueMapping,
  ValueMappingResult,
} from '@/app/ops-analysis/components/ops-analysis-config-sections/types';

interface UnitStep {
  factor: number;
  suffix: string;
}

interface UnitFamily {
  space: boolean;
  steps: UnitStep[];
}

const IEC = 1024;
const SI = 1000;

const FAMILIES: Record<string, UnitFamily> = {
  bytesIEC: {
    space: true,
    steps: [
      { factor: IEC ** 5, suffix: 'PiB' },
      { factor: IEC ** 4, suffix: 'TiB' },
      { factor: IEC ** 3, suffix: 'GiB' },
      { factor: IEC ** 2, suffix: 'MiB' },
      { factor: IEC, suffix: 'KiB' },
      { factor: 1, suffix: 'B' },
    ],
  },
  bytesSI: {
    space: true,
    steps: [
      { factor: SI ** 5, suffix: 'PB' },
      { factor: SI ** 4, suffix: 'TB' },
      { factor: SI ** 3, suffix: 'GB' },
      { factor: SI ** 2, suffix: 'MB' },
      { factor: SI, suffix: 'KB' },
      { factor: 1, suffix: 'B' },
    ],
  },
  bps: {
    space: true,
    steps: [
      { factor: SI ** 4, suffix: 'Tbps' },
      { factor: SI ** 3, suffix: 'Gbps' },
      { factor: SI ** 2, suffix: 'Mbps' },
      { factor: SI, suffix: 'Kbps' },
      { factor: 1, suffix: 'bps' },
    ],
  },
  ms: {
    space: true,
    steps: [
      { factor: 86400000, suffix: 'd' },
      { factor: 3600000, suffix: 'h' },
      { factor: 60000, suffix: 'm' },
      { factor: 1000, suffix: 's' },
      { factor: 1, suffix: 'ms' },
    ],
  },
  short: {
    space: false,
    steps: [
      { factor: SI ** 4, suffix: 'T' },
      { factor: SI ** 3, suffix: 'B' },
      { factor: SI ** 2, suffix: 'M' },
      { factor: SI, suffix: 'K' },
      { factor: 1, suffix: '' },
    ],
  },
};

const EMPTY_VALUE: UnitFormatResult = { text: '--', value: '--', suffix: '' };

export const DEFAULT_THRESHOLD_COLORS: ThresholdColorConfig[] = [
  { color: '#dc2626', value: '70' },
  { color: '#d97706', value: '30' },
  { color: '#2563eb', value: '0' },
];

export const THRESHOLD_COLOR_PRESETS: Record<string, ThresholdColorConfig[]> = {
  default: DEFAULT_THRESHOLD_COLORS,
  traffic: [
    { color: '#ff4d4f', value: '80' },
    { color: '#faad14', value: '50' },
    { color: '#52c41a', value: '0' },
  ],
  temperature: [
    { color: '#ff7a45', value: '60' },
    { color: '#ffa940', value: '40' },
    { color: '#13c2c2', value: '0' },
  ],
};

const formatNumber = (value: number, decimals?: number): string => {
  if (decimals !== undefined && decimals !== null) {
    return value.toFixed(decimals);
  }

  const rounded = Math.round(value * 100) / 100;
  let formatted = rounded.toFixed(2);
  formatted = formatted.replace(/\.?0+$/, '');
  return formatted === '' || formatted === '-0' ? '0' : formatted;
};

const scaleByFamily = (
  value: number,
  family: UnitFamily,
  decimals?: number,
): { value: string; suffix: string } => {
  const abs = Math.abs(value);
  const step =
    family.steps.find((candidate) => abs >= candidate.factor) ||
    family.steps[family.steps.length - 1];

  return {
    value: formatNumber(value / step.factor, decimals),
    suffix: step.suffix,
  };
};

export const formatUnit = (
  value: number | string | null | undefined,
  unitId?: string,
  opts: FormatOptions = {},
): UnitFormatResult => {
  if (value === null || value === undefined || value === '') {
    return EMPTY_VALUE;
  }

  const numericValue = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(numericValue)) {
    return { text: String(value), value: String(value), suffix: '' };
  }

  const factor = opts.conversionFactor ?? 1;
  const workingValue = numericValue * factor;
  const normalizedUnitId = unitId && unitId.trim() ? unitId.trim() : 'none';

  if (normalizedUnitId === 'percent' || normalizedUnitId === 'percentunit') {
    const percentValue =
      normalizedUnitId === 'percentunit' ? workingValue * 100 : workingValue;
    const formattedValue = formatNumber(percentValue, opts.decimals);
    return { text: `${formattedValue}%`, value: formattedValue, suffix: '%' };
  }

  if (normalizedUnitId === 'none') {
    const formattedValue = formatNumber(workingValue, opts.decimals);
    return { text: formattedValue, value: formattedValue, suffix: '' };
  }

  const family = FAMILIES[normalizedUnitId];
  if (!family) {
    const suffix = normalizedUnitId.startsWith('custom:')
      ? normalizedUnitId.slice('custom:'.length)
      : normalizedUnitId;
    const formattedValue = formatNumber(workingValue, opts.decimals);
    return {
      text: `${formattedValue}${suffix}`,
      value: formattedValue,
      suffix,
    };
  }

  const { value: formattedValue, suffix } = scaleByFamily(
    workingValue,
    family,
    opts.decimals,
  );
  const separator = family.space ? ' ' : '';
  return {
    text: `${formattedValue}${separator}${suffix}`,
    value: formattedValue,
    suffix,
  };
};

export const getUnitCategories = (): UnitCategory[] => [
  {
    key: 'misc',
    label: '通用',
    units: [
      { id: 'none', label: '无单位' },
      { id: 'short', label: '计数（自动 K/M/B）' },
      { id: 'percent', label: '百分比 (0-100)' },
      { id: 'percentunit', label: '百分比 (0.0-1.0)' },
    ],
  },
  {
    key: 'data',
    label: '数据量',
    units: [
      { id: 'bytesIEC', label: '字节 (IEC, 1024)' },
      { id: 'bytesSI', label: '字节 (SI, 1000)' },
    ],
  },
  {
    key: 'throughput',
    label: '速率',
    units: [{ id: 'bps', label: '比特/秒 (bps)' }],
  },
  {
    key: 'time',
    label: '时间',
    units: [{ id: 'ms', label: '毫秒 (自动进位)' }],
  },
];

export const initThresholdColors = (
  colors: ThresholdColorConfig[] | undefined | null,
): ThresholdColorConfig[] => {
  if (colors && Array.isArray(colors)) {
    return [...colors].sort(
      (left, right) => parseFloat(right.value) - parseFloat(left.value),
    );
  }

  return DEFAULT_THRESHOLD_COLORS;
};

export const getColorByThreshold = (
  dataValue: number | string | null | undefined,
  thresholds: ThresholdColorConfig[] = [],
  defaultColor = '#000000',
): string => {
  if (thresholds.length === 0) {
    return defaultColor;
  }

  if (dataValue === null || dataValue === undefined || dataValue === '') {
    return defaultColor;
  }

  const numericValue =
    typeof dataValue === 'string' ? parseFloat(dataValue) : dataValue;
  if (Number.isNaN(numericValue)) {
    return defaultColor;
  }

  const sortedThresholds = [...thresholds].sort(
    (left, right) => parseFloat(right.value) - parseFloat(left.value),
  );

  for (const threshold of sortedThresholds) {
    const thresholdValue = parseFloat(threshold.value);
    if (!Number.isNaN(thresholdValue) && numericValue >= thresholdValue) {
      return threshold.color;
    }
  }

  return sortedThresholds[sortedThresholds.length - 1]?.color || defaultColor;
};

export const validateThresholds = (thresholds: ThresholdColorConfig[]) => {
  const errors: string[] = [];

  thresholds.forEach((threshold, index) => {
    if (!threshold.color || !threshold.color.match(/^#[0-9A-Fa-f]{6}$/)) {
      errors.push(`第${index + 1}个阈值的颜色格式无效`);
    }

    if (Number.isNaN(parseFloat(threshold.value))) {
      errors.push(`第${index + 1}个阈值的数值无效`);
    }
  });

  return {
    isValid: errors.length === 0,
    errors,
  };
};

export const formatDisplayValue = (
  value: number | string | null | undefined,
  unit?: string,
  decimalPlaces?: number,
  conversionFactor?: number,
  unitId?: string,
): string => {
  if (unitId && unitId.trim()) {
    return formatUnit(value, unitId, {
      decimals: decimalPlaces,
      conversionFactor,
    }).text;
  }

  if (value === null || value === undefined || value === '') {
    return '--';
  }

  const numericValue = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(numericValue)) {
    return String(value);
  }

  const factor = conversionFactor !== undefined ? conversionFactor : 1;
  const convertedValue = numericValue * factor;
  let formattedValue =
    decimalPlaces !== undefined
      ? convertedValue.toFixed(decimalPlaces)
      : String(convertedValue);

  if (unit && unit.trim()) {
    formattedValue += unit;
  }

  return formattedValue;
};

export const getValueByPath = (
  obj: unknown,
  path: string | undefined,
): unknown => {
  if (!path || obj === null || obj === undefined) {
    return undefined;
  }

  const normalizedPath = path.replace(/\[(\d+)\]/g, '.$1');
  const keys = normalizedPath.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (current === null || current === undefined) {
      return undefined;
    }

    if (Array.isArray(current)) {
      const index = parseInt(key, 10);
      if (!Number.isNaN(index) && index >= 0 && index < current.length) {
        current = current[index];
        continue;
      }

      current =
        current.length > 0 &&
        current[0] &&
        typeof current[0] === 'object'
          ? (current[0] as Record<string, unknown>)[key]
          : undefined;
      continue;
    }

    if (typeof current === 'object') {
      current = (current as Record<string, unknown>)[key];
      continue;
    }

    return undefined;
  }

  return current;
};

const isEmpty = (value: unknown): boolean => value === '';
const isNull = (value: unknown): boolean => value === null || value === undefined;

const matchSpecial = (raw: unknown, kind?: SpecialMatch): boolean => {
  switch (kind) {
    case 'null':
      return isNull(raw);
    case 'empty':
      return isEmpty(raw);
    case 'nan':
      return (typeof raw === 'number' && Number.isNaN(raw)) || raw === 'NaN';
    case 'true':
      return raw === true || raw === 'true';
    case 'false':
      return raw === false || raw === 'false';
    default:
      return false;
  }
};

const matchRange = (raw: unknown, from?: number, to?: number): boolean => {
  const numericValue = typeof raw === 'number' ? raw : parseFloat(String(raw));
  if (Number.isNaN(numericValue)) return false;
  if (from !== undefined && from !== null && numericValue < from) return false;
  if (to !== undefined && to !== null && numericValue > to) return false;
  return from !== undefined || to !== undefined;
};

const matchRegex = (raw: unknown, pattern?: string): boolean => {
  if (!pattern) return false;

  try {
    return new RegExp(pattern).test(String(raw));
  } catch {
    return false;
  }
};

export const applyValueMapping = (
  raw: unknown,
  mappings?: ValueMapping[],
): ValueMappingResult | null => {
  if (!mappings || mappings.length === 0) return null;

  for (const mapping of mappings) {
    let hit = false;

    switch (mapping.type) {
      case 'value':
        hit = mapping.value !== undefined && String(raw) === mapping.value;
        break;
      case 'range':
        hit = matchRange(raw, mapping.from, mapping.to);
        break;
      case 'regex':
        hit = matchRegex(raw, mapping.pattern);
        break;
      case 'special':
        hit = matchSpecial(raw, mapping.match);
        break;
      default:
        hit = false;
    }

    if (hit) {
      return mapping.result || {};
    }
  }

  return null;
};

export const mapValueText = (
  raw: unknown,
  mappings: ValueMapping[] | undefined,
  fallback: string,
): string => {
  const result = applyValueMapping(raw, mappings);
  return result && result.text !== undefined ? result.text : fallback;
};

export const mapValueColor = (
  raw: unknown,
  mappings: ValueMapping[] | undefined,
): string | undefined => {
  const result = applyValueMapping(raw, mappings);
  return result?.color;
};
