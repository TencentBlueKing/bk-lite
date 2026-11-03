import type { BaseMetricConfig } from '../../shared/types';

/** 「数据库压力排行」TopN 数据库数量;单一常量同时驱动 topk 查询与展示。 */
export const PG_TOP_N = 8;

interface GuideItem { label: string; detail: string }

export interface PgTopDbQuery {
  /** 用作 React key 与 state 键 */
  key: string;
  title: string;
  /** formatMetricValue 用的单位 */
  unit: string;
  color: string;
  /** 按 db 聚合 + topk 的查询;__$labels__ 由 buildSearchParams 注入实例过滤 */
  query: string;
  guide: GuideItem[];
}

// 注:checkpoint / buffer 等实例级指标无 db 维度,不纳入按库排行(见 DASHBOARD_DESCRIPTION.md)。
export const PG_TOP_DB_QUERIES: PgTopDbQuery[] = [
  {
    key: 'numbackends',
    title: '连接数 Top',
    unit: 'counts',
    color: '#2563EB',
    query: `topk(${PG_TOP_N}, sum by (db) (postgresql_numbackends{__$labels__}))`,
    guide: [{ label: '连接数排行', detail: '各数据库当前活跃会话数,定位连接集中在哪个库。' }]
  },
  {
    key: 'rollback',
    title: '事务回滚 Top',
    unit: 'cps',
    color: '#EF4444',
    query: `topk(${PG_TOP_N}, sum by (db) (rate(postgresql_xact_rollback{__$labels__}[__$window__])))`,
    guide: [{ label: '回滚排行', detail: '各数据库事务回滚速率,定位失败 / 冲突集中的库。' }]
  },
  {
    key: 'temp_files',
    title: '临时文件 Top',
    unit: 'cps',
    color: '#F59E0B',
    query: `topk(${PG_TOP_N}, sum by (db) (rate(postgresql_temp_files{__$labels__}[__$window__])))`,
    guide: [{ label: '临时文件排行', detail: '各数据库临时文件创建速率,定位复杂查询 / work_mem 压力大的库。' }]
  }
];

const statementDimensions = [
  { name: 'datname', description: '数据库名' },
  { name: 'queryid', description: '语句标识' },
  { name: 'query_text', description: '语句文本' }
];

const waitDimensions = [
  { name: 'wait_event_type', description: '等待类型' },
  { name: 'wait_event', description: '等待事件' }
];

const STATEMENT_BY = 'instance_id, datname, queryid, query_text';
const STATEMENT_KEY = 'instance_id, datname, queryid';
const WAIT_BY = 'instance_id, wait_event_type, wait_event';

/** 有 last/max 点即入选。不用 increase 窗口增量，避免已采集却被判成未采集。 */
const statementPresent = `topk(20, max by (${STATEMENT_BY}) (postgresql_statement_total_time_seconds{__$labels__}))`;
const statementPresentKey = `topk(20, max by (${STATEMENT_KEY}) (postgresql_statement_total_time_seconds{__$labels__}))`;

export interface PostgresDigestMetric extends BaseMetricConfig {
  /** 趋势走区间查询。表上的累计值用即时查询。 */
  range?: boolean;
}

/** 恢复状态。0 为接受写入（含单机），1 为备库。不是采集开关。 */
export const POSTGRES_RECOVERY_QUERY = 'max by (instance_id) (postgresql_recovery_in_recovery{__$labels__})';

/** 当前连着的流复制对端个数。0 是采点，不是缺失。 */
export const POSTGRES_STREAMING_REPLICAS_QUERY = 'max by (instance_id) (postgresql_replication_streaming_replicas{__$labels__})';

/** 复制槽个数，含暂时没连上的槽。0 是采点，不是缺失。 */
export const POSTGRES_REPLICATION_SLOTS_QUERY = 'max by (instance_id) (postgresql_replication_replication_slots{__$labels__})';

/** 已连接副本写完收到变更的最长时间。0 是采到的延迟，不是缺失。 */
export const POSTGRES_WRITE_LAG_QUERY = 'max by (instance_id) (postgresql_replication_write_lag_seconds{__$labels__})';

/** 已连接副本把收到的变更落到磁盘的最长时间。0 是采到的延迟，不是缺失。 */
export const POSTGRES_FLUSH_LAG_QUERY = 'max by (instance_id) (postgresql_replication_flush_lag_seconds{__$labels__})';

/** 已连接副本把收到的变更应用到数据上的最长时间。0 是采到的延迟，不是缺失。 */
export const POSTGRES_REPLAY_LAG_QUERY = 'max by (instance_id) (postgresql_replication_replay_lag_seconds{__$labels__})';

/** 复制槽为了让副本还能接上而留着的数据量。0 是采到的积压，不是缺失。 */
export const POSTGRES_SLOT_RESTART_LAG_QUERY = 'max by (instance_id) (postgresql_replication_slot_restart_lag_bytes{__$labels__})';

/** 专业盘语句/等待查询。传统盘不加载这组指标。 */
export const POSTGRES_DIGEST_METRICS: PostgresDigestMetric[] = [
  {
    name: 'postgresql_statement_time',
    display_name: '语句耗时',
    description: '该语句的累计耗时。有采点即显示，不按窗口增量判断是否采集。',
    unit: 's',
    color: '#2f6bff',
    dimensions: statementDimensions,
    query: statementPresent
  },
  {
    name: 'postgresql_statement_calls',
    display_name: '语句执行次数',
    description: '该语句的累计执行次数。有采点即显示，不按窗口增量判断是否采集。',
    unit: 'counts',
    color: '#ff9f43',
    dimensions: statementDimensions,
    query: `max by (${STATEMENT_BY}) (postgresql_statement_calls_total{__$labels__}) and on (${STATEMENT_KEY}) ${statementPresentKey}`
  },
  {
    name: 'postgresql_statement_rows',
    display_name: '语句返回行数',
    description: '该语句累计返回的行数。有采点即显示，不按窗口增量判断是否采集。',
    unit: 'counts',
    color: '#faad14',
    dimensions: statementDimensions,
    query: `max by (${STATEMENT_BY}) (postgresql_statement_rows_total{__$labels__}) and on (${STATEMENT_KEY}) ${statementPresentKey}`
  },
  {
    name: 'postgresql_statement_time_rate',
    display_name: '语句耗时速率',
    description: '该语句每秒消耗的时间，用来看窗口内负载变化。',
    unit: 's',
    color: '#2f6bff',
    dimensions: statementDimensions,
    range: true,
    query: `sum by (${STATEMENT_BY}) (rate(postgresql_statement_total_time_seconds{__$labels__}[__$window__])) and on (${STATEMENT_KEY}) ${statementPresentKey}`
  },
  {
    name: 'postgresql_wait_sessions',
    display_name: '当前等待会话数',
    description: '采集时刻处于该等待事件的会话数。有采点即显示。',
    unit: 'counts',
    color: '#ff7875',
    dimensions: waitDimensions,
    range: true,
    query: `sum by (${WAIT_BY}) (postgresql_wait_sessions{__$labels__})`
  }
];
