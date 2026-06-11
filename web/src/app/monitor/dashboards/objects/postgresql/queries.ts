/** 「数据库压力排行」TopN 数据库数量;单一常量同时驱动 topk 查询与展示。 */
export const PG_TOP_N = 8;

type GuideItem = { label: string; detail: string };

export interface PgTopDbQuery {
  /** 用作 React key 与 state 键 */
  key: string;
  title: string;
  /** formatMetricValue 用的单位 */
  unit: string;
  color: string;
  /** 按 db(库名,Telegraf postgresql input 的原生标签)聚合 + topk 的查询;__$labels__ 由 buildSearchParams 注入实例过滤 */
  query: string;
  guide: GuideItem[];
}

// 注:checkpoint / buffer 等实例级指标无 db 维度,不纳入按库排行(见 DASHBOARD_DESCRIPTION.md)。
export const PG_TOP_DB_QUERIES: PgTopDbQuery[] = [
  {
    key: 'numbackends',
    title: '连接数 Top',
    unit: 'counts',
    color: '#2f6bff',
    query: `topk(${PG_TOP_N}, sum by (db) (postgresql_numbackends{__$labels__}))`,
    guide: [{ label: '连接数排行', detail: '各数据库当前活跃会话数,定位连接集中在哪个库。' }]
  },
  {
    key: 'rollback',
    title: '事务回滚 Top',
    unit: 'cps',
    color: '#ff4d4f',
    query: `topk(${PG_TOP_N}, sum by (db) (rate(postgresql_xact_rollback{__$labels__}[5m])))`,
    guide: [{ label: '回滚排行', detail: '各数据库事务回滚速率,定位失败 / 冲突集中的库。' }]
  },
  {
    key: 'temp_files',
    title: '临时文件 Top',
    unit: 'cps',
    color: '#faad14',
    query: `topk(${PG_TOP_N}, sum by (db) (rate(postgresql_temp_files{__$labels__}[5m])))`,
    guide: [{ label: '临时文件排行', detail: '各数据库临时文件创建速率,定位复杂查询 / work_mem 压力大的库。' }]
  }
];
