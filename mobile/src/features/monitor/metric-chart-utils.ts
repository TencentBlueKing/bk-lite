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

export type MetricPoint = readonly [number, number | null];

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
  timeWindow?: { startMs: number; endMs: number } | null,
) {
  // 与 Web mini-trend 对齐：卡片只看有效点，缺口不断开，保证有数据时能看见趋势线。
  const finite = points.flatMap((point) => (
    point[1] === null || !Number.isFinite(point[1]) ? [] : [[point[0], point[1]] as const]
  ));
  if (finite.length < 2) return '';
  const values = finite.map((point) => point[1]);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  // 与 Web mini-trend `padding = (max-min)*0.15 || 1` 对齐，避免常量序列贴底。
  const valuePadding = (dataMax - dataMin) * 0.15 || 1;
  const yMin = dataMin - valuePadding;
  const yMax = dataMax + valuePadding;
  const valueSpan = yMax - yMin;
  const drawable = height - padTop - padBottom;
  const times = finite.map((point) => metricTimestampMs(point[0]));
  const dataMinTime = Math.min(...times);
  const dataMaxTime = Math.max(...times);
  const windowStart = timeWindow && Number.isFinite(timeWindow.startMs) ? timeWindow.startMs : dataMinTime;
  const windowEnd = timeWindow && Number.isFinite(timeWindow.endMs) && timeWindow.endMs > windowStart
    ? timeWindow.endMs
    : Math.max(dataMaxTime, dataMinTime + 1);
  const timeSpan = Math.max(windowEnd - windowStart, 1);
  return finite.map((point, index) => {
    const x = ((metricTimestampMs(point[0]) - windowStart) / timeSpan) * width;
    const y = padTop + drawable - ((point[1] - yMin) / valueSpan) * drawable;
    const command = index === 0 ? 'M' : 'L';
    return `${command} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');
}

/** 卡片 sparkline：全局仅 1 个有效点时画圆点（对齐 Web mini-trend showSymbol）。 */
export function buildSeriesSinglePoint(
  points: ReadonlyArray<MetricPoint>,
  width = 100,
  height = 34,
  padTop = 6,
  padBottom = 4,
): { cx: number; cy: number } | null {
  const finite = points.flatMap((point) => (
    point[1] === null || !Number.isFinite(point[1]) ? [] : [[point[0], point[1]] as const]
  ));
  if (finite.length !== 1) return null;
  const drawable = height - padTop - padBottom;
  return {
    cx: width / 2,
    cy: padTop + drawable / 2,
  };
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
  const values = points.flatMap((point) => point[1] === null ? [] : [point[1]]);
  if (!values.length) return { min: 0, max: 1 };
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return { min: min - 1, max: max + 1 };
  return { min, max };
}

/** 与 web lineChart.getNiceStep 对齐：1/2/5×10ⁿ 步长。 */
export function getMetricNiceStep(rawStep: number) {
  if (!Number.isFinite(rawStep) || rawStep <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  if (normalized <= 1) return magnitude;
  if (normalized <= 2) return 2 * magnitude;
  if (normalized <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

/**
 * 与 web lineChart Y 轴 domain 对齐：数据 min/max + ~12% padding，
 * 非负数据夹到 ≥0，全 0 → [0, 1]。
 */
export function buildMetricYAxisDomain(values: ReadonlyArray<number>): [number, number] {
  if (!values.length) return [0, 1];
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const dataSpan = dataMax - dataMin;
  const basePadding = dataSpan > 0
    ? dataSpan * 0.12
    : Math.max(Math.abs(dataMax || dataMin) * 0.18, 0.6);
  let yMin = dataMin - basePadding;
  let yMax = dataMax + basePadding;

  if (dataMin >= 0) {
    yMin = Math.max(0, yMin);
  }

  if (dataSpan === 0) {
    if (dataMax === 0) {
      return [0, 1];
    }
    yMin = Math.max(dataMin >= 0 ? 0 : dataMin - basePadding, dataMin - basePadding);
    yMax = dataMax + basePadding;
  }

  return [yMin, yMax];
}

/** 与 web lineChart.buildNiceAxis 对齐。 */
export function buildMetricNiceAxis(
  rawDomain: readonly [number, number],
  tickCount = 3,
): { domain: [number, number]; ticks: number[]; interval: number } {
  const [rawMin, rawMax] = rawDomain;
  const minValue = Number.isFinite(rawMin) ? rawMin : 0;
  const maxValue = Number.isFinite(rawMax) ? rawMax : minValue + 1;
  const span = Math.max(maxValue - minValue, 1e-6);
  const step = getMetricNiceStep(span / Math.max(tickCount - 1, 1));

  let niceMin = Math.floor(minValue / step) * step;
  let niceMax = Math.ceil(maxValue / step) * step;

  if (minValue >= 0) {
    niceMin = Math.max(0, niceMin);
  }

  if (niceMax <= niceMin) {
    niceMax = niceMin + step;
  }

  const ticks: number[] = [];
  for (let current = niceMin; current <= niceMax + step / 2; current += step) {
    ticks.push(Number(current.toFixed(10)));
  }

  return {
    domain: [niceMin, niceMax],
    ticks,
    interval: step,
  };
}

/** 与 web lineChart.formatAxisNumber 对齐：Y 轴刻度只显示数字，单位放在标题。 */
export function formatMetricAxisNumber(value: number) {
  if (!Number.isFinite(value)) return '';
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (Number.isInteger(value)) return `${value}`;
  return value.toFixed(2).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1');
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * 与 web useFormatTime 按所选时间窗跨度选格式对齐（入参为毫秒跨度）。
 * ≤1 天 HH:mm:ss；≤30 天 MM-DD HH:mm；≤1 年 YYYY-MM-DD；更长 YYYY-MM。
 */
export function metricAxisTimeOptions(spanMs: number): Intl.DateTimeFormatOptions {
  if (!Number.isFinite(spanMs) || spanMs <= 0) {
    return { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' };
  }
  if (spanMs <= DAY_MS) {
    return { hour: '2-digit', minute: '2-digit', second: '2-digit' };
  }
  if (spanMs <= 30 * DAY_MS) {
    return { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' };
  }
  if (spanMs <= 365 * DAY_MS) {
    return { year: 'numeric', month: '2-digit', day: '2-digit' };
  }
  return { year: 'numeric', month: '2-digit' };
}
