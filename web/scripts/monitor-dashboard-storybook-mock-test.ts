import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createStorybookMonitorApiClient } from '../.storybook/mocks/monitor-dashboard-request';
import { NODE_DASHBOARD_CONFIG } from '../src/app/monitor/dashboards/objects/k8s-node/config';
import { renderChart } from '../src/app/monitor/utils/common';
import {
  buildSearchParams,
  getLatestChartValue,
  toMetricSeries
} from '../src/app/monitor/dashboards/shared/utils';

const api = createStorybookMonitorApiClient();
const DATABASE_DASHBOARD_KEYS = ['mysql', 'redis', 'mongodb', 'mssql', 'postgres', 'elasticsearch'];
const MIDDLEWARE_DASHBOARD_KEYS = [
  'nginx',
  'docker',
  'activemq',
  'apache',
  'consul',
  'rabbitmq',
  'ibmmq',
  'tomcat',
  'zookeeper'
];

const assertVisibleSeries = async (query: string, sourceUnit: string, identity: {
  instanceId: string;
  instanceName: string;
  instanceIdKeys?: string[];
  instanceIdValues?: string[];
}) => {
  const result = await api.get('/monitor/api/metrics_instance/query_range/', {
    params: {
      query,
      source_unit: sourceUnit
    }
  });

  const chartData = renderChart(result?.data?.result || [], [
    {
      instance_id_values: identity.instanceIdValues || [identity.instanceId],
      instance_id_keys: identity.instanceIdKeys || ['instance_id'],
      instance_id: identity.instanceId,
      instance_name: identity.instanceName,
      dimensions: [],
      title: 'storybook metric'
    }
  ]);

  assert.ok(result?.data?.result?.length, `${query} should return metric series`);
  assert.ok(chartData.length, `${query} should render chart points`);
  assert.ok(
    Number(chartData.at(-1)?.value1) >= 0,
    `${query} should expose a visible latest value`
  );

  return chartData;
};

const main = async () => {
  const storybookMain = readFileSync('.storybook/main.ts', 'utf8');
  const databaseStories = readFileSync('src/stories/monitor/dashboards/database.stories.tsx', 'utf8');
  const middlewareStories = readFileSync('src/stories/monitor/dashboards/middleware.stories.tsx', 'utf8');
  assert.ok(
    storybookMain.includes("name: '@/utils/request'") && storybookMain.includes('onlyModule: true'),
    'Storybook must put an exact @/utils/request alias before the Next @ alias so dashboard stories use the mock'
  );
  const expectedStoryKeys = [...DATABASE_DASHBOARD_KEYS, ...MIDDLEWARE_DASHBOARD_KEYS];
  for (const key of expectedStoryKeys) {
    const storySource = DATABASE_DASHBOARD_KEYS.includes(key)
      ? databaseStories
      : middlewareStories;
    assert.ok(
      storySource.includes(`dashboardKey: '${key}'`),
      `${key} dashboard should have a Storybook story`
    );
    const instances = await api.get(`/monitor/api/monitor_instance/${key}/list/`);
    assert.ok(instances.results?.[0]?.instance_id, `${key} story should have a mock instance`);
    await assertVisibleSeries(
      `storybook_${key}_healthy_metric{instance_id=~"${instances.results[0].instance_id}"}`,
      'percent',
      {
        instanceId: instances.results[0].instance_id,
        instanceName: instances.results[0].instance_name
      }
    );
  }

  await assertVisibleSeries(
    'clamp_max(100 - avg(ping_percent_packet_loss{instance_id=~"local-ping"}), 100)',
    'percent',
    { instanceId: 'local-ping', instanceName: '127.0.0.1' }
  );
  await assertVisibleSeries(
    'avg(net_response_result_code{instance_id=~"local-tcp"} == bool 0) * 100',
    'percent',
    { instanceId: 'local-tcp', instanceName: '127.0.0.1:3000' }
  );
  await assertVisibleSeries(
    '100 * ( sum(irate(prometheus_remote_write_container_cpu_usage_seconds_total{instance_type="k8s",instance_id=~"orbstack",pod=~"demo-pod-1"}[5m])) by (instance_id,pod) / on(instance_id,pod) sum(prometheus_remote_write_kube_pod_container_resource_limits{instance_type="k8s", resource="cpu",instance_id=~"orbstack",pod=~"demo-pod-1"}) by (instance_id,pod) )',
    'percent',
    {
      instanceId: 'demo-pod-1',
      instanceName: 'demo-pod-1',
      instanceIdKeys: ['instance_id', 'pod'],
      instanceIdValues: ['orbstack', 'demo-pod-1']
    }
  );

  const pingInstances = await api.get('/monitor/api/monitor_instance/ping/list/');
  assert.deepEqual(pingInstances.results?.[0]?.instance_id_values, ['local-ping']);
  const podInstances = await api.post('/monitor/api/monitor_instance/k8s-pod/search/', { page_size: -1 });
  assert.deepEqual(podInstances.results?.[0]?.instance_id_values, ['orbstack', 'demo-pod-1']);

  for (const metricName of ['node_status_condition', 'node_cpu_utilization', 'node_memory_utilization', 'node_disk_usage_rate']) {
    const metric = NODE_DASHBOARD_CONFIG.metrics.find((item) => item.name === metricName);
    assert.ok(metric, `${metricName} config should exist`);
    const result = await api.get(
      '/monitor/api/metrics_instance/query_range/',
      {
        params: buildSearchParams(
          metric.query,
          metric.unit,
          ['orbstack', 'orb-node-1'],
          ['cluster', 'node'],
          { timeRange: [], originValue: 15 },
          undefined,
          false,
          60
        )
      }
    );
    const series = toMetricSeries(metric, result, 'orb-node-1', 'orb-node-1', ['orbstack', 'orb-node-1'], ['cluster', 'node']);
    assert.ok(series.viewData.length, `${metricName} should render dashboard view data`);
    assert.ok(Number.isFinite(getLatestChartValue(series.viewData)), `${metricName} should expose a latest value`);
  }

  console.log('monitor dashboard storybook mock ok');
};

main();
