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
  }
];
