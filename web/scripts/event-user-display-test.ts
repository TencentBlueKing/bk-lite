import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  formatUserDisplayName,
  formatUserName
} from '../src/utils/userDisplay';

const users = [
  { id: '42', username: 'chenyong', display_name: '陈永' },
  { id: 7, username: 'rex', display_name: '' },
  { id: 8, username: 'alice', display_name: '爱丽丝', user_id: 'ext-8' }
];

assert.equal(formatUserDisplayName('chenyong', users), '陈永(chenyong)');
assert.equal(formatUserDisplayName('42', users), '陈永(chenyong)');
assert.equal(formatUserName(users[0]), '陈永(chenyong)');
assert.equal(formatUserDisplayName(7, users), 'rex');
assert.equal(formatUserDisplayName('ext-8', users), '爱丽丝(alice)');
assert.equal(formatUserDisplayName('deleted-user', users), 'deleted-user');
assert.equal(formatUserDisplayName('', users), '--');

const alertPagePath = fileURLToPath(
  new URL('../src/app/log/(pages)/event/alert/page.tsx', import.meta.url)
);
const alertPageSource = readFileSync(alertPagePath, 'utf8');

assert.equal(alertPageSource.includes("dataIndex: 'collect_type_name'"), false);
assert.equal(alertPageSource.includes("dataIndex: 'operator'"), false);

const monitorInfoPath = fileURLToPath(
  new URL(
    '../src/app/monitor/(pages)/event/alert/information.tsx',
    import.meta.url
  )
);
const monitorInfoSource = readFileSync(monitorInfoPath, 'utf8');
assert.equal(monitorInfoSource.includes('notice_users_display'), true);
assert.equal(
  monitorInfoSource.includes('row.notice_users || row.policy?.notice_users'),
  true
);

console.log('event user display validation passed');
