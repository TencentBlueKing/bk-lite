import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { getUnitCategories } from '../../utils/unitFormat';

const require = createRequire(import.meta.url);
const { IntlMessageFormat } = require('intl-messageformat');

const readLocale = (locale: 'en' | 'zh') =>
  JSON.parse(
    readFileSync(new URL(`../${locale}.json`, import.meta.url), 'utf8'),
  ) as Record<string, unknown>;

const flatten = (
  value: unknown,
  prefix = '',
  out: Record<string, string> = {},
): Record<string, string> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return out;
  }
  for (const [key, child] of Object.entries(value)) {
    const next = prefix ? `${prefix}.${key}` : key;
    if (typeof child === 'string') {
      out[next] = child;
    } else {
      flatten(child, next, out);
    }
  }
  return out;
};

const placeholders = (template: string) => {
  const names: string[] = [];
  let quoted = false;
  for (let index = 0; index < template.length; index += 1) {
    const char = template[index];
    if (char === "'") {
      if (template[index + 1] === "'") {
        index += 1;
        continue;
      }
      quoted = !quoted;
      continue;
    }
    if (quoted || char !== '{') {
      continue;
    }
    const end = template.indexOf('}', index);
    assert.notEqual(end, -1, template);
    const name = template.slice(index + 1, end).split(',')[0]?.trim();
    if (name) {
      names.push(name);
    }
    index = end;
  }
  return names.sort();
};

test('ops-analysis locales stay symmetric and ICU-parseable', () => {
  const en = flatten(readLocale('en'));
  const zh = flatten(readLocale('zh'));
  assert.deepEqual(Object.keys(en).sort(), Object.keys(zh).sort());

  for (const key of Object.keys(en)) {
    const enMessage = new IntlMessageFormat(en[key], 'en');
    const zhMessage = new IntlMessageFormat(zh[key], 'zh');
    assert.deepEqual(placeholders(en[key]), placeholders(zh[key]), key);
    if (key === 'dataSource.transform.contractParams') {
      assert.equal(enMessage.format(), 'V1 params is always {}');
      assert.equal(zhMessage.format(), 'V1 的 params 为空对象 {}');
    }
    if (key === 'dashboard.invalidConfiguredFieldsTip') {
      assert.match(String(enMessage.format({ fields: 'cpu' })), /cpu/);
      assert.match(String(zhMessage.format({ fields: 'cpu' })), /cpu/);
    }
    if (key === 'dashboard.cardListFieldUsedIn') {
      assert.match(String(enMessage.format({ slot: 'Title' })), /Title/);
      assert.match(String(zhMessage.format({ slot: '标题' })), /标题/);
    }
  }

  assert.equal(en['dashboard.addField'], 'Add');
  assert.equal(zh['dashboard.addField'], '添加');
});

test('unit categories use translated labels', () => {
  const categories = getUnitCategories((key) => `t:${key}`);
  assert.equal(categories[0]?.label, 't:dashboard.unitCategoryMisc');
  assert.equal(categories[0]?.units[0]?.label, 't:dashboard.unitNone');
  assert.equal(categories[0]?.units[0]?.id, 'none');
});
