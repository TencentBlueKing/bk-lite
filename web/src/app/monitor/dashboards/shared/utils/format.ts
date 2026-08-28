import { CompareFavorableDirection, MetricEnumMap, MetricUnit } from '../types';

const COUNT_UNITS: MetricUnit[] = ['counts', 'thousand', 'million', 'billion', 'trillion', 'quadrillion', 'quintillion', 'sextillion', 'septillion'];
const COUNT_LABELS = ['', 'K', 'Mil', 'Bil', 'Tri', 'Quadr', 'Quint', 'Sext', 'Sept'];
const DATA_BITS_UNITS: MetricUnit[] = ['bits', 'kilobits', 'megabits', 'gigabits', 'terabits', 'petabits'];
const DATA_BITS_LABELS = ['b', 'Kb', 'Mb', 'Gb', 'Tb', 'Pb'];
const DATA_BYTES_UNITS: MetricUnit[] = ['bytes', 'kibibytes', 'mebibytes', 'gibibytes', 'tebibytes', 'pebibytes'];
const DATA_BYTES_LABELS = ['Bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
const DATA_RATE_BITS_UNITS: MetricUnit[] = ['bitps', 'kbitps', 'mbitps', 'gbitps', 'tbitps', 'pbitps'];
const DATA_RATE_BITS_LABELS = ['b/s', 'Kb/s', 'Mb/s', 'Gb/s', 'Tb/s', 'Pb/s'];
const DATA_RATE_BYTES_UNITS: MetricUnit[] = ['byteps', 'kibyteps', 'mibyteps', 'gibyteps', 'tibyteps', 'pibyteps'];
const DATA_RATE_BYTES_LABELS = ['Bytes/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s'];
const HERTZ_UNITS: MetricUnit[] = ['hertz', 'kilohertz', 'megahertz'];
const HERTZ_LABELS = ['Hz', 'KHz', 'MHz'];
const TIME_UNITS = ['ns', 'µs', 'ms', 's', 'm', 'h', 'd'] as const;
const TIME_LABELS: Record<(typeof TIME_UNITS)[number], string> = {
  ns: 'ns',
  'µs': 'µs',
  ms: 'ms',
  s: 's',
  m: 'min',
  h: 'hour',
  d: 'day'
};

const formatScaledValue = (value: number) => (
  value >= 1000
    ? value.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : value.toFixed(value >= 100 ? 0 : 1).replace(/\.0$/, '')
);

const formatAutoScaled = (
  value: number,
  unit: MetricUnit,
  units: readonly MetricUnit[],
  labels: readonly string[],
  base: number
) => {
  const startIndex = units.indexOf(unit);
  if (startIndex === -1) {
    return { value: formatScaledValue(value), unit: String(unit || '') };
  }

  let next = value;
  let index = startIndex;
  while (Math.abs(next) >= base && index < units.length - 1) {
    next /= base;
    index += 1;
  }

  return {
    value: formatScaledValue(next),
    unit: labels[index]
  };
};

const formatTimeValue = (value: number, unit: MetricUnit) => {
  const normalizedUnit = unit === 'us' ? 'µs' : unit;
  const startIndex = TIME_UNITS.indexOf(normalizedUnit as (typeof TIME_UNITS)[number]);
  if (startIndex === -1) {
    return { value: formatScaledValue(value), unit: String(unit || '') };
  }

  let next = value;
  let index = startIndex;

  while (index < 2 && Math.abs(next) >= 1000) {
    next /= 1000;
    index += 1;
  }

  if (index === 3) {
    if (Math.abs(next) >= 86400) {
      const days = Math.floor(next / 86400);
      const hours = Math.floor((next % 86400) / 3600);
      return { value: `${days}${hours > 0 ? `d ${hours}h` : 'd'}`, unit: '' };
    }
    if (Math.abs(next) >= 3600) {
      return { value: (next / 3600).toFixed(Math.abs(next) >= 36000 ? 0 : 1).replace(/\.0$/, ''), unit: TIME_LABELS.h };
    }
    if (Math.abs(next) >= 60) {
      return { value: (next / 60).toFixed(Math.abs(next) >= 600 ? 0 : 1).replace(/\.0$/, ''), unit: TIME_LABELS.m };
    }
  }

  return {
    value: formatScaledValue(next),
    unit: TIME_LABELS[TIME_UNITS[index]]
  };
};

const formatCountRate = (value: number): { value: string; unit: string } => {
  const abs = Math.abs(value);
  if (abs < 1000) {
    return { value: abs >= 100 ? value.toFixed(0) : value.toFixed(2), unit: '/s' };
  }
  const scaled = formatAutoScaled(value, 'counts', COUNT_UNITS, COUNT_LABELS, 1000);
  return { value: `${scaled.value}${scaled.unit}`, unit: '/s' };
};

export const formatSamplingRate = (value: number): { value: string; unit: string } => {
  if (!Number.isFinite(value) || value <= 0) {
    return { value: '--', unit: '' };
  }
  const rounded = Math.round(value);
  return {
    value: `1:${rounded.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
    unit: '',
  };
};

export const formatMetricValue = (value: number, unit: MetricUnit): { value: string; unit: string } => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  const normalizedUnit = unit === 'Bps' ? 'byteps' : unit;

  if (normalizedUnit === 'percent') return { value: value.toFixed(1), unit: '%' };
  if (normalizedUnit === 'msps') return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: 'ms/s' };
  if (normalizedUnit === 'cps' || normalizedUnit === 'pps') return formatCountRate(value);
  if (COUNT_UNITS.includes(normalizedUnit)) return formatAutoScaled(value, normalizedUnit, COUNT_UNITS, COUNT_LABELS, 1000);
  if (DATA_BITS_UNITS.includes(normalizedUnit)) return formatAutoScaled(value, normalizedUnit, DATA_BITS_UNITS, DATA_BITS_LABELS, 1000);
  if (DATA_BYTES_UNITS.includes(normalizedUnit)) return formatAutoScaled(value, normalizedUnit, DATA_BYTES_UNITS, DATA_BYTES_LABELS, 1024);
  if (DATA_RATE_BITS_UNITS.includes(normalizedUnit)) return formatAutoScaled(value, normalizedUnit, DATA_RATE_BITS_UNITS, DATA_RATE_BITS_LABELS, 1000);
  if (DATA_RATE_BYTES_UNITS.includes(normalizedUnit)) return formatAutoScaled(value, normalizedUnit, DATA_RATE_BYTES_UNITS, DATA_RATE_BYTES_LABELS, 1024);
  if ((TIME_UNITS as readonly string[]).includes(normalizedUnit)) return formatTimeValue(value, normalizedUnit);
  if (normalizedUnit === 'us') return formatTimeValue(value, 'µs');
  if (HERTZ_UNITS.includes(normalizedUnit)) return formatAutoScaled(value, normalizedUnit, HERTZ_UNITS, HERTZ_LABELS, 1000);
  if (normalizedUnit === 'celsius') return { value: formatScaledValue(value), unit: '°C' };
  if (normalizedUnit === 'fahrenheit') return { value: formatScaledValue(value), unit: '°F' };
  if (normalizedUnit === 'kelvin') return { value: formatScaledValue(value), unit: 'K' };
  if (normalizedUnit === 'watts') return { value: formatScaledValue(value), unit: 'W' };
  if (normalizedUnit === 'volts') return { value: formatScaledValue(value), unit: 'V' };

  if (normalizedUnit === 'none') {
    return { value: value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1'), unit: '' };
  }

  return {
    value: formatScaledValue(value),
    unit: String(normalizedUnit || '')
  };
};

export const formatEnumValue = (value: number, enumMap?: MetricEnumMap) => {
  if (!Number.isFinite(value) || !enumMap) {
    return { value: '--', color: undefined as string | undefined };
  }

  // 优先精确匹配（如端口部分失活 0.5），避免 Math.round(0.5)→1 误映射为存活。
  const exactMatch = enumMap[value];
  if (exactMatch) {
    return { value: exactMatch.label, color: exactMatch.color };
  }

  const normalizedValue = Math.round(value);
  const match = enumMap[normalizedValue];
  if (match) {
    return { value: match.label, color: match.color };
  }

  // 枚举失配（常见于 mock 用连续浮点冒充 0/1）：显示「未知」，禁止退化成裸数字误导。
  return {
    value: '未知',
    color: '#8c95a8'
  };
};

export const getCompareTone = (
  direction: 'up' | 'down' | 'flat',
  favorableDirection: CompareFavorableDirection = 'down'
) => {
  if (direction === 'flat') return 'flat';
  return direction === favorableDirection ? 'negative' : 'positive';
};
