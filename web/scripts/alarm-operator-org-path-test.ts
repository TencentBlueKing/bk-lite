import * as assert from 'node:assert/strict';
import {
  buildOrganizationPathMap,
  formatAlertOrganizationPath,
} from '../src/app/alarm/utils/organizationPath';

const tree = [
  {
    id: 1,
    name: '集团',
    subGroups: [
      {
        id: 2,
        name: '运维中心',
        subGroups: [{ id: 3, name: 'NOC' }],
      },
    ],
  },
];

const pathById = buildOrganizationPathMap(tree);
assert.equal(pathById.get('3'), '集团 / 运维中心 / NOC');

const nameById = new Map([['9', '共享值班']]);
assert.equal(
  formatAlertOrganizationPath([3, 9], pathById, nameById),
  '集团 / 运维中心 / NOC，共享值班'
);
assert.equal(formatAlertOrganizationPath([], new Map()), '');

console.log('alarm operator org path test passed');
