import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const userModalSource = readFileSync(
  resolve(process.cwd(), 'src/app/system-manager/(pages)/user/structure/userModal.tsx'),
  'utf8'
);
const userModalDataSource = readFileSync(
  resolve(process.cwd(), 'src/app/system-manager/hooks/useUserModalData.ts'),
  'utf8'
);

assert.match(
  userModalSource,
  /label=\{t\('common\.organization'\)\}[\s\S]*required=\{!isSuperuser\}/,
  'a normal user should always require organization selection'
);
assert.match(
  userModalSource,
  /label=\{t\('system\.user\.form\.role'\)\}[\s\S]*required=\{type === 'edit' && !isSuperuser\}/,
  'only editing a normal user should mark role as required'
);
assert.match(
  userModalDataSource,
  /if \(!isSuperuser && selectedGroups\.length === 0\)/,
  'a normal user should always require organization selection'
);
assert.match(
  userModalDataSource,
  /if \(!isSuperuser && !hasNormalGroupSelection\(selectedGroups, groupTreeData\)\)/,
  'a normal user should always require a normal organization'
);
assert.match(
  userModalDataSource,
  /if \(type === 'edit' && !isSuperuser && selectedRoles\.length === 0\)/,
  'only editing a normal user should require role selection'
);

console.log('PASS system-manager-pending-authorization-user');
