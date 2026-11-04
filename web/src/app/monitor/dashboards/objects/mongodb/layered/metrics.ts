import { DASHBOARD_METRICS } from '../config';
import { MONGODB_PRO_QUERIES } from '../queries';
import type { MongoMetricConfig } from '../types';

/**
 * 专业盘要拉的序列。
 * 插入/更新/删除速率已合在 mongodb_write_ops_rate 里，不再单独挂三套。
 * 缓存使用率和脏数据占比用已用、上限、脏字节配对，分母为 0 不发假百分比查询。
 * 断言和游标超时用 queries.ts 里的窗口 increase，盖过传统盘的累计查询。
 */
export const MONGODB_CATEGORY_METRIC_NAMES = [
  'mongodb_uptime_ns',
  'mongodb_connections_current',
  'mongodb_connections_available',
  'mongodb_open_connections',
  'mongodb_active_reads',
  'mongodb_active_writes',
  'mongodb_queued_reads',
  'mongodb_queued_writes',
  'mongodb_latency_commands_avg',
  'mongodb_latency_reads_avg',
  'mongodb_commands_rate',
  'mongodb_queries_rate',
  'mongodb_write_ops_rate',
  'mongodb_document_inserted_rate',
  'mongodb_document_updated_rate',
  'mongodb_document_deleted_rate',
  'mongodb_total_docs_scanned_rate',
  'mongodb_resident_megabytes',
  'mongodb_vsize_megabytes',
  'mongodb_tcmalloc_current_allocated_bytes',
  'mongodb_wtcache_current_bytes',
  'mongodb_wtcache_max_bytes_configured',
  'mongodb_wtcache_tracked_dirty_bytes',
  'mongodb_net_in_bytes_count_rate',
  'mongodb_net_out_bytes_count_rate',
  'mongodb_page_faults_rate',
  'mongodb_assert_user',
  'mongodb_cursor_timed_out_count'
] as const;

const overlay = new Map(MONGODB_PRO_QUERIES.map((metric) => [metric.name, metric]));
const classic = new Map(DASHBOARD_METRICS.map((metric) => [metric.name, metric]));

export const MONGODB_CATEGORY_METRICS: MongoMetricConfig[] = MONGODB_CATEGORY_METRIC_NAMES.map((name) => {
  const metric = overlay.get(name) || classic.get(name);
  if (!metric) {
    throw new Error(`missing mongodb professional metric ${name}`);
  }
  return metric;
});

export const MONGODB_PALETTE = {
  blue: '#2f6bff',
  cyan: '#13c2c2',
  orange: '#ff9f43',
  green: '#27c274',
  violet: '#8a5cff',
  red: '#ff4d4f',
  amber: '#faad14',
  slate: '#9aa9bf'
} as const;
