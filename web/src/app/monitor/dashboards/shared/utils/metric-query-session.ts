/**
 * MySQL 专业仪表盘拉点会话：等实例采集间隔、在新一轮 load 时中止在途 range query。
 * Host / simple-dashboard-core 不要接入，避免改变它们的现有拉点行为。
 */

export const INSTANCE_INTERVAL_WAIT_MS = 800;

export function shouldWaitForInstanceInterval(params: {
  hasInstanceIds: boolean;
  instanceInterval?: number;
  instanceListSettled: boolean;
}): boolean {
  return params.hasInstanceIds && params.instanceInterval === undefined && !params.instanceListSettled;
}

export function beginMetricQueryAbort(previous?: AbortController | null): AbortController {
  previous?.abort();
  return new AbortController();
}

export function isMetricQueryAborted(signal?: AbortSignal): boolean {
  return Boolean(signal?.aborted);
}
