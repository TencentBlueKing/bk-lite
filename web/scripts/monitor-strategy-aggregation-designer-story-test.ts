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
  'Average',
  'Maximum',
  'Minimum',
  'Accumulated',
  'Valid count',
  'Latest value',
  'avg_over_time((avg(metric) by (group_by))[5m:1m])',
  'count(last_over_time(metric[5m])) by (group_by)',
  'any(last_over_time(metric[5m])) by (group_by)',
  'Aggregation period is the observation window',
  'SUM is usually not appropriate for gauge metrics',
].forEach((expected) => {
  assert(storySource.includes(expected), `Story should include ${expected}`);
});

[
  'AVG_OVER_TIME',
  'MAX_OVER_TIME',
  'MIN_OVER_TIME',
  'SUM_OVER_TIME',
].forEach((legacyMethod) => {
  assert(!storySource.includes(`label: '${legacyMethod}'`), `${legacyMethod} should not be a visible method label`);
});

console.log('monitor strategy aggregation designer story contract OK');
