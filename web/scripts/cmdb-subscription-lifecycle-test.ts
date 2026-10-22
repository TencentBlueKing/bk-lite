import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  isInstanceFilterReady,
  isInstanceLifecycleTrigger,
  lifecycleNeedsWatchFields,
} from '../src/app/cmdb/utils/subscriptionLifecycle.ts';

const here = dirname(fileURLToPath(import.meta.url));
const zh = JSON.parse(readFileSync(resolve(here, '../src/app/cmdb/locales/zh.json'), 'utf8'));
const en = JSON.parse(readFileSync(resolve(here, '../src/app/cmdb/locales/en.json'), 'utf8'));
const subscriptionForm = readFileSync(
  resolve(here, '../src/app/cmdb/components/subscription/subscriptionRuleForm.tsx'),
  'utf8',
);
const drawerForm = readFileSync(
  resolve(here, '../src/app/cmdb/components/cmdb-subscription-drawer/subscriptionRuleForm.tsx'),
  'utf8',
);
const subscriptionSelector = readFileSync(
  resolve(here, '../src/app/cmdb/components/subscription/instanceSelector.tsx'),
  'utf8',
);
const drawerSelector = readFileSync(
  resolve(here, '../src/app/cmdb/components/cmdb-subscription-drawer/instanceSelector.tsx'),
  'utf8',
);
const subscriptionTrigger = readFileSync(
  resolve(here, '../src/app/cmdb/components/subscription/triggerTypeConfig.tsx'),
  'utf8',
);
const drawerTrigger = readFileSync(
  resolve(here, '../src/app/cmdb/components/cmdb-subscription-drawer/triggerTypeConfig.tsx'),
  'utf8',
);

assert.equal(isInstanceFilterReady('condition', { query_list: [] }), true);
assert.equal(isInstanceFilterReady('condition', undefined), true);
assert.equal(isInstanceFilterReady('condition', { query_list: [{ field: 'ip' }] }), true);
assert.equal(isInstanceFilterReady('condition', { query_list: 'bad' }), false);
assert.equal(isInstanceFilterReady('instances', { instance_uuids: [] }), false);
assert.equal(isInstanceFilterReady('instances', { instance_uuids: ['63e4a531-b6bb-43cc-9eae-8eb8a09f795e'] }), true);

assert.equal(lifecycleNeedsWatchFields([]), false);
assert.equal(lifecycleNeedsWatchFields(['relation_change']), false);
assert.equal(lifecycleNeedsWatchFields(['instance_added']), true);
assert.equal(lifecycleNeedsWatchFields(['attribute_change']), true);
assert.equal(lifecycleNeedsWatchFields(['instance_deleted']), true);
assert.equal(isInstanceLifecycleTrigger('expiration'), false);

for (const copy of [zh.subscription, en.subscription]) {
  assert.ok(copy.emptyConditionHint);
  assert.ok(copy.triggerTypeInstanceAdded);
  assert.ok(copy.triggerTypeAttributeChange);
  assert.ok(copy.triggerTypeInstanceDeleted);
  assert.ok(copy.lifecycleFieldHint);
}

assert.equal(zh.subscription.emptyConditionHint, '未添加条件时，订阅该模型在当前组织下的全部实例');
assert.equal(zh.subscription.triggerTypeInstanceAdded, '新增');
assert.equal(zh.subscription.triggerTypeAttributeChange, '修改');
assert.equal(zh.subscription.triggerTypeInstanceDeleted, '删除');
assert.equal(
  en.subscription.emptyConditionHint,
  'With no conditions, all instances of this model in the current organization are subscribed',
);
assert.equal(en.subscription.triggerTypeInstanceAdded, 'Create');
assert.equal(en.subscription.triggerTypeAttributeChange, 'Update');
assert.equal(en.subscription.triggerTypeInstanceDeleted, 'Delete');

for (const source of [subscriptionForm, drawerForm]) {
  assert.match(source, /isInstanceFilterReady/);
  assert.match(source, /lifecycleNeedsWatchFields/);
  assert.doesNotMatch(source, /query_list\.length > 0/);
}

for (const source of [subscriptionSelector, drawerSelector]) {
  assert.match(source, /subscription\.emptyConditionHint/);
}

for (const source of [subscriptionTrigger, drawerTrigger]) {
  assert.match(source, /instance_added/);
  assert.match(source, /instance_deleted/);
  assert.match(source, /subscription\.lifecycleFieldHint/);
}

console.log('cmdb subscription lifecycle contract ok');
