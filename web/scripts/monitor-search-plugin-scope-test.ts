import assert from 'node:assert/strict';

import {
  buildSearchQueryParams,
  generateSearchId,
  getMetricsMapKey,
  resolveInitialPlugin,
  resolveMetricSelection,
} from '../src/app/monitor/(pages)/search/searchQueryLogic';
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

assert.equal(
  hostParams.query,
  '100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", instance_id=~"MTVmOTFiYTM5ODZk"}'
);
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

assert.equal(
  remoteParams.query,
  'host_cpu_usage_percent_gauge{instance_type="os", instance_id=~"MTVmOTFiYTM5ODZk"}'
);

console.log('monitor-search plugin scope validation passed');
