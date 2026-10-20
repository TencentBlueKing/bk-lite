import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { materialBatchDeleteFeedback } from '../src/app/opspilot/components/wiki/materialBatchDeleteFeedback';

const root = process.cwd();
const materialTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/MaterialTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

const success = materialBatchDeleteFeedback(
  { deleted_count: 2, failed: null, not_attempted: [] },
  (id) => String(id),
);
assert.equal(success?.level, 'success');
assert.equal(success?.messageKey, 'wiki.deleteSuccess');

const partial = materialBatchDeleteFeedback(
  {
    deleted_count: 1,
    failed: { id: 2, message: '资料来源身份已变化' },
    not_attempted: [3, 4],
  },
  (id) => (id === 3 ? '第三份' : '第四份'),
);
assert.equal(partial?.level, 'error');
assert.equal(partial?.messageKey, 'wiki.batchDeletePartial');
assert.equal(partial?.values?.deleted, 1);
assert.equal(partial?.values?.notAttempted, 2);
assert.equal(partial?.values?.notAttemptedNames, '第三份、第四份');
assert.equal(partial?.values?.failed, '资料来源身份已变化');

const failedOnly = materialBatchDeleteFeedback(
  { deleted_count: 0, failed: { id: 9, message: '资料正在构建中' }, not_attempted: [] },
  (id) => String(id),
);
assert.equal(failedOnly?.messageKey, 'wiki.batchDeleteFailed');
assert.notEqual(failedOnly?.level, 'success');

assert.match(materialTab, /materialBatchDeleteFeedback/);
assert.doesNotMatch(
  materialTab.slice(materialTab.indexOf('deleteMode === "batch"'), materialTab.indexOf('if (!deleteTarget)')),
  /deleted_count > 0[\s\S]*message\.success/,
);

for (const key of ['batchDeletePartial', 'batchDeleteFailed']) {
  assert.equal(typeof zh.wiki[key], 'string', `missing zh wiki.${key}`);
  assert.equal(typeof en.wiki[key], 'string', `missing en wiki.${key}`);
}

console.log('wiki material batch delete feedback validation passed');
