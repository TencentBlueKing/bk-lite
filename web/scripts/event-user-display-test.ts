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

const assertOperatorColumnIsHistoryOnly = (source: string) => {
  assert.match(
    source,
    /\.\.\.\(activeTab === 'historicalAlarms'[\s\S]*?dataIndex: 'operator'[\s\S]*?: \[\]\),/
  );
  assert.equal(source.match(/dataIndex: 'operator'/g)?.length, 1);
};

const logAlertPagePath = fileURLToPath(
  new URL('../src/app/log/(pages)/event/alert/page.tsx', import.meta.url)
);
const logAlertPageSource = readFileSync(logAlertPagePath, 'utf8');

assert.equal(
  logAlertPageSource.includes("dataIndex: 'collect_type_name'"),
  false
);
assertOperatorColumnIsHistoryOnly(logAlertPageSource);
assert.equal(logAlertPageSource.includes('<UserAvatar'), true);
assert.equal(
  logAlertPageSource.includes('formatUserDisplayName(operator, userList)'),
  true
);

const monitorAlertPagePath = fileURLToPath(
  new URL('../src/app/monitor/(pages)/event/alert/page.tsx', import.meta.url)
);
const monitorAlertPageSource = readFileSync(monitorAlertPagePath, 'utf8');
assertOperatorColumnIsHistoryOnly(monitorAlertPageSource);

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
