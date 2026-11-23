export const ROCKETMQ_COLLECTION_UP_METRIC = 'bklite_rocketmq_up';

export interface LockedYAxis {
  domain: [number, number];
  ticks: number[];
}

const LOCKED_ZERO_ONE_AXIS: LockedYAxis = {
  domain: [0, 1],
  ticks: [0, 1],
};

/**
 * RocketMQ 采集存活只展示 0 和 1。
 * 共享折线刻度会给 0–1 留白，再把上沿圆成 2；这里只锁这一条指标。
 */
export function resolveRocketmqCollectionUpAxis(
  metricName?: string | null
): LockedYAxis | null {
  if (metricName !== ROCKETMQ_COLLECTION_UP_METRIC) return null;
  return LOCKED_ZERO_ONE_AXIS;
}
