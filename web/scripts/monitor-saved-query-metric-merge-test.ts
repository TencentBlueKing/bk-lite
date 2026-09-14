import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import type React from 'react';

import type { MetricItem } from '../src/app/monitor/types';
import {
  collectMetricIdsByResource,
  getMetricsAbortKey,
  mergeMetricsById,
  writeMetricsMap
} from '../src/app/monitor/(pages)/search/savedQueryMetricMerge.ts';
import { loadSavedQueryResources } from '../src/app/monitor/(pages)/search/savedQueryLoading.ts';

const makeMetric = (id: number, name = `metric_${id}`): MetricItem => ({
  id,
  metric_group: 1,
  metric_object: 8,
  name,
  type: 'gauge',
  dimensions: []
});

const makeGroup = (
  id: string,
  metric: React.Key | null,
  plugin: React.Key | null = 6,
  object: React.Key = 8
) => ({
  id,
  name: `查询条件 ${id}`,
  object,
  plugin,
  instanceIds: ['host-1'],
  metric,
  legacyMetricName: null as string | null,
  aggregation: 'AVG',
  conditions: [],
  collapsed: false
});

const getResourceKey = (objectId: React.Key, pluginId: React.Key | null) =>
  pluginId !== null && pluginId !== undefined && pluginId !== ''
    ? `${objectId}_${pluginId}`
    : String(objectId);

const FIRST_PAGE = Array.from({ length: 100 }, (_, index) =>
  makeMetric(index + 1)
);

const simulateLastWrite = (
  writes: Array<{ key: string; metrics: MetricItem[]; aborted?: boolean }>
) => {
  const map: Record<string, MetricItem[]> = {};
  for (const write of writes) {
    map[write.key] = write.aborted ? [] : write.metrics;
  }
  return map;
};

const lastWriteLost = simulateLastWrite([
  { key: '8_6', metrics: [...FIRST_PAGE, makeMetric(101)] },
  { key: '8_6', metrics: [...FIRST_PAGE, makeMetric(102)] }
]);
assert.equal(
  lastWriteLost['8_6'].some((metric) => metric.id === 101),
  false,
  '对照：last-write 会丢掉较早的 101'
);
assert.ok(
  lastWriteLost['8_6'].some((metric) => metric.id === 102),
  '对照：last-write 只保留最后写入的 102'
);

const abortedLost = simulateLastWrite([
  { key: '8_6', metrics: [...FIRST_PAGE, makeMetric(101)], aborted: true },
  { key: '8_6', metrics: [...FIRST_PAGE, makeMetric(102)] }
]);
assert.equal(
  abortedLost['8_6'].some((metric) => metric.id === 101),
  false,
  '对照：同 abort key 取消后 101 缺失'
);

const collected = collectMetricIdsByResource(
  [
    makeGroup('g1', 101),
    makeGroup('g2', 102),
    makeGroup('g3', 101),
    makeGroup('remote', 201, 30)
  ],
  getResourceKey
);
assert.deepEqual(collected.get('8_6')?.metricIds, [101, 102]);
assert.deepEqual(collected.get('8_30')?.metricIds, [201]);

const mergedCatalog = mergeMetricsById(
  [...FIRST_PAGE, makeMetric(101)],
  [...FIRST_PAGE, makeMetric(102)]
);
assert.ok(mergedCatalog.some((metric) => metric.id === 101));
assert.ok(mergedCatalog.some((metric) => metric.id === 102));

let protectedMap = writeMetricsMap({}, '8_6', [
  ...FIRST_PAGE,
  makeMetric(101),
  makeMetric(102)
]);
protectedMap = writeMetricsMap(protectedMap, '8_6', []);
assert.ok(
  protectedMap['8_6'].some((metric) => metric.id === 101),
  '空的取消结果不得覆盖已有 101'
);
assert.ok(protectedMap['8_6'].some((metric) => metric.id === 102));

assert.equal(getMetricsAbortKey('8_6', '', undefined, 101), '8_6|metric:101');
assert.equal(getMetricsAbortKey('8_6', '', undefined, 102), '8_6|metric:102');
assert.notEqual(
  getMetricsAbortKey('8_6', '', undefined, 101),
  getMetricsAbortKey('8_6', '', undefined, 102),
  '空 keyword 下不同 selectedMetricId 不得共用 abort key'
);
assert.equal(
  getMetricsAbortKey('8_6', 'cpu', 'g1', 101),
  getMetricsAbortKey('8_6', 'mem', 'g1', 102),
  'keyword+groupId 搜索仍按组取消'
);
assert.notEqual(
  getMetricsAbortKey('8_6', 'cpu', 'g1'),
  getMetricsAbortKey('8_6', 'cpu', 'g2')
);

const run = async () => {
  const metricCalls: Array<React.Key | null | undefined> = [];
  const result = await loadSavedQueryResources({
    queryGroups: [makeGroup('g1', 101), makeGroup('g2', 102)],
    pluginsMap: { '8': [{ id: 6, name: 'Host' }] },
    metricsMap: {},
    instancesMap: {},
    loadPlugins: async () => [{ id: 6, name: 'Host' }],
    loadMetrics: async (_objectId, _pluginId, selectedMetricId) => {
      metricCalls.push(selectedMetricId);
      if (selectedMetricId === null || selectedMetricId === undefined) {
        return FIRST_PAGE;
      }
      return [makeMetric(Number(selectedMetricId))];
    },
    loadInstances: async () => [
      {
        instance_id: 'host-1',
        instance_name: 'Host 1',
        instance_id_values: ['host-1']
      }
    ],
    getResourceKey,
    resolvePlugin: (_plugins, group) => group.plugin,
    resolveLegacyMetric: () => null
  });

  const merged = result.metricsMap['8_6'] || [];
  assert.ok(
    merged.some((metric) => metric.id === 101),
    '101 被 102 覆盖或取消后缺失'
  );
  assert.ok(
    merged.some((metric) => metric.id === 102),
    '同插件首屏外指标 102 应保留'
  );

  const queryPanelSource = readFileSync(
    new URL(
      '../src/app/monitor/(pages)/search/queryPanel.tsx',
      import.meta.url
    ),
    'utf8'
  );
  assert.match(queryPanelSource, /getMetricsAbortKey/);
  assert.match(queryPanelSource, /mergeMetricsById/);

  const resolveMetricId = (
    metrics: MetricItem[],
    selected: React.Key | null
  ) => metrics.find((metric) => String(metric.id) === String(selected))?.id;
  assert.equal(resolveMetricId(merged, 101), 101, 'buildSearchQueryParams 应对 101 得到 metric_id');
  assert.equal(resolveMetricId(merged, 102), 102, 'buildSearchQueryParams 应对 102 得到 metric_id');
  const searchQueryLogicSource = readFileSync(
    new URL(
      '../src/app/monitor/(pages)/search/searchQueryLogic.ts',
      import.meta.url
    ),
    'utf8'
  );
  assert.match(
    searchQueryLogicSource,
    /metric_id: metricItem\?\.id/,
    'buildSearchQueryParams 仍从合并后的 metrics 解析 metric_id'
  );

  let duplicateCalls = 0;
  await loadSavedQueryResources({
    queryGroups: [makeGroup('d1', 101), makeGroup('d2', 101)],
    pluginsMap: { '8': [{ id: 6, name: 'Host' }] },
    metricsMap: {},
    instancesMap: {},
    loadPlugins: async () => [{ id: 6, name: 'Host' }],
    loadMetrics: async (_objectId, _pluginId, selectedMetricId) => {
      if (selectedMetricId === 101 || String(selectedMetricId) === '101') {
        duplicateCalls += 1;
      }
      if (selectedMetricId === null || selectedMetricId === undefined) {
        return FIRST_PAGE;
      }
      return [makeMetric(Number(selectedMetricId))];
    },
    loadInstances: async () => [],
    getResourceKey,
    resolvePlugin: (_plugins, group) => group.plugin,
    resolveLegacyMetric: () => null
  });
  assert.equal(duplicateCalls, 1, '同键重复指标请求仍应去重');

  const distinct = await loadSavedQueryResources({
    queryGroups: [makeGroup('host', 101, 6), makeGroup('remote', 201, 30)],
    pluginsMap: { '8': [{ id: 6 }, { id: 30 }] },
    metricsMap: {},
    instancesMap: {},
    loadPlugins: async () => {
      throw new Error('已有 plugin 缓存时不应再次加载');
    },
    loadMetrics: async (_objectId, pluginId, selectedMetricId) => {
      if (selectedMetricId === null || selectedMetricId === undefined) {
        return FIRST_PAGE;
      }
      return [makeMetric(Number(selectedMetricId))];
    },
    loadInstances: async () => [],
    getResourceKey,
    resolvePlugin: (_plugins, group) => group.plugin,
    resolveLegacyMetric: () => null
  });
  assert.ok(distinct.metricsMap['8_6']?.some((metric) => metric.id === 101));
  assert.ok(distinct.metricsMap['8_30']?.some((metric) => metric.id === 201));
  assert.equal(
    distinct.metricsMap['8_6']?.some((metric) => metric.id === 201),
    false
  );

  const legacyGroup = makeGroup('legacy', null);
  legacyGroup.legacyMetricName = 'metric_7';
  const legacyResult = await loadSavedQueryResources({
    queryGroups: [legacyGroup],
    pluginsMap: { '8': [{ id: 6, name: 'Host' }] },
    metricsMap: {},
    instancesMap: {},
    loadPlugins: async () => [{ id: 6, name: 'Host' }],
    loadMetrics: async () => FIRST_PAGE,
    loadInstances: async () => [],
    getResourceKey,
    resolvePlugin: (_plugins, group) => group.plugin,
    resolveLegacyMetric: (metrics, legacyName) =>
      metrics.find((metric) => metric.name === legacyName) || null
  });
  assert.equal(legacyResult.queryGroups[0].metric, 7);
  assert.equal(legacyResult.queryGroups[0].legacyMetricName, null);

  console.log(
    `monitor saved query metric merge: calls=${JSON.stringify(metricCalls)} merged=${merged.map((metric) => metric.id).filter((id) => id >= 101).join(',')}`
  );
};

void run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
