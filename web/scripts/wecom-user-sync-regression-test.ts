import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const configFields = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx', import.meta.url),
  'utf8',
);
const configModal = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx', import.meta.url),
  'utf8',
);
const operateModal = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx', import.meta.url),
  'utf8',
);
const userSyncTypes = readFileSync(
  new URL('../src/app/system-manager/types/user-sync.ts', import.meta.url),
  'utf8',
);
const zh = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'));
const en = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'));

assert.match(
  configFields,
  /\}, \[departmentIdType, form, initialRootScopeValue, resolvedTemplate, rootDepartmentFieldKey, selectedInstanceId, t\]\);/,
  'department options must reload for instance or ID-type changes, not form-value changes',
);
assert.match(
  configModal,
  /const initialRootScopeValue = source\?\.business_config\?\.\[rootScopeFieldKey\];/,
  'the edit modal must read the saved root scope directly from the source',
);
assert.match(
  configModal,
  /initialRootScopeValue=\{typeof initialRootScopeValue === 'string' \? initialRootScopeValue : ''\}/,
  'the edit modal must pass the saved root scope without waiting for form effects',
);
assert.doesNotMatch(
  operateModal,
  /initialRootScopeValue=/,
  'the create modal must not provide an edit-only saved root scope',
);
assert.match(
  configFields,
  /useEffect\(\(\) => \{\n\s+currentRootDepartmentIdRef\.current = currentRootDepartmentId;\n\s+\}, \[currentRootDepartmentId\]\);/,
  'the latest saved department value must remain synchronized into the request ref',
);
assert.match(
  configFields,
  /current_root_department_id: currentRootDepartmentIdRef\.current \|\| initialRootScopeValue,/,
  'the first edit request must fall back to the saved source value before form effects run',
);
assert.match(
  configFields,
  /onChange=\{\(\) => \{\n\s+form\.setFields\(\[\{ name: namePath, errors: \[\] \}\]\);\n\s+setDepartmentSelectionMissing\(false\);\n\s+\}\}/,
  'the missing-selection warning must be cleared after a real user selection',
);
assert.doesNotMatch(configFields, /__all__|ALL_DEPARTMENT_SELECTION_ID|is_all/);
assert.doesNotMatch(operateModal, /__all__|ALL_DEPARTMENT_SELECTION_ID|is_all/);
assert.doesNotMatch(userSyncTypes, /__all__|ALL_DEPARTMENT_SELECTION_ID|is_all/);
assert.match(
  operateModal,
  /if \(isDepartmentSelectMode\(resolvedTemplate\)\) \{\n\s+delete nextBusinessConfig\.root_department_id;/,
  'new department-select forms must leave root_department_id undefined',
);
assert.match(
  configFields,
  /const nextValue = result\.selection_missing\n\s+\? ''\n\s+: result\.selected_id;/,
  'an empty selected_id must leave the field empty rather than selecting a default tree node',
);
assert.doesNotMatch(configFields, /items\[0\]/);
assert.equal(zh.system.channel.imNotificationPage.externalFieldOption.userid, '用户 ID');
assert.equal(en.system.channel.imNotificationPage.externalFieldOption.userid, 'User ID');
assert.equal(
  zh.system.user.userSyncPage.departmentSelectionInvalid,
  '当前选择的部门已不在应用可访问范围内，请重新选择',
);
assert.equal(
  en.system.user.userSyncPage.departmentSelectionInvalid,
  'The selected department is no longer within the application\'s accessible scope. Please select again.',
);

console.log('WeCom user-sync and IM notification regression tests passed');
