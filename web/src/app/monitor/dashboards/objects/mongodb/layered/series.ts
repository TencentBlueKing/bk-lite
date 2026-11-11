import type { ChartData } from '@/app/monitor/types';
import { formatDuration } from '../../common/simple-dashboard-core';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { deriveRatioPercent, latestNumber, primaryChartSeries } from '../../host/layered/readings';

export type MongoMetricMap = Record<string, {
  loadState: 'success' | 'error';
  viewData: ChartData[];
} | undefined>;

const timeSeconds = (time: number) => (time > 1e11 ? time / 1000 : time);

export const mongoPoints = (metricMap: MongoMetricMap, name: string): ChartData[] => (
  primaryChartSeries(metricMap[name]?.loadState === 'success' ? metricMap[name]?.viewData : [])
    .map((point) => ({ time: timeSeconds(Number(point.time)), value1: point.value1 }))
);

export const mongoLatest = (metricMap: MongoMetricMap, name: string) => (
  latestNumber(metricMap[name])
);

/** 已是百分数。分母为 0 或对不齐的时刻不留点，也不补 0%。 */
export const mongoRatioPoints = (
  metricMap: MongoMetricMap,
  part: string,
  total: string
): ChartData[] => deriveRatioPercent(mongoPoints(metricMap, part), mongoPoints(metricMap, total));

/**
 * 折线右端优先。时间对不齐时，两条都有最新值且分母大于 0，才用最新值配对。
 * 分母为 0 返回 null，调用方显示 —。
 */
export const mongoRatioPercent = (
  metricMap: MongoMetricMap,
  part: string,
  total: string
): number | null => {
  const points = mongoRatioPoints(metricMap, part, total);
  const last = points[points.length - 1];
  if (last && typeof last.value1 === 'number' && Number.isFinite(last.value1)) return last.value1;
  const numerator = mongoLatest(metricMap, part);
  const denominator = mongoLatest(metricMap, total);
  if (numerator == null || denominator == null || !(denominator > 0)) return null;
  return Math.min(100, Math.max(0, (100 * numerator) / denominator));
};

export const formatMongoPercent = (value: number | null) => {
  if (value == null || !Number.isFinite(value)) return '—';
  const formatted = formatMetricValue(value, 'percent');
  return `${formatted.value}${formatted.unit || ''}`;
};

/**
 * 可接纳上限 = 当前连接 + 尚可接纳。只做旁注，不当主读。
 * 缺一侧、非数或出现负数时不给上限。
 */
export const connectionCap = (
  current: number | null,
  available: number | null
): number | null => {
  if (current == null || available == null) return null;
  if (!Number.isFinite(current) || !Number.isFinite(available)) return null;
  if (current < 0 || available < 0) return null;
  return current + available;
};

export type ActiveQueueChartState = 'loading' | 'empty' | 'plot';

/**
 * 活跃与排队。窗口里有点就画折线，四点全是 0 也画。
 * 一个点都没有且还在等 → 加载。都返回了仍无点 → 无数据。
 * 无点不造 0 线。
 */
export const activeQueueChartState = (
  samples: ReadonlyArray<readonly number[]>,
  pending: ReadonlyArray<boolean>
): ActiveQueueChartState => {
  if (samples.some((values) => values.length > 0)) return 'plot';
  if (pending.some(Boolean)) return 'loading';
  return 'empty';
};

/**
 * 全 0 的计数软顶。固定轴会把它画成 0、2、4。
 * 出现非 0 就返回 null，交给按数据的软顶，不再锁 0–4。
 * 没有采样也不锁，避免无点被画成一条 0 轴。
 */
export const activeQueueAxisBounds = (
  samples: readonly number[]
): { min: number; max: number } | null => {
  if (!samples.length) return null;
  let lo = samples[0];
  let hi = samples[0];
  for (let index = 1; index < samples.length; index += 1) {
    const value = samples[index];
    if (value < lo) lo = value;
    if (value > hi) hi = value;
  }
  if (lo === 0 && hi === 0) return { min: 0, max: 4 };
  return null;
};

/** 运行时间来自纳秒读数。没有读数时显示 —，不把缺失写成 0。 */
export const mongoUptimeText = (nanoseconds: number | null) => {
  if (nanoseconds == null || !Number.isFinite(nanoseconds) || nanoseconds < 0) return '—';
  return formatDuration(nanoseconds / 1e9);
};

export const formatMongoReading = (value: number | null, unit: MetricUnit) => {
  if (value == null || !Number.isFinite(value)) return '—';
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

/** 次数。整数，带「次」。 */
export const formatEventCount = (value: number) => `${Math.round(Math.max(0, value))} 次`;

export const mongoMerged = (
  metricMap: MongoMetricMap,
  items: ReadonlyArray<{ name: string; label: string }>
) => mergeChartSeries(items.flatMap((item) => {
  const data = mongoPoints(metricMap, item.name);
  return data.length ? [{ key: item.name, label: item.label, data }] : [];
}));

/** 次数桶。负的外推按 0。没有点不造线。 */
export const mongoCountMerged = (
  metricMap: MongoMetricMap,
  items: ReadonlyArray<{ name: string; label: string }>
) => mergeChartSeries(items.flatMap((item) => {
  const data = mongoPoints(metricMap, item.name).map((point) => ({
    ...point,
    value1: typeof point.value1 === 'number' ? Math.max(0, point.value1) : 0
  }));
  return data.length ? [{ key: item.name, label: item.label, data }] : [];
}));
