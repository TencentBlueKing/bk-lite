import assert from 'node:assert/strict';

import {
  getTimeSelectorDefaultValue,
  getTimeSelectorKey,
} from '../src/app/ops-analysis/components/paramsConfigTimeRange';

const quick = getTimeSelectorDefaultValue(10080);
assert.equal(quick.selectValue, 10080);
assert.equal(quick.rangePickerVaule, null);

const custom = getTimeSelectorDefaultValue([1000, 2000]);
assert.equal(custom.selectValue, 0);
assert.deepEqual(custom.rangePickerVaule?.map((value) => value.valueOf()), [1000, 2000]);

assert.notEqual(getTimeSelectorKey(10080), getTimeSelectorKey([1000, 2000]));
assert.equal(getTimeSelectorKey(undefined), getTimeSelectorKey(10080));

console.log('ops analysis params time range tests passed');
