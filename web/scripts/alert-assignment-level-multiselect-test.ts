import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import {
  LEVEL_MULTI_OPERATOR_OPTIONS,
  getMatchRuleOperatorOptions,
  getMatchRuleValueAfterOperatorChange,
  getMatchRuleValueSelectState,
  isEmptyMatchRuleValue,
  isLevelMultiSelectEnabled,
  normalizeMultipleRuleValue,
} from '../src/app/alarm/(pages)/settings/components/matchRuleValue';

assert.deepEqual(normalizeMultipleRuleValue('0'), ['0']);
assert.deepEqual(normalizeMultipleRuleValue(['0', '1']), ['0', '1']);
assert.deepEqual(normalizeMultipleRuleValue(undefined), []);
assert.equal(isEmptyMatchRuleValue([]), true);
assert.equal(isEmptyMatchRuleValue(null), true);
assert.equal(isEmptyMatchRuleValue(false), true);
assert.equal(isEmptyMatchRuleValue(0), false);
assert.equal(isEmptyMatchRuleValue('0'), false);
assert.equal(isLevelMultiSelectEnabled('level', true), true);
assert.equal(isLevelMultiSelectEnabled('title', true), false);
assert.deepEqual(LEVEL_MULTI_OPERATOR_OPTIONS, [
  { name: 'eq', desc: '等于' },
  { name: 'ne', desc: '不等于' },
]);

const fallbackOperatorOptions = [{ name: 'contains', desc: '包含' }];
assert.deepEqual(
  getMatchRuleOperatorOptions('level', true, fallbackOperatorOptions),
  LEVEL_MULTI_OPERATOR_OPTIONS,
);
assert.deepEqual(
  getMatchRuleOperatorOptions('title', true, fallbackOperatorOptions),
  fallbackOperatorOptions,
);
assert.deepEqual(getMatchRuleValueSelectState('level', true, '0'), {
  mode: 'multiple',
  value: ['0'],
});
assert.deepEqual(getMatchRuleValueSelectState('title', true, '0'), {
  mode: undefined,
  value: '0',
});
assert.equal(
  getMatchRuleValueAfterOperatorChange('level', true, ['0']),
  undefined,
);
assert.deepEqual(
  getMatchRuleValueAfterOperatorChange('level', false, ['0']),
  ['0'],
);
assert.deepEqual(
  getMatchRuleValueAfterOperatorChange('title', true, ['0']),
  ['0'],
);

const settingsRoot = new URL(
  '../src/app/alarm/(pages)/settings/',
  import.meta.url,
);
const levelMultiSelectCallSites = readdirSync(settingsRoot, {
  recursive: true,
  encoding: 'utf8',
})
  .filter((path) => path.endsWith('.tsx'))
  .filter((path) =>
    /<MatchRule\s+[\s\S]*?enableLevelMultiSelect[\s\S]*?\/>/.test(
      readFileSync(new URL(path, settingsRoot), 'utf8'),
    ),
  );
assert.deepEqual(levelMultiSelectCallSites, [
  'alertAssign/components/operateModal.tsx',
]);
console.log('alert assignment level multiselect validation passed');
