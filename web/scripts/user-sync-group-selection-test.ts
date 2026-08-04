import assert from 'node:assert/strict';
import { filterSyncedGroupsForLocalUser } from '../src/app/system-manager/utils/userFormUtils';

const tree = [
  {
    title: '本地组织',
    key: 1,
    value: 1,
    children: [],
  },
  {
    title: '同步根组织',
    key: 2,
    value: 2,
    syncSource: 9,
    children: [
      {
        title: '同步子组织',
        key: 3,
        value: 3,
        syncSource: 9,
        children: [],
      },
    ],
  },
];

const groupsForCreate = filterSyncedGroupsForLocalUser(tree);
assert.deepEqual(groupsForCreate.map((group) => group.key), [1]);

const groupsForEdit = filterSyncedGroupsForLocalUser(tree, [3]);
assert.deepEqual(groupsForEdit.map((group) => group.key), [1, 2]);
assert.deepEqual(groupsForEdit[1].children.map((group) => group.key), [3]);

console.log('user sync group selection test passed');
