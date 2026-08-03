import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const configFields = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx', import.meta.url),
  'utf8',
);
const zh = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'));
const en = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'));

assert.match(
  configFields,
  /\}, \[departmentIdType, currentRootDepartmentId, form, resolvedTemplate, rootDepartmentFieldKey, selectedInstanceId, t\]\);/,
  'department options must reload after the saved root department reaches the edit form',
);
assert.equal(zh.system.channel.imNotificationPage.externalFieldOption.userid, '用户 ID');
assert.equal(en.system.channel.imNotificationPage.externalFieldOption.userid, 'User ID');

console.log('WeCom user-sync and IM notification regression tests passed');
