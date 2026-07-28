import type { TimeValuesProps } from '@/app/monitor/types';

export interface MetricQueryWindow {
  startMs: number;
  endMs: number;
  xAxisDomain: [number, number];
}

export const createMetricQueryWindow = (
  timeValues: TimeValuesProps,
  nowMs = Date.now()
): MetricQueryWindow | undefined => {
  const relativeMinutes = Number(timeValues.originValue);
  const [explicitStart, explicitEnd] = timeValues.timeRange || [];
  const startMs = relativeMinutes > 0
    ? nowMs - relativeMinutes * 60 * 1000
    : Number(explicitStart);
  const endMs = relativeMinutes > 0 ? nowMs : Number(explicitEnd);

  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
    return undefined;
  }

  return {
    startMs,
    endMs,
    xAxisDomain: [startMs / 1000, endMs / 1000],
  };
};
