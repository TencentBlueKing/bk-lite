import type { MongoMetricConfig } from './types';

/**
 * 专业盘新增查询。传统盘 config.ts 不改。
 * 断言和游标超时在传统盘是累计值；专业盘按时间窗 increase，单位是次。
 */
export const MONGODB_PRO_QUERIES: MongoMetricConfig[] = [
  {
    name: 'mongodb_total_docs_scanned_rate',
    display_name: '文档扫描频率',
    description: '每秒扫描的文档数。',
    unit: 'cps',
    query: 'rate(mongodb_total_docs_scanned{__$labels__}[__$window__])',
    color: '#13c2c2'
  },
  {
    name: 'mongodb_document_inserted_rate',
    display_name: '文档插入',
    description: '每秒插入的文档数。',
    unit: 'cps',
    query: 'rate(mongodb_document_inserted{__$labels__}[__$window__])',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_document_updated_rate',
    display_name: '文档更新',
    description: '每秒更新的文档数。',
    unit: 'cps',
    query: 'rate(mongodb_document_updated{__$labels__}[__$window__])',
    color: '#ff9f43'
  },
  {
    name: 'mongodb_document_deleted_rate',
    display_name: '文档删除',
    description: '每秒删除的文档数。',
    unit: 'cps',
    query: 'rate(mongodb_document_deleted{__$labels__}[__$window__])',
    color: '#ff4d4f'
  },
  {
    name: 'mongodb_assert_user',
    display_name: '用户断言次数',
    description: '当前时间范围内发生的用户断言次数。',
    unit: 'counts',
    query: 'increase(mongodb_assert_user{__$labels__}[__$window__])',
    color: '#ff4d4f'
  },
  {
    name: 'mongodb_cursor_timed_out_count',
    display_name: '游标超时次数',
    description: '当前时间范围内游标超时的次数。',
    unit: 'counts',
    query: 'increase(mongodb_cursor_timed_out_count{__$labels__}[__$window__])',
    color: '#faad14'
  },
  {
    name: 'mongodb_repl_lag',
    display_name: '复制延迟',
    description: '本实例落后主库的时间。主库自己通常是 0 秒。',
    unit: 's',
    query: 'mongodb_repl_lag{__$labels__}',
    color: '#ff9f43'
  },
  {
    name: 'mongodb_repl_oplog_window_sec',
    display_name: 'oplog 窗口',
    description: '操作日志还能覆盖的时长。',
    unit: 's',
    query: 'mongodb_repl_oplog_window_sec{__$labels__}',
    color: '#13c2c2'
  },
  {
    name: 'mongodb_repl_state',
    display_name: '副本状态',
    description: '本实例在副本集中的状态。',
    unit: 'none',
    query: 'mongodb_repl_state{__$labels__}',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_repl_member_health',
    display_name: '成员健康',
    description: '本实例在副本集中是否正常。',
    unit: 'none',
    query: 'mongodb_repl_member_health{__$labels__}',
    color: '#27c274'
  },
  {
    name: 'mongodb_member_status',
    display_name: '成员角色标记',
    description: '本实例上报的副本角色。有读数才表示已上报。',
    unit: 'none',
    query: 'mongodb_member_status{__$labels__}',
    color: '#8a5cff'
  }
];
