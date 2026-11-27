export const NGINX_DEFAULT_INTERVAL_SECONDS = 60;

/** 采集间隔。缺省或非法时按 60 秒。步长下限和请求里的 interval_seconds 都用这个值。 */
export const nginxCollectionIntervalSeconds = (intervalSeconds?: number) => {
  const value = Number(intervalSeconds);
  if (!Number.isFinite(value) || value <= 0) return NGINX_DEFAULT_INTERVAL_SECONDS;
  return Math.ceil(value);
};
