import type { MetricUnit } from '../../../shared/types';
import { formatMetricValue } from '../../../shared/utils/format';

const BYTE_RATE_UNITS = ['byteps', 'kibyteps', 'mibyteps', 'gibyteps', 'tibyteps', 'pibyteps'] as const;
const BYTE_RATE_LABELS = ['Bytes/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s'];
const BIT_RATE_UNITS = ['bitps', 'kbitps', 'mbitps', 'gbitps', 'tbitps', 'pbitps'] as const;
const BIT_RATE_LABELS = ['b/s', 'Kb/s', 'Mb/s', 'Gb/s', 'Tb/s', 'Pb/s'];

/** 与 Y 轴 axisLabel.margin 一致，算左 gutter 时要扣掉。 */
export const FOCUS_AXIS_LABEL_MARGIN = 4;

export interface FocusAxis {
  /** 标题右侧短单位，不含括号。空字符串表示不展示（如活跃会话）。 */
  unitLabel: string;
  formatTick: (value: number) => string;
  /** 绘图区左边距。比带单位时的 44 更窄，把刻度让出的宽度还给折线。 */
  left: number;
  labelMargin: number;
}

const formatAxisNumber = (value: number) => {
  if (!Number.isFinite(value)) return '--';
  const abs = Math.abs(value);
  if (abs >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  return value.toFixed(abs >= 100 ? 0 : 1).replace(/\.0$/, '');
};

let measureCanvas: HTMLCanvasElement | null = null;

const textWidth = (text: string) => {
  if (typeof document === 'undefined') return text.length * 6.2;
  if (!measureCanvas) measureCanvas = document.createElement('canvas');
  const context = measureCanvas.getContext('2d');
  if (!context) return text.length * 6.2;
  context.font = '10px sans-serif';
  return context.measureText(text).width;
};

const withGutter = (
  unitLabel: string,
  formatTick: (value: number) => string,
  samples: number[]
): FocusAxis => {
  const max = samples.reduce((peak, value) => Math.max(peak, Math.abs(value)), 0);
  const probe = max === 0 ? 1 : max;
  const texts = [formatTick(0), formatTick(probe), formatTick(probe * 1.2)];
  const width = texts.reduce((peak, text) => Math.max(peak, textWidth(text)), 0);
  const left = Math.max(22, Math.ceil(width) + FOCUS_AXIS_LABEL_MARGIN + 4);
  return {
    unitLabel,
    formatTick,
    left,
    labelMargin: FOCUS_AXIS_LABEL_MARGIN
  };
};

const lockScale = (
  startIndex: number,
  labels: readonly string[],
  base: number,
  samples: number[]
) => {
  const max = samples.reduce((peak, value) => Math.max(peak, Math.abs(value)), 0);
  let next = max;
  let index = Math.max(0, startIndex);
  while (next >= base && index < labels.length - 1) {
    next /= base;
    index += 1;
  }
  const divisor = base ** (index - Math.max(0, startIndex));
  return {
    unitLabel: labels[index] || '',
    formatTick: (value: number) => formatAxisNumber(value / divisor)
  };
};

export const seriesSampleValues = (data: ReadonlyArray<Record<string, unknown>>): number[] => {
  const values: number[] = [];
  data.forEach((point) => {
    Object.keys(point).forEach((key) => {
      if (!key.startsWith('value')) return;
      const value = point[key];
      if (typeof value === 'number' && Number.isFinite(value)) values.push(value);
    });
  });
  return values;
};

/**
 * 标题右侧单位。空串、空白和空括号都不占位，避免写出 `()`。
 * 括号只包一层，调用方传入 `次/秒` 或 `%` 即可。
 */
export const formatFocusUnitText = (unit: string | null | undefined) => {
  const bare = (unit ?? '').trim().replace(/^\(+/, '').replace(/\)+$/, '').trim();
  return bare ? `(${bare})` : '';
};

/** 重点关注大数字：与 Y 轴同一把尺，只留数字。 */
export const formatFocusHeadline = (
  axis: FocusAxis,
  value: number | null | undefined
) => {
  if (value == null || !Number.isFinite(value)) return '--';
  return axis.formatTick(value);
};

/**
 * 重点关注 spark：刻度与主值只留数字，单位只在标题括号里出现一次。
 * 百分比、速率的单位固定；字节速率按整段最大值锁一个刻度，主值跟同一把尺。
 */
export const describeFocusAxis = (unit: MetricUnit, samples: number[]): FocusAxis => {
  const normalized = unit === 'Bps' ? 'byteps' : unit;

  if (normalized === 'percent' || normalized === 'percentunit') {
    return withGutter('%', (value) => formatMetricValue(value, normalized).value, samples);
  }

  if (normalized === 'cps' || normalized === 'pps') {
    return withGutter('次/秒', (value) => formatMetricValue(value, normalized).value, samples);
  }

  if (normalized === 'none') {
    return withGutter('', (value) => formatMetricValue(value, 'none').value, samples);
  }

  if (normalized === 'counts') {
    return withGutter('', formatAxisNumber, samples);
  }

  const byteIndex = BYTE_RATE_UNITS.indexOf(normalized as (typeof BYTE_RATE_UNITS)[number]);
  if (byteIndex >= 0) {
    const locked = lockScale(byteIndex, BYTE_RATE_LABELS, 1024, samples);
    return withGutter(locked.unitLabel, locked.formatTick, samples);
  }

  const bitIndex = BIT_RATE_UNITS.indexOf(normalized as (typeof BIT_RATE_UNITS)[number]);
  if (bitIndex >= 0) {
    const locked = lockScale(bitIndex, BIT_RATE_LABELS, 1000, samples);
    return withGutter(locked.unitLabel, locked.formatTick, samples);
  }

  const peak = samples.reduce((max, value) => Math.max(max, Math.abs(value)), 1);
  const sample = formatMetricValue(peak, normalized);
  return withGutter(sample.unit, (value) => formatMetricValue(value, normalized).value, samples);
};
