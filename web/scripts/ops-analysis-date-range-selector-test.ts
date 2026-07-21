import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import dayjs from 'dayjs';

import {
  completeCustomDateRange,
  getDateRangeSelectorValue,
  toDateRangePickerValue,
} from '../src/app/ops-analysis/components/dateRangeSelectorModel';

assert.deepEqual(getDateRangeSelectorValue(undefined), { rangeType: 'last_7_days' });
assert.equal(getDateRangeSelectorValue(null), null);
assert.deepEqual(toDateRangePickerValue({
  rangeType: 'custom', startDate: '2026-07-01', endDate: '2026-07-17',
})?.map((item) => item.format('YYYY-MM-DD')), ['2026-07-01', '2026-07-17']);
assert.equal(completeCustomDateRange([dayjs('2026-07-01'), null]), null);
assert.deepEqual(completeCustomDateRange([
  dayjs('2026-07-01'), dayjs('2026-07-17'),
]), { rangeType: 'custom', startDate: '2026-07-01', endDate: '2026-07-17' });

const source = readFileSync(
  new URL('../src/app/ops-analysis/components/dateRangeSelector.tsx', import.meta.url),
  'utf8',
);
assert.match(source, /DatePicker/);
assert.match(source, /RangePicker/);
assert.match(source, /allowClear/);
assert.match(source, /onChange\?\.\(null\)/);
assert.match(source, /validateDateRangeValue/);
assert.match(source, /value !== undefined/);
assert.match(source, /customOpen\s*\?\s*customDraft\s*:\s*toDateRangePickerValue\(effectiveValue\)/);
assert.match(source, /customOpen\s*\|\|\s*effectiveValue\?\.rangeType === 'custom'\s*\?/);
assert.match(source, /CalendarOutlined/);
assert.match(source, /zIndex:\s*customOpen\s*\|\|\s*effectiveValue\?\.rangeType === 'custom'/);
assert.doesNotMatch(source, /TimeSelector|toISOString|valueOf\(\)|unix\(/);

console.log('ops analysis date range selector tests passed');
