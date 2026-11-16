export type MssqlTab = 'overview' | 'buffer_memory' | 'io_storage' | 'waits' | 'top_sql' | 'replication';

export const MSSQL_TABS: ReadonlyArray<{ key: MssqlTab; label: string; dimmed: boolean; badge?: string }> = [
  { key: 'overview', label: '概览', dimmed: false },
  { key: 'buffer_memory', label: '缓冲与内存', dimmed: false },
  { key: 'io_storage', label: 'I/O 与存储', dimmed: false },
  { key: 'waits', label: '等待', dimmed: false },
  { key: 'top_sql', label: 'Top SQL', dimmed: true, badge: '暂无排行' },
  { key: 'replication', label: '复制', dimmed: true, badge: '采集未开启' }
];

const TAB_KEYS = new Set<string>(MSSQL_TABS.map((tab) => tab.key));

export const isMssqlTab = (value: string | null): value is MssqlTab => (
  value != null && TAB_KEYS.has(value)
);

export const resolveMssqlTab = (requested: string | null): MssqlTab => (
  isMssqlTab(requested) ? requested : 'overview'
);

export interface MssqlFocusTarget {
  tab: MssqlTab;
  anchor: string;
}

/** 概览 KPI 进对应趋势。告警走共用抽屉，不在这里。 */
export const mssqlKpiJump = (key: string): MssqlFocusTarget | null => {
  if (key === 'connections') return { tab: 'overview', anchor: 'connections' };
  if (key === 'batch') return { tab: 'overview', anchor: 'batch' };
  if (key === 'hit') return { tab: 'buffer_memory', anchor: 'hit' };
  if (key === 'cpu') return { tab: 'overview', anchor: 'cpu' };
  return null;
};

export const mssqlFocusJump = (key: string): MssqlFocusTarget | null => {
  if (key === 'read-latency') return { tab: 'io_storage', anchor: 'latency' };
  if (key === 'ple') return { tab: 'buffer_memory', anchor: 'ple' };
  if (key === 'blocked') return { tab: 'waits', anchor: 'locks' };
  if (key === 'deadlocks') return { tab: 'waits', anchor: 'deadlocks' };
  return null;
};
