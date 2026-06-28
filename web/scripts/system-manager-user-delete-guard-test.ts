import assert from 'node:assert/strict';
import {
  canDirectlyDeleteUser,
  getBlockedDeleteSelection,
  shouldBlockBatchDelete,
} from '../src/app/system-manager/utils/userDeleteGuards';

const manualUser = {
  key: '1',
  username: 'manual-user',
  email: 'manual@example.com',
  display_name: 'Manual User',
  roles: [],
  groups: [],
  sync_source: null,
};

const syncedUser = {
  key: '2',
  username: 'synced-user',
  email: 'synced@example.com',
  display_name: 'Synced User',
  roles: [],
  groups: [],
  sync_source: 7,
};

assert.equal(canDirectlyDeleteUser(manualUser), true);
assert.equal(canDirectlyDeleteUser(syncedUser), false);
assert.equal(shouldBlockBatchDelete([manualUser]), false);
assert.equal(shouldBlockBatchDelete([manualUser, syncedUser]), true);
assert.deepEqual(getBlockedDeleteSelection([manualUser, syncedUser]), [syncedUser]);

console.log('PASS system-manager-user-delete-guard');
