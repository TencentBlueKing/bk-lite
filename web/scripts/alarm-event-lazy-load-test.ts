import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const read = (path: string) =>
  readFileSync(resolve(process.cwd(), path), 'utf8');

const detailPaths = [
  'src/app/alarm/(pages)/alarms/components/alarmDetail.tsx',
  'src/app/alarm/components/alarm-detail-drawer/index.tsx',
];

for (const path of detailPaths) {
  const source = read(path);
  const eventRequests =
    source.match(/getEventListData\(\{ alert_id: formData\.id \}\)/g) || [];
  assert.equal(
    eventRequests.length,
    1,
    `${path} should have one Event request trigger`
  );
  assert.match(
    source,
    /activeTab !== 'event'/,
    `${path} should guard Event loading by the active tab`
  );
}

const sourceNamePaths = [
  'src/app/alarm/(pages)/alarms/components/alarmTable.tsx',
  'src/app/alarm/(pages)/alarms/components/baseInfo.tsx',
  'src/app/alarm/components/alarm-base-info/index.tsx',
  'src/app/alarm/components/alarm-detail-drawer/index.tsx',
  'src/app/alarm/types/alarms.ts',
];

for (const path of sourceNamePaths) {
  assert.doesNotMatch(
    read(path),
    /source_names/,
    `${path} should not expose source_names`
  );
}

console.log('alarm Event lazy-loading contract passed');
