import * as assert from 'node:assert/strict';
import { resolveK8sCurrentInstanceOption } from '../src/app/monitor/dashboards/objects/k8s-cluster/instance';

const options = [
  {
    label: 'dev-cluster',
    value: "('k8s_dev',)",
    instanceIdValues: ['k8s_dev'],
    searchTokens: ['dev-cluster', 'k8s_dev']
  },
  {
    label: 'prod-cluster',
    value: "('k8s_prod',)",
    instanceIdValues: ['k8s_prod'],
    searchTokens: ['prod-cluster', 'k8s_prod']
  }
];

assert.equal(
  resolveK8sCurrentInstanceOption(options, "('k8s_dev',)", ['k8s_dev'], 'dev-cluster')?.label,
  'dev-cluster'
);

assert.equal(
  resolveK8sCurrentInstanceOption(options, 'k8s_dev', ['k8s_dev'], 'dev-cluster')?.value,
  "('k8s_dev',)"
);

assert.equal(
  resolveK8sCurrentInstanceOption(options, 'missing', ['missing'], 'missing'),
  undefined
);

console.log('k8s dashboard instance binding tests passed');
