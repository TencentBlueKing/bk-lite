import { formatMongoReading, mongoLatest, type MongoMetricMap } from './series';

/** 复制签要拉的即时读数。有任一真实采样（含 0）即出数。 */
export const MONGODB_REPLICATION_METRIC_NAMES = [
  'mongodb_repl_lag',
  'mongodb_repl_oplog_window_sec',
  'mongodb_repl_state',
  'mongodb_repl_member_health',
  'mongodb_member_status'
] as const;

export type MongoReplicationLoad = 'loading' | 'ready' | 'not_collected';

/** 有任一真实采样（含主库延迟 0）即出数。全无序列才是未采集。查询未回时先保持加载。 */
export const mongoReplicationLoad = (
  metricMap: MongoMetricMap,
  pending: ReadonlySet<string>,
  booting = false
): MongoReplicationLoad => {
  const anyPoint = MONGODB_REPLICATION_METRIC_NAMES.some(
    (name) => mongoLatest(metricMap, name) != null
  );
  if (anyPoint) return 'ready';
  const waiting = booting || MONGODB_REPLICATION_METRIC_NAMES.some((name) => pending.has(name));
  if (waiting) return 'loading';
  return 'not_collected';
};

export const mongoReplicationTabMode = (
  load: MongoReplicationLoad
): 'ready' | 'loading' | 'empty' => {
  if (load === 'ready') return 'ready';
  if (load === 'loading') return 'loading';
  return 'empty';
};

/** 「未采集」只在相关序列全部落定且没有样本时出现。 */
export const mongoReplicationDimmed = (load: MongoReplicationLoad) => load === 'not_collected';

export const mongoDurationText = (value: number | null) => formatMongoReading(value, 's');

/** 1 为正常，0 为异常。其它有限读数原样显示，缺失为 —。 */
export const mongoMemberHealthText = (value: number | null): { text: string; tone?: string } => {
  if (value == null || !Number.isFinite(value)) return { text: '—' };
  if (value === 1) return { text: '正常', tone: 'var(--color-success)' };
  if (value === 0) return { text: '异常', tone: 'var(--color-fail)' };
  return { text: formatMongoReading(value, 'none') };
};
