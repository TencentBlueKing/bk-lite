import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { getArchivedActionPresentation } from '../src/app/system-manager/utils/archivedGroupActions';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

assert.deepEqual(
  getArchivedActionPresentation({}),
  { type: 'empty' },
  '子组织行没有 capability，操作列留空',
);

assert.deepEqual(
  getArchivedActionPresentation({ can_restore: false, can_permanently_delete: false }),
  { type: 'sync_reconcile_reason' },
  '同步源仍在但两端能力均为 false 时，仍展示对账原因而不是空占位',
);

assert.deepEqual(
  getArchivedActionPresentation({ can_restore: true, can_permanently_delete: true }),
  { type: 'buttons', can_restore: true, can_permanently_delete: true },
);

assert.deepEqual(
  getArchivedActionPresentation({ can_restore: false, can_permanently_delete: true }),
  { type: 'buttons', can_restore: false, can_permanently_delete: true },
);

const drawer = readFileSync(
  join(root, 'src/app/system-manager/components/group/ArchivedGroupDrawer.tsx'),
  'utf8',
);
assert.match(drawer, /getArchivedActionPresentation/);
assert.match(drawer, /system\.group\.syncReconcileArchived/);
assert.match(drawer, /system\.group\.syncReconcileArchivedHint/);
assert.match(drawer, /system\.group\.permanentlyDeleteConfirmCxtSynced/);
assert.doesNotMatch(drawer, /return '--'/);

for (const locale of ['zh', 'en'] as const) {
  const payload = JSON.parse(
    readFileSync(join(root, `src/app/system-manager/locales/${locale}.json`), 'utf8'),
  ) as { system: { group: Record<string, string> } };
  assert.equal(typeof payload.system.group.syncReconcileArchived, 'string');
  assert.equal(typeof payload.system.group.syncReconcileArchivedHint, 'string');
  assert.equal(typeof payload.system.group.permanentlyDeleteConfirmCxtSynced, 'string');
  assert.ok(payload.system.group.syncReconcileArchived.length > 0);
  assert.ok(payload.system.group.syncReconcileArchivedHint.length > 0);
  assert.ok(payload.system.group.permanentlyDeleteConfirmCxtSynced.length > 0);
}

console.log('archived-group-actions-test: ok');
