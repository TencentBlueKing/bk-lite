import type { ListItem } from '@/types';
import type {
  CollectionStatusResult,
  CompareFavorableDirection,
  GapInterval,
  MetricEnumMap,
  MetricUnit,
} from '@/app/monitor/components/monitor-dashboard-widgets/types';

const COUNT_UNITS: MetricUnit[] = ['counts', 'thousand', 'million', 'billion', 'trillion', 'quadrillion', 'quintillion', 'sextillion', 'septillion'];
const COUNT_LABELS = ['', 'K', 'Mil', 'Bil', 'Tri', 'Quadr', 'Quint', 'Sext', 'Sept'];
const DATA_BITS_UNITS: MetricUnit[] = ['bits', 'kilobits', 'megabits', 'gigabits', 'terabits', 'petabits'];
const DATA_BITS_LABELS = ['b', 'Kb', 'Mb', 'Gb', 'Tb', 'Pb'];
const DATA_BYTES_UNITS: MetricUnit[] = ['bytes', 'kibibytes', 'mebibytes', 'gibibytes', 'tebibytes', 'pebibytes'];
const DATA_BYTES_LABELS = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
const DATA_RATE_BITS_UNITS: MetricUnit[] = ['bitps', 'kbitps', 'mbitps', 'gbitps', 'tbitps', 'pbitps'];
const DATA_RATE_BITS_LABELS = ['b/s', 'Kb/s', 'Mb/s', 'Gb/s', 'Tb/s', 'Pb/s'];
const DATA_RATE_BYTES_UNITS: MetricUnit[] = ['byteps', 'kibyteps', 'mibyteps', 'gibyteps', 'tibyteps', 'pibyteps'];
const DATA_RATE_BYTES_LABELS = ['B/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s'];
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
  d: 'day',
};

export const COLLECTION_STATUS_SEGMENT_COUNT = 18;

export const COLLECTION_STATUS_LEGEND = [
  { key: 'success' as const, label: '正常', color: '#22c55e' },
  { key: 'empty' as const, label: '无数据', color: '#cbd5e1' },
  { key: 'error' as const, label: '异常', color: '#ff4d4f' },
];

export const DEFAULT_REFRESH_FREQUENCY_LIST: ListItem[] = [
  { label: '关闭', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '2m', value: 120000 },
  { label: '5m', value: 300000 },
  { label: '10m', value: 600000 },
];

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
  base: number,
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
    unit: labels[index],
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
    unit: TIME_LABELS[TIME_UNITS[index]],
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

export const formatMetricValue = (value: number, unit: MetricUnit): { value: string; unit: string } => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  if (unit === 'percent') return { value: value.toFixed(1), unit: '%' };
  if (unit === 'msps') return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: 'ms/s' };
  if (unit === 'cps') return formatCountRate(value);
  if (COUNT_UNITS.includes(unit)) return formatAutoScaled(value, unit, COUNT_UNITS, COUNT_LABELS, 1000);
  if (DATA_BITS_UNITS.includes(unit)) return formatAutoScaled(value, unit, DATA_BITS_UNITS, DATA_BITS_LABELS, 1000);
  if (DATA_BYTES_UNITS.includes(unit)) return formatAutoScaled(value, unit, DATA_BYTES_UNITS, DATA_BYTES_LABELS, 1024);
  if (DATA_RATE_BITS_UNITS.includes(unit)) return formatAutoScaled(value, unit, DATA_RATE_BITS_UNITS, DATA_RATE_BITS_LABELS, 1000);
  if (DATA_RATE_BYTES_UNITS.includes(unit)) return formatAutoScaled(value, unit, DATA_RATE_BYTES_UNITS, DATA_RATE_BYTES_LABELS, 1024);
  if ((TIME_UNITS as readonly string[]).includes(unit)) return formatTimeValue(value, unit);
  if (unit === 'us') return formatTimeValue(value, 'µs');
  if (HERTZ_UNITS.includes(unit)) return formatAutoScaled(value, unit, HERTZ_UNITS, HERTZ_LABELS, 1000);
  if (unit === 'celsius') return { value: formatScaledValue(value), unit: '°C' };
  if (unit === 'fahrenheit') return { value: formatScaledValue(value), unit: '°F' };
  if (unit === 'kelvin') return { value: formatScaledValue(value), unit: 'K' };
  if (unit === 'watts') return { value: formatScaledValue(value), unit: 'W' };
  if (unit === 'volts') return { value: formatScaledValue(value), unit: 'V' };

  if (unit === 'none') {
    return { value: value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1'), unit: '' };
  }

  return {
    value: formatScaledValue(value),
    unit: String(unit || ''),
  };
};

export const formatEnumValue = (value: number, enumMap?: MetricEnumMap) => {
  if (!Number.isFinite(value) || !enumMap) {
    return { value: '--', color: undefined as string | undefined };
  }

  const normalizedValue = Math.round(value);
  const match = enumMap[normalizedValue];
  if (match) {
    return { value: match.label, color: match.color };
  }

  return {
    value: formatMetricValue(value, 'none').value,
    color: undefined,
  };
};

export const getCompareTone = (
  direction: 'up' | 'down' | 'flat',
  favorableDirection: CompareFavorableDirection = 'down',
) => {
  if (direction === 'flat') return 'flat';
  return direction === favorableDirection ? 'negative' : 'positive';
};

export const normalizeCollectionStatus = (
  status: CollectionStatusResult,
): CollectionStatusResult => status;

export const normalizeGapIntervals = (gaps: GapInterval[] = []): GapInterval[] => {
  return gaps
    .map((gap) => ({
      ...gap,
      start: Number(gap.start),
      end: Number(gap.end),
    }))
    .filter(
      (gap) =>
        Number.isFinite(gap.start) &&
        Number.isFinite(gap.end) &&
        gap.end >= gap.start,
    );
};
