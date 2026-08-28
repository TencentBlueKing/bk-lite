import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  ALARM_DISPLAY_FIELD_KEYS,
  ALARM_SETTINGS_STORAGE_KEY,
  ALARM_TABLE_ACTION_COLUMN_KEY,
  getAlarmTableChoosableColumns,
  parseAlarmSettings,
  readAlarmDisplayFieldKeys,
  resolveAlarmTableColumns,
  saveAlarmDisplayFieldKeys,
} from '../src/app/alarm/utils/alarmTableColumns';

const here = dirname(fileURLToPath(import.meta.url));
const tableSource = readFileSync(
  resolve(here, '../src/app/alarm/(pages)/alarms/components/alarmTable.tsx'),
  'utf8'
);
const pageSource = readFileSync(
  resolve(here, '../src/app/alarm/(pages)/alarms/page.tsx'),
  'utf8'
);

const columns = [
  { key: 'level' },
  { key: 'title' },
  { key: 'content' },
  { key: 'incident_name' },
  { key: ALARM_TABLE_ACTION_COLUMN_KEY },
];

assert.deepEqual(
  getAlarmTableChoosableColumns(columns).map((column) => column.key),
  ['level', 'title', 'content', 'incident_name'],
  '操作列不进入可配置候选'
);

assert.deepEqual(
  resolveAlarmTableColumns(columns, null).map((column) => column.key),
  ['level', 'title', 'content', 'incident_name', 'action'],
  '未保存过列配置时保持当前默认列与操作列'
);

assert.deepEqual(
  resolveAlarmTableColumns(columns, [
    'content',
    'title',
    'missing',
    'action',
    'level',
  ]).map((column) => column.key),
  ['content', 'title', 'level', 'action'],
  '按保存顺序显示列，忽略未知列，操作列始终在最右'
);

assert.deepEqual(
  resolveAlarmTableColumns(columns, []).map((column) => column.key),
  ['action'],
  '空配置只保留操作列'
);

class MemoryStorage {
  private data = new Map<string, string>();

  getItem(key: string) {
    return this.data.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
}

const storage = new MemoryStorage();
assert.equal(readAlarmDisplayFieldKeys(storage), null);

storage.setItem(
  ALARM_SETTINGS_STORAGE_KEY,
  JSON.stringify({ myAlarms: true, pageSize: 50 })
);
saveAlarmDisplayFieldKeys(['title', 'content'], storage);
assert.deepEqual(
  parseAlarmSettings(storage.getItem(ALARM_SETTINGS_STORAGE_KEY)),
  {
    myAlarms: true,
    pageSize: 50,
    [ALARM_DISPLAY_FIELD_KEYS]: ['title', 'content'],
  },
  '保存列配置时必须合并已有 alarmSettings，不能覆盖我的告警等偏好'
);
assert.deepEqual(readAlarmDisplayFieldKeys(storage), ['title', 'content']);

storage.setItem(ALARM_SETTINGS_STORAGE_KEY, '{not json');
assert.equal(readAlarmDisplayFieldKeys(storage), null, '损坏的设置视为未配置');

storage.setItem(
  ALARM_SETTINGS_STORAGE_KEY,
  JSON.stringify({ displayFieldKeys: ['title', 1] })
);
assert.equal(readAlarmDisplayFieldKeys(storage), null, '非法列配置视为未配置');

assert.match(tableSource, /fieldSetting=\{\{/);
assert.match(tableSource, /showSetting:\s*true/);
assert.match(
  tableSource,
  /const choosableFields = getAlarmTableChoosableColumns\(columns\)/
);
assert.match(tableSource, /choosableFields,/);
assert.match(tableSource, /onSelectFields=\{onSelectFields\}/);
assert.match(tableSource, /resolveAlarmTableColumns\(columns, displayFieldKeys\)/);
assert.match(tableSource, /saveAlarmDisplayFieldKeys/);
assert.match(tableSource, /ALARM_TABLE_ACTION_COLUMN_KEY/);
assert.match(
  pageSource,
  new RegExp(`getItem\\(['"]${ALARM_SETTINGS_STORAGE_KEY}['"]\\)`)
);

console.log('alarm table column preference test passed');
