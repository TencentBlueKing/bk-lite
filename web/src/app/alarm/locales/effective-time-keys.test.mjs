import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = dirname(fileURLToPath(import.meta.url));
const zh = JSON.parse(readFileSync(join(dir, 'zh.json'), 'utf8')).settings;
const en = JSON.parse(readFileSync(join(dir, 'en.json'), 'utf8')).settings;
const keys = [
  'effectiveOnce', 'effectiveDaily', 'effectiveWeekly', 'effectiveMonthly',
  'weekdayMon', 'weekdayTue', 'weekdayWed', 'weekdayThu', 'weekdayFri', 'weekdaySat', 'weekdaySun',
];
for (const key of keys) {
  assert.equal(typeof zh[key], 'string', key);
  assert.equal(typeof en[key], 'string', key);
  assert.notEqual(zh[key], en[key], key);
}
console.log('alarm effective time keys ok');
