import assert from 'node:assert/strict';

import {
  buildClusterFilterOptions,
  filterInstanceOptionsByCluster,
  isInstanceOptionForIdentity,
  selectFirstInstanceInCluster
} from '../src/app/monitor/dashboards/shared/utils/instance.ts';

const options = [
  { label: 'pod-a', value: "('cluster-a', 'pod-a')", instanceIdValues: ['cluster-a', 'pod-a'] },
  { label: 'pod-b', value: "('cluster-a', 'pod-b')", instanceIdValues: ['cluster-a', 'pod-b'] },
  { label: 'pod-c', value: "('cluster-b', 'pod-c')", instanceIdValues: ['cluster-b', 'pod-c'] },
  { label: 'orphan', value: "('orphan',)", instanceIdValues: ['orphan'] }
];

assert.deepEqual(buildClusterFilterOptions(options), [
  { label: 'cluster-a', value: 'cluster-a', searchTokens: ['cluster-a'] },
  { label: 'cluster-b', value: 'cluster-b', searchTokens: ['cluster-b'] },
  { label: 'orphan', value: 'orphan', searchTokens: ['orphan'] }
]);

assert.deepEqual(
  filterInstanceOptionsByCluster(options, 'cluster-a').map((item) => item.label),
  ['pod-a', 'pod-b']
);
assert.deepEqual(
  filterInstanceOptionsByCluster(options, undefined).map((item) => item.label),
  ['pod-a', 'pod-b', 'pod-c', 'orphan']
);

assert.equal(selectFirstInstanceInCluster(options, 'cluster-b')?.value, "('cluster-b', 'pod-c')");
assert.equal(selectFirstInstanceInCluster(options, 'missing'), undefined);

assert.equal(
  isInstanceOptionForIdentity(options[0], "('cluster-a', 'pod-a')", ['cluster-a', 'pod-a']),
  true
);
assert.equal(
  isInstanceOptionForIdentity(options[1], "('cluster-a', 'pod-a')", ['cluster-a', 'pod-a']),
  false,
  '同集群但不同 Pod/Node 不能被识别为当前实例'
);

console.log('k8s cluster filter tests passed');
