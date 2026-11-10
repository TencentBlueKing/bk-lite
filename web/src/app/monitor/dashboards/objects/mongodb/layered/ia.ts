export type MongoTab = 'overview' | 'connections' | 'throughput' | 'cache' | 'replication';

export const MONGO_TABS: ReadonlyArray<{ key: MongoTab; label: string }> = [
  { key: 'overview', label: '概览' },
  { key: 'connections', label: '连接' },
  { key: 'throughput', label: '吞吐' },
  { key: 'cache', label: '缓存与内存' },
  { key: 'replication', label: '复制' }
];

const TAB_KEYS = new Set<string>(MONGO_TABS.map((tab) => tab.key));

/** 旧合并签里属于连接故事的锚。network 已迁到连接签。throughput 深链带上它们时改落连接签。 */
const CONNECTION_ANCHORS = new Set(['connections', 'queue', 'network']);

export const mongoConnectionAnchor = (focus: string | null) => (
  focus != null && CONNECTION_ANCHORS.has(focus)
);

export const isMongoTab = (value: string | null): value is MongoTab => (
  value != null && TAB_KEYS.has(value)
);

export interface MongoFocusTarget {
  tab: MongoTab;
  anchor: string;
}

/** 概览 KPI 进趋势签。告警走共用抽屉，运行时间不跳。 */
export const mongoKpiJump = (key: string): MongoFocusTarget | null => {
  if (key === 'connections') return { tab: 'connections', anchor: 'connections' };
  if (key === 'queries') return { tab: 'throughput', anchor: 'throughput' };
  if (key === 'latency') return { tab: 'throughput', anchor: 'latency' };
  if (key === 'cache') return { tab: 'cache', anchor: 'cache-usage' };
  return null;
};

export const mongoFocusJump = (key: string): MongoFocusTarget | null => {
  if (key === 'queued-writes') return { tab: 'connections', anchor: 'queue' };
  if (key === 'docs-scanned') return { tab: 'throughput', anchor: 'docs-scanned' };
  if (key === 'page-faults') return { tab: 'cache', anchor: 'page-faults' };
  if (key === 'dirty') return { tab: 'cache', anchor: 'dirty' };
  return null;
};

/**
 * URL `mongodbTab`。
 * 旧「连接与吞吐」的 key 仍是 throughput：focus 为 connections / queue / network 时改落连接签；
 * 吞吐侧锚点留在吞吐。没有 focus 的 throughput 就是拆开后的吞吐签。
 */
export const resolveMongoTab = (requested: string | null, focus: string | null = null): MongoTab => {
  if (requested === 'throughput' && mongoConnectionAnchor(focus)) {
    return 'connections';
  }
  return isMongoTab(requested) ? requested : 'overview';
};
