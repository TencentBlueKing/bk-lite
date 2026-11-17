import type { MetricUnit } from '../../../shared/types';

const BYTE_UNITS = ['bytes', 'kibibytes', 'mebibytes', 'gibibytes', 'tebibytes', 'pebibytes'] as const;
const BYTE_LABELS = ['Bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];

/** 列表一行的固定高度。Clerk 和等待 Top 共用，保证行高对齐。 */
export const MSSQL_LIST_ROW_PX = 36;
/** Clerk 图下列表最多露出的行数，再多就在列表内滚动。 */
export const MSSQL_CLERK_VISIBLE_ROWS = 6;
/** 等待类别 Top 的可视行数。左右卡按这个高度对齐。 */
export const MSSQL_WAIT_TOP_VISIBLE_ROWS = 5;
export const MSSQL_CLERK_LIST_MAX_PX = MSSQL_LIST_ROW_PX * MSSQL_CLERK_VISIBLE_ROWS;
export const MSSQL_WAIT_TOP_VIEWPORT = MSSQL_LIST_ROW_PX * MSSQL_WAIT_TOP_VISIBLE_ROWS;

/** 最多两位。整数不补 .00。非整数固定两位，53.599 → 53.60。 */
export function formatMssqlFixed(value: number): string {
  if (!Number.isFinite(value)) return '--';
  const text = value.toFixed(2);
  return text.endsWith('.00') ? text.slice(0, -3) : text;
}

export function mssqlDurationSuffix(peakMs: number): 'ms' | 's' | 'min' {
  const abs = Math.abs(peakMs);
  if (abs >= 60_000) return 'min';
  if (abs >= 1_000) return 's';
  return 'ms';
}

const durationDivisor = (suffix: 'ms' | 's' | 'min') => (
  suffix === 'min' ? 60_000 : suffix === 's' ? 1_000 : 1
);

export function formatMssqlDuration(valueMs: number, peakMs: number): string {
  if (!Number.isFinite(valueMs)) return '--';
  const suffix = mssqlDurationSuffix(peakMs);
  return `${formatMssqlFixed(valueMs / durationDivisor(suffix))} ${suffix}`;
}

function byteScale(unit: MetricUnit, peak: number): { divisor: number; label: string } | null {
  const start = BYTE_UNITS.indexOf(unit as (typeof BYTE_UNITS)[number]);
  if (start < 0) return null;
  let index = start;
  let next = Math.abs(peak);
  while (next >= 1024 && index < BYTE_LABELS.length - 1) {
    next /= 1024;
    index += 1;
  }
  return { divisor: 1024 ** (index - start), label: BYTE_LABELS[index] };
}

export function formatMssqlBytes(value: number, unit: MetricUnit, peak: number): string | null {
  const scale = byteScale(unit, peak);
  if (!scale || !Number.isFinite(value)) return null;
  return `${formatMssqlFixed(value / scale.divisor)} ${scale.label}`;
}

/**
 * 同一张卡按窗口峰值锁一个单位。
 * 毫秒走时长阶梯，字节走 1024。ms/s、次/秒、百分比不锁，调用方继续用原格式。
 */
export function mssqlLockedReading(
  unit: MetricUnit | undefined,
  peak: number
): ((value: number) => string) | null {
  if (!unit || !Number.isFinite(peak)) return null;
  if (unit === 'ms') return (value) => formatMssqlDuration(value, peak);
  if (byteScale(unit, peak)) return (value) => formatMssqlBytes(value, unit, peak) ?? '--';
  return null;
}
