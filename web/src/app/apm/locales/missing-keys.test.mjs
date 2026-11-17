import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = dirname(fileURLToPath(import.meta.url));
const zh = JSON.parse(readFileSync(join(dir, 'zh.json'), 'utf8')).apm;
const en = JSON.parse(readFileSync(join(dir, 'en.json'), 'utf8')).apm;
const keys = [
  ['alerts', 'budgetRemaining'],
  ['alerts', 'conditions'],
  ['alerts', 'matched'],
  ['alerts', 'notMatched'],
  ['policies', 'conditionSlowThreshold'],
  ['policies', 'conditionMinRequest'],
  ['policies', 'guardValueRequired'],
  ['explore', 'durationShare'],
  ['explore', 'errorSuffix'],
];
for (const [section, key] of keys) {
  assert.equal(typeof zh[section][key], 'string', `zh ${section}.${key}`);
  assert.equal(typeof en[section][key], 'string', `en ${section}.${key}`);
  assert.notEqual(zh[section][key], en[section][key], `${section}.${key}`);
}
assert.match(zh.policies.conditionSlowThreshold, /\{ref\}/);
assert.match(en.policies.conditionMinRequest, /\{ref\}/);
console.log('apm keys: 9 ok');
