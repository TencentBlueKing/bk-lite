import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { IntlMessageFormat } from 'intl-messageformat';

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

assert.equal(
  new IntlMessageFormat(en.alarms.notificationSummary, 'en').format({ total: 5, shown: 3 }),
  '5 notifications; showing the latest 3',
);
assert.equal(
  new IntlMessageFormat(zh.alarms.notificationSummary, 'zh').format({ total: 5, shown: 3 }),
  '共 5 次通知，显示最近 3 次',
);
assert.match(tooltipSource, /t\('alarms\.notificationSummary', undefined, \{/);
assert.doesNotMatch(tooltipSource, /\.replace\('{{total}}'/);

const visibleKeys = [
  'actionTriggerCreated',
  'actionTypeJob',
  'actionExecPending',
  'actionViewJob',
  'actionComingSoon',
  'actionTargetHost',
  'actionFallbackName',
  'actionRecordsRuleName',
];
for (const key of visibleKeys) {
  assert.equal(typeof zh.settings[key], 'string', key);
  assert.equal(typeof en.settings[key], 'string', key);
  if (key !== 'actionTypeItsm' && key !== 'actionTypeWebhook') {
    assert.notEqual(zh.settings[key], en.settings[key], key);
  }
}
assert.equal(zh.integration.precheck.title, '部署前检查');
assert.equal(en.integration.precheck.title, 'Pre-deployment checks');

console.log('alarm notification tooltip test passed');
