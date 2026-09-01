import assert from 'node:assert/strict';

import {
  buildSearchQueryParams,
  generateSearchId,
  getMetricsMapKey,
  resolveInitialPlugin,
  resolveMetricSelection,
} from '../src/app/monitor/(pages)/search/searchQueryLogic';
import {
  buildSearchTimeQueryParams,
  parseSearchTimeQueryParams,
} from '../src/app/monitor/utils/searchTimeQuery';
import type { MetricItem } from '../src/app/monitor/types';
import type { InstanceItem } from '../src/app/monitor/types/search';

const hostMetric = {
  id: 125,
  name: 'cpu_usage_total',
  display_name: 'CPU Usage',
  query: '100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__}',
  unit: 'percent',
  instance_id_keys: ['instance_id'],
  dimensions: [],
} as MetricItem;

const hostRemoteMetric = {
  id: 494,
  name: 'cpu_usage_total',
  display_name: 'CPU Usage',
  query: 'host_cpu_usage_percent_gauge{instance_type="os", __$labels__}',
  unit: '%',
  instance_id_keys: ['instance_id'],
  dimensions: [],
} as MetricItem;

const memoryMetric = {
  id: 152,
  name: 'mem_used_percent',
  display_name: 'Memory Usage',
  query: 'mem_used_percent{instance_type="os", __$labels__}',
  unit: 'percent',
  instance_id_keys: ['instance_id'],
  dimensions: [],
} as MetricItem;

const hostInstance = {
  instance_id: "('MTVmOTFiYTM5ODZk',)",
  instance_name: '10.10.41.149',
  instance_id_values: ['MTVmOTFiYTM5ODZk'],
} satisfies InstanceItem;

assert.equal(getMetricsMapKey(8, 6), '8_6');
assert.equal(getMetricsMapKey('8', null), '8');

assert.equal(
  generateSearchId({ randomUUID: () => 'native-random-uuid' }),
  'native-random-uuid'
);
assert.equal(
  generateSearchId({
    getRandomValues: (values) => {
      values.fill(0);
      return values;
    },
  }),
  '00000000-0000-4000-8000-000000000000'
);

assert.equal(resolveInitialPlugin([{ id: 6, name: 'Host' }]), 6);
assert.equal(
  resolveInitialPlugin([
    { id: 6, name: 'Host' },
    { id: 30, name: 'Host Remote' },
  ]),
  null
);

assert.equal(resolveMetricSelection([hostMetric, hostRemoteMetric], 494)?.id, 494);
assert.equal(resolveMetricSelection([hostMetric, memoryMetric], 'mem_used_percent')?.id, 152);
assert.equal(resolveMetricSelection([hostMetric, hostRemoteMetric], 'cpu_usage_total')?.id, 125);

const hostParams = buildSearchQueryParams({
  group: {
    id: 'g1',
    name: '查询条件 1',
    object: 8,
    plugin: 6,
    instanceIds: [hostInstance.instance_id],
    metric: 125,
    aggregation: 'AVG',
    conditions: [],
    collapsed: false,
  },
  metrics: [hostMetric, hostRemoteMetric],
  instances: [hostInstance],
  timeRange: { timeRange: [100000, 460000], originValue: 0 },
});

assert.equal(hostParams.query, undefined);
assert.equal(hostParams.monitor_object_id, 8);
assert.equal(hostParams.metric_id, 125);
assert.deepEqual(hostParams.instance_ids, [hostInstance.instance_id]);
assert.equal(hostParams.source_unit, 'percent');
assert.equal(hostParams.start, 100000);
assert.equal(hostParams.end, 460000);

const remoteParams = buildSearchQueryParams({
  group: {
    id: 'g1',
    name: '查询条件 1',
    object: 8,
    plugin: 30,
    instanceIds: [hostInstance.instance_id],
    metric: 494,
    aggregation: 'AVG',
    conditions: [],
    collapsed: false,
  },
  metrics: [hostMetric, hostRemoteMetric],
  instances: [hostInstance],
  timeRange: { timeRange: [100000, 460000], originValue: 0 },
});

assert.equal(remoteParams.query, undefined);
assert.equal(remoteParams.monitor_object_id, 8);
assert.equal(remoteParams.metric_id, 494);
assert.deepEqual(remoteParams.instance_ids, [hostInstance.instance_id]);

assert.deepEqual(buildSearchTimeQueryParams({ timeRange: [], originValue: 15 }), {
  origin: '15',
});
assert.deepEqual(buildSearchTimeQueryParams({ timeRange: [], originValue: 60 }), {
  origin: '60',
});
assert.deepEqual(
  buildSearchTimeQueryParams({
    timeRange: [1_700_000_000_000, 1_700_000_900_000],
    originValue: 0,
  }),
  { start: '1700000000000', end: '1700000900000' }
);
assert.deepEqual(
  buildSearchTimeQueryParams({ timeRange: [100, 50], originValue: 0 }),
  {}
);

const asParams = (query: string) => new URLSearchParams(query);
assert.deepEqual(parseSearchTimeQueryParams(asParams('origin=60')), {
  timeValues: { timeRange: [], originValue: 60 },
  selectValue: 60,
  rangeStart: null,
  rangeEnd: null,
});
assert.deepEqual(
  parseSearchTimeQueryParams(asParams('start=1700000000000&end=1700000900000')),
  {
    timeValues: { timeRange: [1_700_000_000_000, 1_700_000_900_000], originValue: 0 },
    selectValue: 0,
    rangeStart: 1_700_000_000_000,
    rangeEnd: 1_700_000_900_000,
  }
);
assert.deepEqual(parseSearchTimeQueryParams(asParams('origin=15&start=1&end=2')), {
  timeValues: { timeRange: [], originValue: 15 },
  selectValue: 15,
  rangeStart: null,
  rangeEnd: null,
});
assert.deepEqual(parseSearchTimeQueryParams(asParams('start=abc&end=def')), {
  timeValues: { timeRange: [], originValue: 15 },
  selectValue: 15,
  rangeStart: null,
  rangeEnd: null,
});
assert.deepEqual(parseSearchTimeQueryParams(asParams('')), {
  timeValues: { timeRange: [], originValue: 15 },
  selectValue: 15,
  rangeStart: null,
  rangeEnd: null,
});

console.log('monitor-search plugin scope validation passed');
