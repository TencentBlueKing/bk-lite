import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const alarmDir = resolve(here, '../src/app/alarm');

const bindingSource = readFileSync(
  resolve(alarmDir, '(pages)/settings/actionRules/components/fieldBindingTable.tsx'),
  'utf8'
);
const matchRuleSource = readFileSync(
  resolve(alarmDir, '(pages)/settings/actionRules/components/matchRule.tsx'),
  'utf8'
);
const ruleListSource = readFileSync(
  resolve(alarmDir, 'constants/settings.ts'),
  'utf8'
);

assert.match(bindingSource, /label:\s*'告警ID'/);
assert.match(bindingSource, /value:\s*'alert_id'/);
assert.doesNotMatch(ruleListSource, /name:\s*'alert_id'/);
assert.doesNotMatch(matchRuleSource, /alert_id/);
