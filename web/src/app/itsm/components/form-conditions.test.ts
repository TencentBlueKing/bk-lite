import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';
import { matches } from './form-conditions';

const cases = JSON.parse(readFileSync(resolve(process.cwd(), '../server/apps/itsm/tests/fixtures/form_conditions.json'), 'utf8'));
it.each(cases)('按服务端条件语义判断 %j', (rule, values, expected) => {
  expect(matches(rule, values)).toBe(expected);
});
