import type { BaseMetricConfig } from '../../shared/types';

const statementDimensions = [
  { name: 'schema', description: '库名' },
  { name: 'digest', description: '语句摘要' },
  { name: 'digest_text', description: '语句文本' }
];

const waitDimensions = [
  { name: 'event_name', description: '等待事件' }
];

const STATEMENT_BY = 'instance_id, schema, digest, digest_text';
const STATEMENT_DIGEST = 'instance_id, digest';
const WAIT_EVENT = 'instance_id, event_name';

/** 有 last 点即入选。不用 increase 窗口增量，避免已采集却被判成未采集。 */
const statementPresent = `topk(20, max by (${STATEMENT_BY}) (mysql_perf_schema_events_statements_seconds_total{__$labels__}))`;
const statementPresentDigest = `topk(20, max by (${STATEMENT_DIGEST}) (mysql_perf_schema_events_statements_seconds_total{__$labels__}))`;
const waitPresent = `topk(20, max by (${WAIT_EVENT}) (mysql_perf_schema_events_waits_seconds_total{__$labels__}))`;

/** 专业盘语句/等待查询。传统盘不加载这组指标。 */
export const MYSQL_DIGEST_METRICS: BaseMetricConfig[] = [
  {
    name: 'mysql_statement_time',
    display_name: '语句耗时',
    description: '该语句的累计耗时。有采点即显示，不按窗口增量判断是否采集。',
    unit: 's',
    color: '#2f6bff',
    dimensions: statementDimensions,
    query: statementPresent
  },
  {
    name: 'mysql_statement_calls',
    display_name: '语句执行次数',
    description: '该语句的累计执行次数。有采点即显示，不按窗口增量判断是否采集。',
    unit: 'counts',
    color: '#ff9f43',
    dimensions: statementDimensions,
    query: `max by (${STATEMENT_BY}) (mysql_perf_schema_events_statements_total{__$labels__}) and on (${STATEMENT_DIGEST}) ${statementPresentDigest}`
  },
  {
    name: 'mysql_statement_rows_examined',
    display_name: '语句扫描行数',
    description: '该语句累计扫描的行数。有采点即显示，不按窗口增量判断是否采集。',
    unit: 'counts',
    color: '#faad14',
    dimensions: statementDimensions,
    query: `max by (${STATEMENT_BY}) (mysql_perf_schema_events_statements_rows_examined_total{__$labels__}) and on (${STATEMENT_DIGEST}) ${statementPresentDigest}`
  },
  {
    name: 'mysql_statement_time_rate',
    display_name: '语句耗时速率',
    description: '该语句每秒消耗的时间，用来看窗口内负载变化。',
    unit: 's',
    color: '#2f6bff',
    dimensions: statementDimensions,
    query: `sum by (${STATEMENT_BY}) (rate(mysql_perf_schema_events_statements_seconds_total{__$labels__}[__$window__])) and on (${STATEMENT_DIGEST}) ${statementPresentDigest}`
  },
  {
    name: 'mysql_wait_event_time',
    display_name: '等待事件耗时',
    description: '该等待事件的累计耗时。有采点即显示，不按窗口增量判断是否采集。',
    unit: 's',
    color: '#ff7875',
    dimensions: waitDimensions,
    query: waitPresent
  },
  {
    name: 'mysql_wait_event_count',
    display_name: '等待事件次数',
    description: '该等待事件的累计次数。有采点即显示，不按窗口增量判断是否采集。',
    unit: 'counts',
    color: '#722ed1',
    dimensions: waitDimensions,
    query: `max by (${WAIT_EVENT}) (mysql_perf_schema_events_waits_total{__$labels__}) and on (${WAIT_EVENT}) ${waitPresent}`
  },
  {
    name: 'mysql_wait_event_time_rate',
    display_name: '等待事件耗时速率',
    description: '该等待事件每秒消耗的时间，用来看窗口内负载变化。',
    unit: 's',
    color: '#ff7875',
    dimensions: waitDimensions,
    query: `sum by (${WAIT_EVENT}) (rate(mysql_perf_schema_events_waits_seconds_total{__$labels__}[__$window__])) and on (${WAIT_EVENT}) ${waitPresent}`
  }
];
