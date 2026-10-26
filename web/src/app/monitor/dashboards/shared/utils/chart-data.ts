import { ChartData } from '@/app/monitor/types';
import { calculateMetrics } from '@/app/monitor/utils/common';

export const getLatestChartValue = (data: ChartData[]) => {
  const latestValue = calculateMetrics(data as Record<string, number>[]).latestValue;
  return typeof latestValue === 'number' ? latestValue : 0;
};

/** 指标最新值命中不可用哨兵（如 H3C 温度 65535）时，返回展示文案；否则 null。 */
export const resolveUnavailableSentinelLabel = (
  value: number,
  sentinels?: number[],
  label = '无传感器'
): string | null => {
  if (!sentinels?.length || !Number.isFinite(value)) return null;
  return sentinels.includes(value) ? label : null;
};

/** 去掉整点取值均为不可用哨兵的时序点，避免趋势图画成 65535 直线。 */
export const stripUnavailableSentinelPoints = (
  data: ChartData[],
  sentinels?: number[]
): ChartData[] => {
  if (!sentinels?.length || !data.length) return data;
  return data.filter((point) => {
    const values = Object.entries(point)
      .filter(([key, value]) => /^value\d+$/.test(key) && typeof value === 'number' && Number.isFinite(value))
      .map(([, value]) => value as number);
    if (!values.length) return false;
    return values.some((value) => !sentinels.includes(value));
  });
};

export const getChartPointSeriesTotal = (point?: ChartData) => {
  if (!point) return 0;
  return Object.entries(point).reduce((sum, [key, value]) => {
    if (!/^value\d+$/.test(key) || typeof value !== 'number' || !Number.isFinite(value)) return sum;
    return sum + value;
  }, 0);
};

export const buildSeriesTotalByTime = (data: ChartData[] = []) => {
  const totals = new Map<number, number>();
  data.forEach((point) => {
    const time = Number(point.time);
    if (!Number.isFinite(time)) return;
    totals.set(time, getChartPointSeriesTotal(point));
  });
  return totals;
};

export const mergeChartSeries = (
  seriesList: Array<{ key: string; label: string; displayName?: string; data: ChartData[] }>
): ChartData[] => {
  const merged = new Map<number, ChartData>();

  seriesList.forEach((series, index) => {
    const valueKey = `value${index + 1}`;
    series.data.forEach((point) => {
      const time = Number(point.time);
      const current = merged.get(time) || { time, title: series.label, details: {} };
      current[valueKey] = getChartPointSeriesTotal(point);
      current.details = current.details || {};
      current.details[valueKey] = [
        { name: series.key, label: series.displayName || '', value: series.displayName || series.label }
      ];
      merged.set(time, current);
    });
  });

  const allValueKeys = seriesList.map((_, index) => `value${index + 1}`);
  const result = Array.from(merged.values()).sort((a, b) => Number(a.time) - Number(b.time));
  result.forEach((point) => {
    allValueKeys.forEach((key) => {
      if (!(key in point)) {
        point[key] = null;
      }
    });
  });

  return result;
};

const positiveDeltas = (points: ChartData[]) => {
  const times = points
    .map((point) => Number(point.time))
    .filter((time) => Number.isFinite(time))
    .sort((left, right) => left - right);
  const deltas: number[] = [];
  for (let index = 1; index < times.length; index += 1) {
    const delta = times[index] - times[index - 1];
    if (delta > 0) deltas.push(delta);
  }
  return deltas;
};

const median = (values: number[]) => {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor((sorted.length - 1) / 2)];
};

/** 采集步长：忽略几秒内的抖动，取稳定间隔的中位数。 */
const seriesStepSeconds = (points: ChartData[]) => {
  const deltas = positiveDeltas(points);
  const stable = deltas.filter((delta) => delta >= 5);
  return median(stable.length ? stable : deltas);
};

const seriesSamples = (points: ChartData[]) => points.flatMap((point) => {
  const time = Number(point.time);
  const value = getChartPointSeriesTotal(point);
  if (!Number.isFinite(time)) return [];
  return [{ time, value }];
}).sort((left, right) => left.time - right.time);

const nearestSampleValue = (
  samples: Array<{ time: number; value: number }>,
  time: number,
  tolerance: number
) => {
  if (!samples.length || tolerance <= 0) return null;
  let low = 0;
  let high = samples.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (samples[mid].time < time) low = mid + 1;
    else high = mid;
  }
  const candidates = [samples[low - 1], samples[low]].filter(
    (sample): sample is { time: number; value: number } => sample != null
  );
  let bestValue: number | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  candidates.forEach((sample) => {
    const distance = Math.abs(sample.time - time);
    if (distance <= tolerance && distance < bestDistance) {
      bestValue = sample.value;
      bestDistance = distance;
    }
  });
  return bestValue;
};

/**
 * 与 mergeChartSeries 相同，但各序列时间戳差在半个采集步长内时互相补值。
 * 分开查询的指标常差几秒，按精确时间戳合并会把已采到的点写成 null，tooltip 就变成 `--`。
 * 超过半步的空档仍留空，不把上一拍的数补到这一拍。
 */
export const mergeChartSeriesAligned = (
  seriesList: Array<{ key: string; label: string; displayName?: string; data: ChartData[] }>
): ChartData[] => {
  const merged = mergeChartSeries(seriesList);
  const steps = seriesList
    .map((series) => seriesStepSeconds(series.data))
    .filter((step): step is number => step != null && step > 0);
  const step = steps.length ? Math.min(...steps) : null;
  const tolerance = step != null ? step / 2 : 30;
  if (tolerance <= 0) return merged;
  const samples = seriesList.map((series) => seriesSamples(series.data));
  merged.forEach((point) => {
    const time = Number(point.time);
    if (!Number.isFinite(time)) return;
    samples.forEach((seriesSamplesAt, index) => {
      const key = `value${index + 1}`;
      const current = point[key];
      if (typeof current === 'number' && Number.isFinite(current)) return;
      const nearest = nearestSampleValue(seriesSamplesAt, time, tolerance);
      if (nearest == null) return;
      point[key] = nearest;
    });
  });
  return merged;
};
