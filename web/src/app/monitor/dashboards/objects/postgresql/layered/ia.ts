export type PostgresTab =
  | 'overview'
  | 'cache-txn'
  | 'checkpoint-anomaly'
  | 'statements'
  | 'waits'
  | 'replication';

export const POSTGRES_TABS: ReadonlyArray<{ key: PostgresTab; label: string }> = [
  { key: 'overview', label: '概览' },
  { key: 'cache-txn', label: '缓存与事务' },
  { key: 'checkpoint-anomaly', label: '检查点与异常' },
  { key: 'statements', label: 'Top SQL' },
  { key: 'waits', label: '等待' },
  { key: 'replication', label: '复制' }
];

const TAB_KEYS = new Set<string>(POSTGRES_TABS.map((tab) => tab.key));

/** 旧 `performance` 深链里落到检查点与异常的小节 / 图锚。其余锚进缓存与事务。 */
const CHECKPOINT_ANOMALY_ANCHORS = new Set([
  'checkpoint',
  'checkpoints',
  'buffer-source',
  'buffer-alloc',
  'anomaly',
  'deadlock',
  'temp'
]);

export const isPostgresTab = (value: string | null): value is PostgresTab => (
  value != null && TAB_KEYS.has(value)
);

export interface PostgresFocusTarget {
  tab: PostgresTab;
  anchor: string;
}

export const postgresOpenTarget = (anchor: string): PostgresFocusTarget => ({
  tab: CHECKPOINT_ANOMALY_ANCHORS.has(anchor) ? 'checkpoint-anomaly' : 'cache-txn',
  anchor
});

/** 概览 KPI 进趋势签。连接与告警不在这里。 */
export const postgresKpiJump = (key: string): PostgresFocusTarget | null => {
  if (key === 'cache') return postgresOpenTarget('cache-hit');
  if (key === 'commit') return postgresOpenTarget('xact');
  if (key === 'deadlock') return postgresOpenTarget('deadlock');
  return null;
};

/**
 * URL `postgresTab`。旧 `performance` 深链按锚点落到新签；
 * 没有锚或锚在缓存/事务侧时进缓存与事务。
 */
export const resolvePostgresTab = (requested: string | null, focus: string | null): PostgresTab => {
  if (requested === 'performance') return postgresOpenTarget(focus ?? '').tab;
  return isPostgresTab(requested) ? requested : 'overview';
};
