import assert from 'node:assert/strict';
import fs from 'node:fs';

import {
  NODE_MGMT_SYNC_STATUS_BADGE,
  createNodeMgmtSyncRequestGuard,
  getNodeMgmtSyncDisplayEmptyStateKey,
  getNodeMgmtSyncEmptyStateKey,
  getNodeMgmtSyncReasonTextKey,
  normalizeNodeMgmtSyncStatus,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/nodeMgmtSyncViewModel';

const normalizedStatuses = {
  waiting_sync: 'waiting_sync',
  running: 'running',
  submitted: 'submitted',
  success: 'success',
  partial_success: 'partial_success',
  blocked: 'blocked',
  failed: 'failed',
  timeout: 'timeout',
  error: 'failed',
  writing: 'running',
  force_stop: 'blocked',
} as const;

for (const [raw, expected] of Object.entries(normalizedStatuses)) {
  const result = normalizeNodeMgmtSyncStatus(raw);
  assert.equal(result.status, expected, `${raw} 必须归一化为 ${expected}`);
  assert.equal(result.isUnknown, false);
  assert.ok(result.status && NODE_MGMT_SYNC_STATUS_BADGE[result.status]);
}

for (const raw of ['unknown', 'future_backend_status', 'unexecuted', 42]) {
  const result = normalizeNodeMgmtSyncStatus(raw);
  assert.equal(result.status, 'blocked');
  assert.equal(result.isUnknown, true);
  assert.equal(NODE_MGMT_SYNC_STATUS_BADGE[result.status], 'error');
}

assert.equal(normalizeNodeMgmtSyncStatus(null).status, null);
assert.equal(
  getNodeMgmtSyncEmptyStateKey({ status: 'success', reasonCode: '', total: 0 }),
  'Collection.nodeMgmtSync.empty.noNodes'
);
for (const reasonCode of ['NODE_SOURCE_EMPTY', 'NO_VALID_NODES']) {
  assert.equal(
    getNodeMgmtSyncEmptyStateKey({ status: 'blocked', reasonCode, total: 0 }),
    'Collection.nodeMgmtSync.empty.noNodes'
  );
  assert.notEqual(
    getNodeMgmtSyncReasonTextKey(reasonCode),
    'Collection.nodeMgmtSync.reason.unknown',
    `${reasonCode} 必须映射到稳定本地化错误文案`
  );
}
assert.equal(
  getNodeMgmtSyncEmptyStateKey({ status: 'partial_success', reasonCode: '', total: 0 }),
  'Collection.nodeMgmtSync.empty.partialFailure'
);
assert.equal(
  getNodeMgmtSyncDisplayEmptyStateKey({
    message: { all: 0 },
    run: { status: 'blocked', reason_code: 'NO_ACCESS_POINT' },
    task: { health: { reason_code: '' } },
  }),
  'Collection.nodeMgmtSync.empty.noAccessPoint',
  '真实展示 payload 的父任务 NO_ACCESS_POINT 必须进入专用空态'
);

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: Error) => void;
}
const deferred = <T>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const testRequestGuard = async () => {
  const guard = createNodeMgmtSyncRequestGuard();
  guard.open();
  const requestA = guard.beginRequest();
  const responseA = deferred<string>();
  let rendered = '';
  const applyA = responseA.promise.then((value) => {
    if (guard.isRequestCurrent(requestA)) rendered = value;
  });

  guard.close();
  guard.open();
  const requestB = guard.beginRequest();
  const responseB = deferred<string>();
  const applyB = responseB.promise.then((value) => {
    if (guard.isRequestCurrent(requestB)) rendered = value;
  });
  responseB.resolve('B');
  await applyB;
  responseA.resolve('A');
  await applyA;
  assert.equal(rendered, 'B', '关闭后重开时旧 GET A 不得覆盖新 GET B');

  const mutation = guard.beginMutation();
  const put = deferred<string>();
  let taskState = 'optimistic';
  const applyPut = put.promise.catch(() => {
    if (guard.isMutationCurrent(mutation)) taskState = 'rollback';
  });
  guard.close();
  guard.open();
  taskState = 'reopened';
  put.reject(new Error('late failure'));
  await applyPut;
  assert.equal(taskState, 'reopened', '关闭重开后旧 PUT 失败不得回滚新页面状态');

  const currentMutation = guard.beginMutation();
  assert.equal(guard.isMutationCurrent(currentMutation), true);
  const mutationRefetch = guard.beginRequest();
  assert.equal(guard.isRequestCurrent(mutationRefetch), true);
  assert.equal(guard.isMutationCurrent(currentMutation), true, 'PUT 后 refetch 不得使当前 mutation 失效');
  guard.beginMutation();
  assert.equal(guard.isMutationCurrent(currentMutation), false, '较新的 mutation 必须栅栏旧 mutation');

  for (const locale of ['zh', 'en']) {
    const messages = JSON.parse(fs.readFileSync(`src/app/cmdb/locales/${locale}.json`, 'utf8'));
    const nodeMgmtSync = messages.Collection.nodeMgmtSync;
    assert.ok(nodeMgmtSync.status?.unknown, `${locale}: 缺少未知状态 fallback`);
    assert.ok(nodeMgmtSync.empty?.partialFailure, `${locale}: 缺少部分失败空态`);
    assert.ok(nodeMgmtSync.reason?.unknown, `${locale}: 缺少未知错误码脱敏 fallback`);
    assert.ok(nodeMgmtSync.reason?.nodeSourceEmpty, `${locale}: 缺少节点源为空文案`);
    assert.ok(nodeMgmtSync.reason?.noValidNodes, `${locale}: 缺少无有效节点文案`);
  }
};

testRequestGuard()
  .then(() => console.log('cmdb-node-mgmt-sync-health test passed'))
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
