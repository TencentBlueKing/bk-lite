import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = dirname(fileURLToPath(import.meta.url));
const zh = JSON.parse(readFileSync(join(dir, 'zh.json'), 'utf8')).common;
const en = JSON.parse(readFileSync(join(dir, 'en.json'), 'utf8')).common;
assert.equal(typeof zh.noContentToCopy, 'string');
assert.equal(typeof en.noContentToCopy, 'string');
assert.notEqual(zh.noContentToCopy, en.noContentToCopy);
console.log('common.noContentToCopy ok');
