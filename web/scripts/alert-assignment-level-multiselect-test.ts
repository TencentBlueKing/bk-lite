import assert from 'node:assert/strict';
import { invalidMatchRules } from '../src/app/alarm/utils/multivalueRules';

// 级别实际值为单枚举，条件允许多个完整候选值。
assert.equal(invalidMatchRules([[{key:'level',operator:'eq',value:['0','1']}]],false,'assignment'),true);
assert.equal(invalidMatchRules([[{key:'level',operator:'any_of',value:['0','1']}]],false,'assignment'),false);
assert.equal(invalidMatchRules([[{key:'level',operator:'none_of',value:['0']}]],false,'assignment'),false);
assert.equal(invalidMatchRules([[{key:'source_names',operator:'all_of',value:['平台A','平台B']}]],false,'assignment'),false);
assert.equal(invalidMatchRules([[{key:'push_source_ids',operator:'all_of',value:['a','b']}]],false,'assignment'),false);
console.log('alert candidate and set validation passed');
