import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const formPath = new URL(
  '../src/app/conversation/components/custom-components/application-form.tsx',
  import.meta.url,
);

function dateLocaleResolver(source) {
  const match = source.match(/const dateLocale = ([^;]+);/);
  assert.ok(match, 'application form must define dateLocale in one expression');
  return new Function('locale', `"use strict"; return (${match[1]});`);
}

test('英文会话日期用 en-US，中文、空值和其他语言仍用 zh-CN', async () => {
  const source = await readFile(formPath, 'utf8');
  const dateLocale = dateLocaleResolver(source);

  assert.equal(dateLocale('en'), 'en-US');
  assert.equal(dateLocale('EN'), 'en-US');
  assert.equal(dateLocale('en-US'), 'en-US');
  assert.equal(dateLocale('zh'), 'zh-CN');
  assert.equal(dateLocale('zh-Hans'), 'zh-CN');
  assert.equal(dateLocale(''), 'zh-CN');
  assert.equal(dateLocale('ja'), 'zh-CN');

  const sample = new Date(2024, 2, 5, 8, 9);
  assert.notEqual(
    sample.toLocaleDateString(dateLocale('en')),
    sample.toLocaleDateString(dateLocale('zh')),
  );
  assert.equal(sample.toLocaleDateString(dateLocale('')), sample.toLocaleDateString('zh-CN'));
});

test('表单只把 dateLocale 传给 toLocale*，提交值仍是 formData', async () => {
  const source = await readFile(formPath, 'utf8');
  const calls = [...source.matchAll(/toLocale(?:String|DateString|TimeString)\(\s*([^\s,)]+)/g)];

  assert.equal(calls.length, 6);
  assert.deepEqual(calls.map((call) => call[1]), Array(6).fill('dateLocale'));
  assert.doesNotMatch(source, /toLocale(?:String|DateString|TimeString)\(\s*['"]zh-CN['"]/);

  const submitAt = source.indexOf('onSubmit?.(formData)');
  const displayAt = source.indexOf('date.toLocaleString(dateLocale)');
  assert.ok(submitAt > 0);
  assert.ok(displayAt > submitAt);
});
