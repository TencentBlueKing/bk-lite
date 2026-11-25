export const EMPTY_READING = '暂无数据';
export const NOT_ONBOARDED = '尚未接入采集';
export const COLLECTION_OK = '采集成功';

export type DurationUnit = 'ms' | 's' | 'min';

const trimNumber = (value: number, digits: number) => (
  value.toFixed(digits).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
);

export const pickDurationUnit = (maxAbsMs: number): DurationUnit => {
  if (!(maxAbsMs >= 1000)) return 'ms';
  if (maxAbsMs < 60_000) return 's';
  return 'min';
};

export const formatDuration = (ms: number, unit: DurationUnit) => {
  if (!Number.isFinite(ms)) return EMPTY_READING;
  if (unit === 'ms') {
    const digits = Math.abs(ms) >= 100 || ms === 0 ? 0 : 1;
    return `${trimNumber(ms, digits)} ms`;
  }
  const scaled = unit === 's' ? ms / 1000 : ms / 60_000;
  const suffix = unit === 's' ? '秒' : '分钟';
  return `${trimNumber(scaled, Math.abs(scaled) >= 100 ? 0 : 1)} ${suffix}`;
};

export const formatPerSecond = (value: number, noun: string) => {
  if (!Number.isFinite(value)) return EMPTY_READING;
  const abs = Math.abs(value);
  const digits = abs >= 100 || value === 0 ? 0 : abs >= 10 ? 1 : 2;
  return `${trimNumber(value, digits)} ${noun}/秒`;
};

export const formatCount = (value: number, unit: string) => {
  if (!Number.isFinite(value)) return EMPTY_READING;
  const digits = Math.abs(value) >= 100 || Number.isInteger(value) ? 0 : 1;
  const text = trimNumber(value, digits);
  return unit ? `${text} ${unit}` : text;
};

export const formatPercent = (ratio: number | null) => {
  if (ratio == null || !Number.isFinite(ratio)) return EMPTY_READING;
  return `${trimNumber(ratio * 100, 1)}%`;
};

const BYTE_SCALES = [
  { div: 1, suffix: '字节/秒' },
  { div: 1024, suffix: 'KiB/秒' },
  { div: 1024 ** 2, suffix: 'MiB/秒' },
  { div: 1024 ** 3, suffix: 'GiB/秒' }
] as const;

export const byteScale = (peak: number) => {
  let picked: (typeof BYTE_SCALES)[number] = BYTE_SCALES[0];
  BYTE_SCALES.forEach((scale) => {
    if (peak >= scale.div) picked = scale;
  });
  return picked;
};

export const formatBytesPerSecond = (value: number, scale: { div: number; suffix: string }) => {
  if (!Number.isFinite(value)) return EMPTY_READING;
  const scaled = value / scale.div;
  const abs = Math.abs(scaled);
  const digits = abs >= 100 || scaled === 0 ? 0 : abs >= 10 ? 1 : 2;
  return `${trimNumber(scaled, digits)} ${scale.suffix}`;
};

export const formatPlain = (value: number, suffix = '') => {
  if (!Number.isFinite(value)) return EMPTY_READING;
  const digits = Math.abs(value) >= 100 || Number.isInteger(value) ? 0 : 1;
  const text = trimNumber(value, digits);
  return suffix ? `${text} ${suffix}` : text;
};

export const nonNegativeBounds = (samples: readonly number[], floor: number) => {
  let peak = 0;
  samples.forEach((value) => {
    if (Number.isFinite(value)) peak = Math.max(peak, Math.abs(value));
  });
  return { min: 0, max: Math.max(peak, floor) * 1.1 };
};
