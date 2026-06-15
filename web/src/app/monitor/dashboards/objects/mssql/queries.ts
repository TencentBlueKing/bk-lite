/** 「数据库压力排行」TopN 数据库数量;单一常量同时驱动 topk 查询与展示。 */
export const MSSQL_TOP_N = 8;

type GuideItem = { label: string; detail: string };

export interface MssqlTopDbQuery {
  /** 用作 React key 与 state 键 */
  key: string;
  title: string;
  /** formatMetricValue 用的单位 */
  unit: string;
  color: string;
  /** 按 database 聚合 + topk 的查询;__$labels__ 由 buildSearchParams 注入实例过滤 */
  query: string;
  guide: GuideItem[];
}

// sqlserver_database_io_* 系列由 Telegraf 按 database_name 标签分库输出,适合做按库的读写热点排行。
// 实例级 / 卷级(volume_mount_point)/ 计数器(counter)指标无 database_name 维度,不纳入按库排行。
export const MSSQL_TOP_DB_QUERIES: MssqlTopDbQuery[] = [
  {
    key: 'read_latency',
    title: '读延迟 Top',
    unit: 'ms',
    color: '#2f6bff',
    query: `topk(${MSSQL_TOP_N}, sum by (database_name) (sqlserver_database_io_read_latency_ms{__$labels__}))`,
    guide: [{ label: '读延迟排行', detail: '各数据库文件读操作平均延迟,定位读取最慢的库。' }]
  },
  {
    key: 'write_latency',
    title: '写延迟 Top',
    unit: 'ms',
    color: '#ff8a1f',
    query: `topk(${MSSQL_TOP_N}, sum by (database_name) (sqlserver_database_io_write_latency_ms{__$labels__}))`,
    guide: [{ label: '写延迟排行', detail: '各数据库文件写操作平均延迟,定位写入最慢的库。' }]
  },
  {
    key: 'io_rate',
    title: 'I/O 速率 Top',
    unit: 'cps',
    color: '#27c274',
    query: `topk(${MSSQL_TOP_N}, sum by (database_name) (rate(sqlserver_database_io_reads{__$labels__}[5m]) + rate(sqlserver_database_io_writes{__$labels__}[5m])))`,
    guide: [{ label: 'I/O 速率排行', detail: '各数据库读写操作合计速率,定位 I/O 负载最重的库。' }]
  }
];
