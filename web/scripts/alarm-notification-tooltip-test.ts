import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const read = (path: string) => readFileSync(resolve(here, path), 'utf8');
const tooltipSource = read('../src/app/alarm/(pages)/alarms/components/notificationStatusTooltip.tsx');
const tableSource = read('../src/app/alarm/(pages)/alarms/components/alarmTable.tsx');
const baseInfoSource = read('../src/app/alarm/(pages)/alarms/components/baseInfo.tsx');
const typesSource = read('../src/app/alarm/types/alarms.ts');
const zh = JSON.parse(read('../src/app/alarm/locales/zh.json'));
const en = JSON.parse(read('../src/app/alarm/locales/en.json'));

assert.match(tooltipSource, /import \{[^}]*Tag[^}]*Tooltip[^}]*\} from 'antd'/);
assert.match(tooltipSource, /trigger=\{\['hover', 'focus'\]\}/);
assert.match(tooltipSource, /tabIndex=\{0\}/);
assert.match(tooltipSource, /records\.slice\(0, 5\)/);
assert.match(tooltipSource, /notify_time/);
assert.match(tooltipSource, /channel_name/);
assert.match(tooltipSource, /recipients/);
assert.match(tooltipSource, /failure_reason/);
assert.match(tooltipSource, /max-h-\[320px\]/);

assert.match(tableSource, /<NotificationStatusTooltip[\s\S]*?status=\{notify_status\}/);
assert.match(baseInfoSource, /<NotificationStatusTooltip[\s\S]*?status=\{detail\.notify_status\}/);
assert.doesNotMatch(baseInfoSource, /detail\.notification_status/);

assert.match(typesSource, /export interface NotifyRecord/);
assert.match(typesSource, /notify_status\?: string/);
assert.match(typesSource, /notify_total\?: number/);
assert.match(typesSource, /notify_records\?: NotifyRecord\[\]/);

for (const locale of [zh, en]) {
  for (const key of [
    'notificationSummary',
    'notificationTime',
    'notificationChannel',
    'notificationRecipients',
    'notificationResult',
    'notificationFailureReason',
    'notificationReasonUnavailable',
    'noNotificationRecords',
  ]) {
    assert.equal(typeof locale.alarms[key], 'string', `missing alarms.${key}`);
  }
}

console.log('alarm notification tooltip test passed');
