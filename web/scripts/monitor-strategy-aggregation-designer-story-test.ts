import fs from 'fs';
import path from 'path';

const storyPath = path.join(
  process.cwd(),
  'src/stories/monitor-strategy-aggregation-designer.stories.tsx'
);

const assert = (condition: unknown, message: string) => {
  if (!condition) {
    throw new Error(message);
  }
};

assert(fs.existsSync(storyPath), 'Monitor strategy aggregation designer story should exist');

const storySource = fs.readFileSync(storyPath, 'utf8');

[
  "title: 'Monitor/StrategyAggregationDesigner'",
  'AggregationDesignerFrame',
  'DefaultNumericMetric',
  'InterfaceStatusLast',
  'DeltaCounterSum',
  'MethodComparison',
  '汇聚方式',
  'AVG_OVER_TIME',
  'MAX_OVER_TIME',
  'MIN_OVER_TIME',
  'SUM_OVER_TIME',
  'COUNT_OVER_TIME',
  'LAST_OVER_TIME',
  '采集模板',
  '主机（Telegraf）',
  '主机远程采集（Telegraf）',
  '条件维度',
  '聚合周期',
  '聚合方式',
  '默认：AVG',
  'COUNT（计数）',
  '默认：AVG_OVER_TIME',
  '30 个计算点',
  'by',
  'groupByControlStyle',
  'groupMethodSelectStyle',
  'groupDimensionSelectStyle',
  'groupByDividerStyle',
  'groupBySelectClassName',
  'height: 36',
  'borderRight',
  'borderLeft',
  'formRowStyle',
  'formLabelStyle',
  'formControlStyle',
  'avg_over_time((avg(metric) by (group_by))[5m:10s])',
  'last_over_time((count(metric) by (group_by))[5m:10s])',
  'last_over_time((avg(metric) by (group_by))[5m:10s])',
  '汇聚周期是观察窗口',
].forEach((expected) => {
  assert(storySource.includes(expected), `Story should include ${expected}`);
});

[
  '策略双层汇聚设计器',
  '当前语义：分组',
  'MethodSummary',
  'label="分组聚合方式"',
  '分组聚合 SUM + 聚合方式 COUNT_OVER_TIME',
].forEach((removed) => {
  assert(!storySource.includes(removed), `Story should not keep redesign shell text ${removed}`);
});

console.log('monitor strategy aggregation designer story contract OK');
