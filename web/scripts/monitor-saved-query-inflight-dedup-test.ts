import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import type React from 'react';

import type { MetricItem } from '../src/app/monitor/types';

const run = async () => {
const queryPanelSource = readFileSync(
  new URL(
    '../src/app/monitor/(pages)/search/queryPanel.tsx',
    import.meta.url
  ),
  'utf8'
);

assert.match(
  queryPanelSource,
  /loadSavedQueryResources/,
  '保存查询加载路径应通过共享资源编排合并同键在途请求'
);

const { loadSavedQueryResources } = await import(
  '../src/app/monitor/(pages)/search/savedQueryLoading.ts'
);

const makeGroup = (id: string, plugin: number | null = 6) => ({
  id,
  name: `查询条件 ${id}`,
  object: 8,
  plugin,
  instanceIds: ['host-1'],
  metric: null,
  legacyMetricName: 'cpu_usage_total',
  aggregation: 'AVG',
  conditions: [],
  collapsed: false
});

const makeMetric = (id: number, name = 'cpu_usage_total'): MetricItem => ({
  id,
  metric_group: 1,
  metric_object: 8,
  name,
  type: 'gauge',
  dimensions: []
});

const getResourceKey = (objectId: React.Key, pluginId: React.Key | null) =>
  pluginId !== null && pluginId !== undefined && pluginId !== ''
    ? `${objectId}_${pluginId}`
    : String(objectId);

const duplicateGroups = Array.from({ length: 50 }, (_, index) =>
  makeGroup(`g${index + 1}`)
);
const beforeRequestCount = 1 + duplicateGroups.length * 3;
assert.equal(beforeRequestCount, 151);

let pluginLoads = 0;
let metricLoads = 0;
let instanceLoads = 0;
const result = await loadSavedQueryResources({
  queryGroups: duplicateGroups,
  pluginsMap: {},
  metricsMap: {},
  instancesMap: {},
  loadPlugins: async () => {
    pluginLoads += 1;
    return [{ id: 6, name: 'Host' }];
  },
  loadMetrics: async () => {
    metricLoads += 1;
    return [makeMetric(125)];
  },
  loadInstances: async () => {
    instanceLoads += 1;
    return [
      {
        instance_id: 'host-1',
        instance_name: 'Host 1',
        instance_id_values: ['host-1']
      }
    ];
  },
  getResourceKey,
  resolvePlugin: (plugins, group) =>
    group.plugin || (plugins.length === 1 ? plugins[0].id : null),
  resolveLegacyMetric: (metrics, legacyName) =>
    metrics.find((metric) => metric.name === legacyName) || null
});

const afterRequestCount = pluginLoads + metricLoads * 2 + instanceLoads;
assert.equal(afterRequestCount, 4);
assert.deepEqual(
  result.queryGroups.map((group) => group.id),
  duplicateGroups.map((group) => group.id),
  '合并请求不能改变查询组顺序'
);
assert.ok(result.queryGroups.every((group) => group.metric === 125));
assert.ok(
  result.queryGroups.every((group) => group.legacyMetricName === null),
  '每个重复组都应独立完成 legacy metric 解析'
);

const distinctGroups = [makeGroup('host', 6), makeGroup('remote', 30)];
let distinctMetricLoads = 0;
let distinctInstanceLoads = 0;
const distinctResult = await loadSavedQueryResources({
  queryGroups: distinctGroups,
  pluginsMap: { '8': [{ id: 6 }, { id: 30 }] },
  metricsMap: {},
  instancesMap: {},
  loadPlugins: async () => {
    throw new Error('已有 plugin 缓存时不应再次加载');
  },
  loadMetrics: async (_objectId, pluginId) => {
    distinctMetricLoads += 1;
    return [makeMetric(Number(pluginId))];
  },
  loadInstances: async () => {
    distinctInstanceLoads += 1;
    return [];
  },
  getResourceKey,
  resolvePlugin: (_plugins, group) => group.plugin,
  resolveLegacyMetric: (metrics) => metrics[0] || null
});
assert.equal(distinctMetricLoads, 2, '不同 object/plugin 键不能被错误合并');
assert.equal(distinctInstanceLoads, 2, '不同 object/plugin 键不能被错误合并');
assert.deepEqual(Object.keys(distinctResult.metricsMap).sort(), ['8_30', '8_6']);

const missingPluginGroup = makeGroup('missing', null);
let missingMetricKey = '';
await loadSavedQueryResources({
  queryGroups: [missingPluginGroup],
  pluginsMap: { '8': [] },
  metricsMap: {},
  instancesMap: {},
  loadPlugins: async () => [],
  loadMetrics: async (objectId, pluginId) => {
    missingMetricKey = `${objectId}:${String(pluginId)}`;
    return [];
  },
  loadInstances: async () => [],
  getResourceKey,
  resolvePlugin: () => null,
  resolveLegacyMetric: () => null
});
assert.equal(
  missingMetricKey,
  '8:null',
  '缺失 plugin 时保持原有按 object 加载行为'
);

let attempts = 0;
const retryArgs: Parameters<typeof loadSavedQueryResources>[0] = {
  queryGroups: [makeGroup('retry')],
  pluginsMap: { '8': [{ id: 6 }] },
  metricsMap: {},
  instancesMap: {},
  loadPlugins: async () => [{ id: 6 }],
  loadMetrics: async () => {
    attempts += 1;
    if (attempts === 1) throw new Error('temporary failure');
    return [makeMetric(125)];
  },
  loadInstances: async () => [],
  getResourceKey,
  resolvePlugin: (_plugins, group) => group.plugin,
  resolveLegacyMetric: (metrics, legacyName) =>
    metrics.find((metric) => metric.name === legacyName) || null
};
await assert.rejects(() => loadSavedQueryResources(retryArgs));
await loadSavedQueryResources(retryArgs);
assert.equal(attempts, 2, '失败后再次加载必须发起新请求');

console.log(
  `monitor saved query in-flight dedup passed: requests ${beforeRequestCount} -> ${afterRequestCount}`
);
};

void run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
