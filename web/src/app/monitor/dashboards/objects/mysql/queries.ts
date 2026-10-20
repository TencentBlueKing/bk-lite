import type { BaseMetricConfig } from '../../shared/types';

const statementDimensions = [
  { name: 'schema', description: '库名' },
  { name: 'digest', description: '语句摘要' },
  { name: 'digest_text', description: '语句文本' }
];

const waitDimensions = [
  { name: 'event_name', description: '等待事件' }
];

/** 专业盘语句/等待查询。传统盘不加载这组指标。 */
export const MYSQL_DIGEST_METRICS: BaseMetricConfig[] = [
  {
    name: 'mysql_statement_time',
    display_name: '语句耗时',
    description: '单条语句的累计耗时，单位秒。',
    unit: 's',
    color: '#2f6bff',
    dimensions: statementDimensions,
    query: 'topk(20, max by (instance_id, schema, digest, digest_text) (mysql_perf_schema_events_statements_seconds_total{__$labels__}))'
  },
  {
    name: 'mysql_statement_calls',
    display_name: '语句执行次数',
    description: '单条语句的累计执行次数。',
    unit: 'counts',
    color: '#ff9f43',
    dimensions: statementDimensions,
    query: 'max by (instance_id, schema, digest, digest_text) (mysql_perf_schema_events_statements_total{__$labels__}) and on (instance_id, digest) topk(20, max by (instance_id, digest) (mysql_perf_schema_events_statements_seconds_total{__$labels__}))'
  },
  {
    name: 'mysql_statement_rows_examined',
    display_name: '语句扫描行数',
    description: '单条语句累计扫描的行数。',
    unit: 'counts',
    color: '#faad14',
    dimensions: statementDimensions,
    query: 'max by (instance_id, schema, digest, digest_text) (mysql_perf_schema_events_statements_rows_examined_total{__$labels__}) and on (instance_id, digest) topk(20, max by (instance_id, digest) (mysql_perf_schema_events_statements_seconds_total{__$labels__}))'
  },
  {
    name: 'mysql_wait_event_time',
    display_name: '等待事件耗时',
    description: '单个等待事件的累计耗时，单位秒。',
    unit: 's',
    color: '#ff7875',
    dimensions: waitDimensions,
    query: 'topk(20, max by (instance_id, event_name) (mysql_perf_schema_events_waits_seconds_total{__$labels__}))'
  },
  {
    name: 'mysql_wait_event_count',
    display_name: '等待事件次数',
    description: '单个等待事件的累计次数。',
    unit: 'counts',
    color: '#722ed1',
    dimensions: waitDimensions,
    query: 'max by (instance_id, event_name) (mysql_perf_schema_events_waits_total{__$labels__}) and on (instance_id, event_name) topk(20, max by (instance_id, event_name) (mysql_perf_schema_events_waits_seconds_total{__$labels__}))'
  }
];
