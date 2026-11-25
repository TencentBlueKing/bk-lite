import assert from 'node:assert/strict';
import {
  UNRECORDED,
  buildOperationLogChangeView,
  buildOperationLogDetailView,
  hasOperationDetail,
  normalizeOperationOutcome,
} from '../src/app/system-manager/utils/operationLogDetail';

assert.equal(hasOperationDetail({ detail: { after_data: { a: 1 } } }), true);
assert.equal(hasOperationDetail({ detail: {} }), false);
assert.equal(hasOperationDetail({ detail: null }), false);
assert.equal(hasOperationDetail({}), false);

assert.equal(normalizeOperationOutcome(''), UNRECORDED);
assert.equal(normalizeOperationOutcome(null), UNRECORDED);
assert.equal(normalizeOperationOutcome('success'), 'success');
assert.equal(normalizeOperationOutcome('failure'), 'failure');
assert.equal(normalizeOperationOutcome('accepted'), 'accepted');

const missingObject = buildOperationLogDetailView({
  username: 'alice',
  app: 'cmdb',
  app_name: '配置管理',
  source_ip: '1.1.1.1',
  operation_time: '2026-01-01 00:00:00',
});
assert.equal(missingObject.targetType, UNRECORDED);
assert.equal(missingObject.targetName, UNRECORDED);
assert.equal(missingObject.targetId, UNRECORDED);
assert.equal(missingObject.outcome, UNRECORDED);
assert.equal(missingObject.appName, '配置管理');
assert.equal(missingObject.changes.kind, 'unrecorded');

const emptyOutcomeWithDiff = buildOperationLogChangeView({
  action_type: 'update',
  outcome: '',
  detail: { before_data: { name: 'a' }, after_data: { name: 'b' } },
});
assert.equal(emptyOutcomeWithDiff.kind, 'unrecorded');

const failureHidesAfter = buildOperationLogChangeView({
  action_type: 'update',
  outcome: 'failure',
  detail: { before_data: { name: 'a' }, after_data: { name: 'submitted' } },
});
assert.equal(failureHidesAfter.kind, 'hidden');

const acceptedHides = buildOperationLogChangeView({
  action_type: 'execute',
  outcome: 'accepted',
  detail: { after_data: { status: 'queued' } },
});
assert.equal(acceptedHides.kind, 'hidden');

const updateOnlyChanged = buildOperationLogChangeView({
  action_type: 'update',
  outcome: 'success',
  detail: {
    before_data: { name: 'a', keep: 1 },
    after_data: { name: 'b', keep: 1 },
  },
});
assert.equal(updateOnlyChanged.kind, 'update');
if (updateOnlyChanged.kind === 'update') {
  assert.deepEqual(updateOnlyChanged.fields, [
    { key: 'name', before: 'a', after: 'b' },
  ]);
}

const createOnlyAfter = buildOperationLogChangeView({
  action_type: 'create',
  outcome: 'success',
  detail: { after_data: { name: 'new' }, before_data: { leaked: true } },
});
assert.equal(createOnlyAfter.kind, 'create');
if (createOnlyAfter.kind === 'create') {
  assert.deepEqual(createOnlyAfter.after, { name: 'new' });
}

const deleteOnlyBefore = buildOperationLogChangeView({
  action_type: 'delete',
  outcome: 'success',
  detail: { before_data: { name: 'gone' }, after_data: { leaked: true } },
});
assert.equal(deleteOnlyBefore.kind, 'delete');
if (deleteOnlyBefore.kind === 'delete') {
  assert.deepEqual(deleteOnlyBefore.before, { name: 'gone' });
}

const acceptedView = buildOperationLogDetailView({
  outcome: 'accepted',
  target_name: 'job-1',
  target_id: '9',
  target_type: 'job',
});
assert.equal(acceptedView.showAcceptedHint, true);
assert.equal(acceptedView.targetName, 'job-1');

console.log('PASS operation-log-detail');
