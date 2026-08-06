/** 与 web/src/app/monitor/dashboards/shared/utils/format.ts 对齐的单位格式化。 */
export type MetricUnit =
  | 'none'
  | 'percent'
  | 'counts'
  | 'thousand'
  | 'million'
  | 'billion'
  | 'trillion'
  | 'quadrillion'
  | 'quintillion'
  | 'sextillion'
  | 'septillion'
  | 'bits'
  | 'kilobits'
  | 'megabits'
  | 'gigabits'
  | 'terabits'
  | 'petabits'
  | 'bytes'
  | 'kibibytes'
  | 'mebibytes'
  | 'gibibytes'
  | 'tebibytes'
  | 'pebibytes'
  | 'bitps'
  | 'kbitps'
  | 'mbitps'
  | 'gbitps'
  | 'tbitps'
  | 'pbitps'
  | 'byteps'
  | 'kibyteps'
  | 'mibyteps'
  | 'gibyteps'
  | 'tibyteps'
  | 'pibyteps'
  | 'Bps'
  | 'ns'
  | 'µs'
  | 'us'
  | 'ms'
  | 's'
  | 'm'
  | 'h'
  | 'd'
  | 'cps'
  | 'hertz'
  | 'kilohertz'
  | 'megahertz'
  | 'msps'
  | 'celsius'
  | 'fahrenheit'
  | 'kelvin'
  | 'watts'
  | 'volts'
  | string;

export type MetricPoint = readonly [number, number];

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
  d: 'day',
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

export function formatMetricValue(value: number, unit: MetricUnit = 'none'): { value: string; unit: string } {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  const normalizedUnit = unit === 'Bps' ? 'byteps' : unit;

  if (normalizedUnit === 'percent') return { value: value.toFixed(1), unit: '%' };
  if (normalizedUnit === 'msps') return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: 'ms/s' };
  if (normalizedUnit === 'cps') return formatCountRate(value);
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
    unit: String(normalizedUnit || ''),
  };
}

export function formatMetricDisplay(value: number, unit: MetricUnit = 'none') {
  const formatted = formatMetricValue(value, unit);
  return formatted.unit ? `${formatted.value} ${formatted.unit}` : formatted.value;
}

/** Prometheus 多为秒级时间戳；兼容已是毫秒的值。 */
export function metricTimestampMs(timestamp: number) {
  return timestamp < 1e12 ? timestamp * 1000 : timestamp;
}

export function buildSeriesPath(
  points: ReadonlyArray<MetricPoint>,
  width = 100,
  height = 34,
  padTop = 6,
  padBottom = 4,
) {
  if (points.length < 2) return '';
  const values = points.map((point) => point[1]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const drawable = height - padTop - padBottom;
  return points.map((point, index) => {
    const x = (index / (points.length - 1)) * width;
    const y = padTop + drawable - ((point[1] - min) / span) * drawable;
    return `${index ? 'L' : 'M'} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');
}

export function pickPointByRatio(
  points: ReadonlyArray<MetricPoint>,
  ratio: number,
): { index: number; point: MetricPoint; ratio: number } | null {
  if (!points.length) return null;
  const clamped = Math.min(1, Math.max(0, ratio));
  const index = Math.round(clamped * (points.length - 1));
  const point = points[index];
  if (!point) return null;
  return {
    index,
    point,
    ratio: points.length === 1 ? 0 : index / (points.length - 1),
  };
}

export function valueDomain(points: ReadonlyArray<MetricPoint>) {
  if (!points.length) return { min: 0, max: 1 };
  const values = points.map((point) => point[1]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return { min: min - 1, max: max + 1 };
  return { min, max };
}
