import assert from 'node:assert/strict';

import { buildFlowEndpointGuideStep, shouldShowSingleFlowEndpoint } from '../src/app/monitor/utils/flowAccessGuide';

const netflowEndpoints = [
  {
    protocol: 'netflow_v5',
    protocol_name: 'NetFlow v5',
    endpoint: 'udp://10.10.41.149:2055',
    port: 2055,
  },
  {
    protocol: 'netflow_v9',
    protocol_name: 'NetFlow v9',
    endpoint: 'udp://10.10.41.149:2056',
    port: 2056,
  },
];

const translate = (key: string, _fallback?: unknown, values?: Record<string, unknown>) => {
  if (key === 'monitor.integrations.flow.guideStepSetVersionEndpoints') {
    return `请按导出版本选择采集端或目的端地址：${values?.endpoints}。`;
  }
  if (key === 'monitor.integrations.flow.guideStepSetEndpoint') {
    return `请将采集端或目的端地址配置为 ${values?.endpoint}。`;
  }
  return key;
};

const versionStep = buildFlowEndpointGuideStep({
  endpoint: 'udp://10.10.41.149:2056',
  listenerEndpoints: netflowEndpoints,
  t: translate,
});

assert.equal(
  versionStep,
  '请按导出版本选择采集端或目的端地址：NetFlow v5：udp://10.10.41.149:2055；NetFlow v9：udp://10.10.41.149:2056。'
);
assert.equal(shouldShowSingleFlowEndpoint(netflowEndpoints), false);

const sflowStep = buildFlowEndpointGuideStep({
  endpoint: 'udp://10.10.41.149:6343',
  listenerEndpoints: [
    {
      protocol: 'sflow',
      protocol_name: 'sFlow',
      endpoint: 'udp://10.10.41.149:6343',
      port: 6343,
    },
  ],
  t: translate,
});

assert.equal(sflowStep, '请将采集端或目的端地址配置为 udp://10.10.41.149:6343。');
assert.equal(shouldShowSingleFlowEndpoint([]), true);

console.log('flow access guide step tests passed');
