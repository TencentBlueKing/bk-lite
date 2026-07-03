import assert from 'node:assert/strict';

import {
  buildCollectDetectFingerprint,
  getCollectDetectResultPresentation,
  getRowsForBatchCollectDetect,
  shouldAcceptCollectDetectResult,
} from '../src/app/monitor/(pages)/integration/list/detail/configure/automaticCollectDetect';

const rowA = {
  key: 'row-a',
  node_ids: ['node-a'],
  instance_name: 'mysql-a',
  password: 'secret',
};
const rowB = {
  key: 'row-b',
  node_ids: ['node-b'],
  instance_name: 'mysql-b',
};

assert.deepEqual(getRowsForBatchCollectDetect([rowA, rowB], ['row-b']), [rowB]);
assert.deepEqual(getRowsForBatchCollectDetect([rowA, rowB], []), []);

const fingerprintA = buildCollectDetectFingerprint({
  monitorPluginId: 1,
  monitorObjectId: 2,
  nodeId: 'node-a',
  instance: { b: 2, a: 1 },
});
const fingerprintB = buildCollectDetectFingerprint({
  monitorPluginId: 1,
  monitorObjectId: 2,
  nodeId: 'node-a',
  instance: { a: 1, b: 2 },
});
assert.equal(fingerprintA, fingerprintB);

assert.equal(shouldAcceptCollectDetectResult({ rowKey: 'row-a', fingerprint: fingerprintA }, { 'row-a': fingerprintA }), true);
assert.equal(shouldAcceptCollectDetectResult({ rowKey: 'row-a', fingerprint: fingerprintA }, { 'row-a': 'stale' }), false);

assert.deepEqual(getCollectDetectResultPresentation({ status: 'pending' }), {
  tone: 'processing',
  titleKey: 'monitor.integrations.collectDetectRunning',
});
assert.deepEqual(getCollectDetectResultPresentation({ status: 'failed' }), {
  tone: 'error',
  titleKey: 'monitor.integrations.collectDetectFailed',
});

console.log('monitor collect detect logic tests passed');
