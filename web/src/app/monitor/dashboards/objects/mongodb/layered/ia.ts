export type MongoTab = 'overview' | 'throughput' | 'cache' | 'replication';

export const MONGO_TABS: ReadonlyArray<{ key: MongoTab; label: string; gray?: boolean }> = [
  { key: 'overview', label: '概览' },
  { key: 'throughput', label: '连接与吞吐' },
  { key: 'cache', label: '缓存与内存' },
  { key: 'replication', label: '复制', gray: true }
];

const TAB_KEYS = new Set<string>(MONGO_TABS.map((tab) => tab.key));

export const isMongoTab = (value: string | null): value is MongoTab => (
  value != null && TAB_KEYS.has(value)
);

export interface MongoFocusTarget {
  tab: MongoTab;
  anchor: string;
}

/** 概览 KPI 进趋势签。告警走共用抽屉，不在这里。 */
export const mongoKpiJump = (key: string): MongoFocusTarget | null => {
  if (key === 'connections') return { tab: 'throughput', anchor: 'connections' };
  if (key === 'queries') return { tab: 'throughput', anchor: 'throughput' };
  if (key === 'latency') return { tab: 'throughput', anchor: 'latency' };
  if (key === 'cache') return { tab: 'cache', anchor: 'cache-usage' };
  return null;
};

export const mongoFocusJump = (key: string): MongoFocusTarget | null => {
  if (key === 'queued-writes') return { tab: 'throughput', anchor: 'queue' };
  if (key === 'dirty') return { tab: 'cache', anchor: 'dirty' };
  return null;
};

export const resolveMongoTab = (requested: string | null): MongoTab => (
  isMongoTab(requested) ? requested : 'overview'
);
