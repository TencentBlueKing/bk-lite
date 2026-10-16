import type { TimeValuesProps } from '@/app/monitor/types';

/** 实例 + 时间选择（不是 freeze 后的绝对窗）。切 Tab 不换这个键。 */
export const dashboardDatasetKey = (
  instanceId: string | number,
  idValuesKey: string,
  timeValues: Pick<TimeValuesProps, 'originValue' | 'timeRange'>
) =>
  `${String(instanceId)}|${idValuesKey}|${timeValues.originValue ?? ''}|${(timeValues.timeRange || []).join(',')}`;

/**
 * 同一代加载里已有序列或在飞的 name 不再打请求。
 * 换实例 / 改时间 / 静默刷新会升代，可见集再拉。
 */
export const metricNamesNeedingFetch = (
  wanted: readonly string[],
  loadedGeneration: ReadonlyMap<string, number>,
  generation: number,
  inflight: ReadonlySet<string>
): string[] =>
  wanted.filter((name) => !inflight.has(name) && loadedGeneration.get(name) !== generation);
