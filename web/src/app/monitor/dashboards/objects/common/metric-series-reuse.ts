import type { TimeValuesProps } from '@/app/monitor/types';

/** 实例 + 时间选择（不是 freeze 后的绝对窗）。切 Tab 不换这个键。 */
export const dashboardDatasetKey = (
  instanceId: string | number,
  idValuesKey: string,
  timeValues: Pick<TimeValuesProps, 'originValue' | 'timeRange'>
) =>
  `${String(instanceId)}|${idValuesKey}|${timeValues.originValue ?? ''}|${(timeValues.timeRange || []).join(',')}`;

/**
 * 已提供但白名单为空（磁盘/网络页不拉主机指标）时的作用域键。
 * 不可与未传 metricNames 的 `''` 混用，否则 disk↔net / 初值会误判成作用域未变。
 */
export const EMPTY_METRIC_SCOPE_KEY = '__empty__';

export const dashboardMetricScopeKey = (metricNames: readonly string[] | undefined): string => {
  if (metricNames == null) return '';
  if (metricNames.length === 0) return EMPTY_METRIC_SCOPE_KEY;
  return metricNames.join('\n');
};

export const metricNamesFromScopeKey = (scopeKey: string): string[] =>
  !scopeKey || scopeKey === EMPTY_METRIC_SCOPE_KEY
    ? []
    : scopeKey.split('\n').filter(Boolean);

/** 增量补拉必须挂活 signal；已 abort / 空则换新控制器，禁止复用死信号。 */
export const resolveLiveAbortController = (
  current: AbortController | null
): AbortController =>
  !current || current.signal.aborted ? new AbortController() : current;

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

/**
 * 磁盘/网络页可见集为空。静默刷新若仍升代，会把其它页签已加载序列标成过期，
 * 回切时整表重打。手动刷新不走这里，仍升代。
 * wantedCount 为 null 表示未传作用域（其它仪表盘），恒不跳过。
 */
export const shouldSkipEmptyScopeSilentRefresh = (
  reuseLoadedSeries: boolean,
  sameDataset: boolean,
  silent: boolean,
  wantedCount: number | null
): boolean => (
  reuseLoadedSeries && sameDataset && silent && wantedCount === 0
);
