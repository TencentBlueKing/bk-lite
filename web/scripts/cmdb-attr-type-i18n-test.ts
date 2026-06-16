import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { ATTR_TYPE_LIST } from '../src/app/cmdb/constants/asset';

const here = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(here, '../src/app/cmdb/locales');

type Nested = { [key: string]: string | Nested };

// Mirror of /api/locales route flattenMessages: nested JSON -> dot-keys.
const flatten = (obj: Nested, prefix = ''): Record<string, string> =>
  Object.keys(obj).reduce((acc: Record<string, string>, key) => {
    const value = obj[key];
    const prefixedKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      acc[prefixedKey] = value;
    } else {
      Object.assign(acc, flatten(value, prefixedKey));
    }
    return acc;
  }, {});

const loadMessages = (locale: 'zh' | 'en') =>
  flatten(JSON.parse(readFileSync(resolve(localesDir, `${locale}.json`), 'utf8')));

const zh = loadMessages('zh');
const en = loadMessages('en');

// Every attribute type label (rendered via t(item.name) in the add-attribute
// dropdown and the attribute list type column) must resolve in both locales,
// otherwise the UI shows the raw English token (e.g. "image" instead of "图片").
for (const { id, name } of ATTR_TYPE_LIST) {
  assert.ok(
    zh[name] !== undefined,
    `expected zh translation for attr type "${id}" via key "${name}"`
  );
  assert.ok(
    en[name] !== undefined,
    `expected en translation for attr type "${id}" via key "${name}"`
  );
}

console.log('cmdb attr type i18n test passed');
