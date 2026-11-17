import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = dirname(fileURLToPath(import.meta.url));
const zh = JSON.parse(readFileSync(join(dir, 'zh.json'), 'utf8')).rum;
const en = JSON.parse(readFileSync(join(dir, 'en.json'), 'utf8')).rum;

const keys = [
  ['overview', 'allItems'],
  ['overview', 'moreItems'],
  ['monitors', 'basic'],
  ['monitors', 'conditionStep'],
  ['monitors', 'whenMetric'],
  ['monitors', 'noticeStep'],
  ['monitors', 'breadcrumb'],
  ['monitors', 'backAria'],
  ['monitors', 'notFound'],
  ['sessions', 'filterRoute'],
];

for (const [section, key] of keys) {
  assert.equal(typeof zh[section][key], 'string', `zh ${section}.${key}`);
  assert.equal(typeof en[section][key], 'string', `en ${section}.${key}`);
  assert.notEqual(zh[section][key], en[section][key], `${section}.${key}`);
}

assert.match(zh.overview.moreItems, /\{n\}/);
assert.match(en.overview.moreItems, /\{n\}/);
assert.match(zh.monitors.whenMetric, /\{metric\}/);
assert.match(en.monitors.whenMetric, /\{metric\}/);
console.log('rum missing keys: 10 ok');
