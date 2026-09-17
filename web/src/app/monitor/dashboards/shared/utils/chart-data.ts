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
