import assert from 'node:assert/strict';
import { hasOperationDetail } from '../src/app/system-manager/utils/operationLogDetail';

assert.equal(hasOperationDetail({ detail: { after_data: { a: 1 } } }), true);
assert.equal(hasOperationDetail({ detail: {} }), false);
assert.equal(hasOperationDetail({ detail: null }), false);
assert.equal(hasOperationDetail({}), false);
console.log('PASS operation-log-detail');
