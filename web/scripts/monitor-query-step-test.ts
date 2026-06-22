import assert from 'node:assert/strict';

import { calculateQueryStep } from '../src/app/monitor/utils/queryStep';
import { buildSearchQueryParams } from '../src/app/monitor/(pages)/search/searchQueryLogic';
import type { MetricItem } from '../src/app/monitor/types';
import type { InstanceItem } from '../src/app/monitor/types/search';

const oneHourMs = 60 * 60 * 1000;
const fifteenMinutesMs = 15 * 60 * 1000;

assert.equal(calculateQueryStep(0, oneHourMs), 36);
assert.equal(calculateQueryStep(0, oneHourMs, 60), 60);
assert.equal(calculateQueryStep(0, fifteenMinutesMs, 10), 10);
assert.equal(calculateQueryStep(0, oneHourMs, undefined), 36);
assert.equal(calculateQueryStep(0, oneHourMs, 'bad'), 36);
assert.equal(calculateQueryStep(0, oneHourMs, 0), 36);
assert.equal(calculateQueryStep(0, oneHourMs, -1), 36);
assert.equal(calculateQueryStep(0, 1, 'bad'), 1);

const metric = {
  id: 1,
  metric_group: 1,
  metric_object: 8,
  name: 'cpu_usage',
  type: 'gauge',
  display_name: 'CPU Usage',
  query: 'cpu_usage{__$labels__}',
  unit: 'percent',
  instance_id_keys: ['instance_id'],
  dimensions: [],
} satisfies MetricItem;

const fastInstance = {
  instance_id: 'fast',
  instance_name: 'fast-host',
  instance_id_values: ['fast'],
  interval: 10,
} satisfies InstanceItem;

const slowInstance = {
  instance_id: 'slow',
  instance_name: 'slow-host',
  instance_id_values: ['slow'],
  interval: 60,
} satisfies InstanceItem;

const searchParams = buildSearchQueryParams({
  group: {
    id: 'g1',
    name: '查询条件 1',
    object: 8,
    plugin: 6,
    instanceIds: [fastInstance.instance_id, slowInstance.instance_id],
    metric: metric.id,
    legacyMetricName: null,
    aggregation: 'AVG',
    conditions: [],
    collapsed: false,
  },
  metrics: [metric],
  instances: [fastInstance, slowInstance],
  timeRange: { timeRange: [0, oneHourMs], originValue: 0 },
});

assert.equal(searchParams.step, 60);

console.log('monitor query step tests passed');
