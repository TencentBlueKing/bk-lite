import assert from 'node:assert/strict';
import {
  LEVEL_MULTI_OPERATOR_OPTIONS,
  isEmptyMatchRuleValue,
  isLevelMultiSelectEnabled,
  normalizeMultipleRuleValue,
} from '../src/app/alarm/(pages)/settings/components/matchRuleValue';

assert.deepEqual(normalizeMultipleRuleValue('0'), ['0']);
assert.deepEqual(normalizeMultipleRuleValue(['0', '1']), ['0', '1']);
assert.deepEqual(normalizeMultipleRuleValue(undefined), []);
assert.equal(isEmptyMatchRuleValue([]), true);
assert.equal(isEmptyMatchRuleValue('0'), false);
assert.equal(isLevelMultiSelectEnabled('level', true), true);
assert.equal(isLevelMultiSelectEnabled('title', true), false);
assert.deepEqual(LEVEL_MULTI_OPERATOR_OPTIONS, [
  { name: 'eq', desc: '等于' },
  { name: 'ne', desc: '不等于' },
]);
console.log('alert assignment level multiselect validation passed');
