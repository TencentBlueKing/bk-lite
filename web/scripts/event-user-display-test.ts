import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  formatUserDisplayName,
  formatUserName
} from '../src/utils/userDisplay';

const users = [
  { id: '42', username: 'chenyong', display_name: '陈永' },
  { id: 7, username: 'rex', display_name: '' }
];

assert.equal(formatUserDisplayName('chenyong', users), '陈永(chenyong)');
assert.equal(formatUserDisplayName('42', users), '陈永(chenyong)');
assert.equal(formatUserName(users[0]), '陈永(chenyong)');
assert.equal(formatUserDisplayName(7, users), 'rex');
assert.equal(formatUserDisplayName('deleted-user', users), 'deleted-user');
assert.equal(formatUserDisplayName('', users), '--');

const alertPagePath = fileURLToPath(
  new URL('../src/app/log/(pages)/event/alert/page.tsx', import.meta.url)
);
const alertPageSource = readFileSync(alertPagePath, 'utf8');

assert.equal(alertPageSource.includes("dataIndex: 'collect_type_name'"), false);
assert.equal(alertPageSource.includes("dataIndex: 'operator'"), false);

console.log('event user display validation passed');
