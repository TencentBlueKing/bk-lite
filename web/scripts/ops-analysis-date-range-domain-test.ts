import assert from 'node:assert/strict';

import {
  DATE_RANGE_TYPES,
  DEFAULT_DATE_RANGE_VALUE,
} from '../src/app/ops-analysis/types/dateRange';
import {
  getDateRangeTimezone,
  resolveDateRange,
  validateDateRangeValue,
} from '../src/app/ops-analysis/utils/dateRange';

assert.deepEqual(DATE_RANGE_TYPES, [
  'today',
  'yesterday',
  'this_week',
  'last_week',
  'this_month',
  'last_month',
  'last_7_days',
  'last_30_days',
  'last_90_days',
  'custom',
]);
assert.deepEqual(DEFAULT_DATE_RANGE_VALUE, { rangeType: 'last_7_days' });

for (const rangeType of DATE_RANGE_TYPES) {
  const value = rangeType === 'custom'
    ? { rangeType, startDate: '2026-07-01', endDate: '2026-07-17' }
    : { rangeType };
  assert.equal(validateDateRangeValue(value).valid, true, rangeType);
}

assert.equal(validateDateRangeValue(null).valid, true);
for (const invalidValue of [
  undefined,
  [],
  { rangeType: 'last30days' },
  { rangeType: 'custom', startDate: '2026-07-01' },
  { rangeType: 'custom', startDate: '2026-02-30', endDate: '2026-03-01' },
  { rangeType: 'custom', startDate: '2026-7-01', endDate: '2026-07-17' },
  { rangeType: 'custom', startDate: '2026-07-17T00:00:00Z', endDate: '2026-07-18' },
  { rangeType: 'custom', startDate: 1784246400000, endDate: 1784332800000 },
  { rangeType: 'custom', startDate: '2026-07-17', endDate: '2026-07-01' },
  { rangeType: 'last_7_days', startDate: '2026-07-01', endDate: '2026-07-17' },
  { rangeType: 'today', extra: true },
]) {
  assert.equal(validateDateRangeValue(invalidValue).valid, false, JSON.stringify(invalidValue));
}

const context = {
  referenceNow: '2026-07-17T03:08:00.176Z',
  timezone: 'Asia/Shanghai',
};
const expectedRanges = {
  today: ['2026-07-17', '2026-07-17'],
  yesterday: ['2026-07-16', '2026-07-16'],
  this_week: ['2026-07-13', '2026-07-17'],
  last_week: ['2026-07-06', '2026-07-12'],
  this_month: ['2026-07-01', '2026-07-17'],
  last_month: ['2026-06-01', '2026-06-30'],
  last_7_days: ['2026-07-11', '2026-07-17'],
  last_30_days: ['2026-06-18', '2026-07-17'],
  last_90_days: ['2026-04-19', '2026-07-17'],
} as const;

for (const [rangeType, expected] of Object.entries(expectedRanges)) {
  assert.deepEqual(resolveDateRange({ rangeType }, context), expected, rangeType);
}

assert.deepEqual(
  resolveDateRange(
    { rangeType: 'custom', startDate: '2026-07-01', endDate: '2026-07-17' },
    context,
  ),
  ['2026-07-01', '2026-07-17'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'custom', startDate: '2026-07-17', endDate: '2026-07-17' },
    context,
  ),
  ['2026-07-17', '2026-07-17'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'custom', startDate: '2027-01-01', endDate: '2027-12-31' },
    context,
  ),
  ['2027-01-01', '2027-12-31'],
);
assert.equal(resolveDateRange(null, context), null);
assert.equal(resolveDateRange({ rangeType: 'unknown' }, context), null);

assert.deepEqual(
  resolveDateRange(
    { rangeType: 'this_week' },
    { referenceNow: '2026-07-12T12:00:00Z', timezone: 'Asia/Shanghai' },
  ),
  ['2026-07-06', '2026-07-12'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'this_week' },
    { referenceNow: '2026-07-13T12:00:00Z', timezone: 'UTC' },
  ),
  ['2026-07-13', '2026-07-13'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'this_month' },
    { referenceNow: '2026-07-01T12:00:00Z', timezone: 'UTC' },
  ),
  ['2026-07-01', '2026-07-01'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'today' },
    { referenceNow: '2024-02-29T12:00:00Z', timezone: 'UTC' },
  ),
  ['2024-02-29', '2024-02-29'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'last_week' },
    { referenceNow: '2026-03-02T12:00:00Z', timezone: 'UTC' },
  ),
  ['2026-02-23', '2026-03-01'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'last_month' },
    { referenceNow: '2026-01-01T12:00:00Z', timezone: 'UTC' },
  ),
  ['2025-12-01', '2025-12-31'],
);

const timezoneBoundaryNow = '2026-07-17T23:30:00Z';
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'today' },
    { referenceNow: timezoneBoundaryNow, timezone: 'America/Los_Angeles' },
  ),
  ['2026-07-17', '2026-07-17'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'today' },
    { referenceNow: timezoneBoundaryNow, timezone: 'Asia/Shanghai' },
  ),
  ['2026-07-18', '2026-07-18'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'last_7_days' },
    { referenceNow: '2026-03-09T06:30:00Z', timezone: 'America/New_York' },
  ),
  ['2026-03-03', '2026-03-09'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'today' },
    { referenceNow: '2026-03-08T06:30:00Z', timezone: 'America/New_York' },
  ),
  ['2026-03-08', '2026-03-08'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'today' },
    { referenceNow: '2026-03-08T07:30:00Z', timezone: 'America/New_York' },
  ),
  ['2026-03-08', '2026-03-08'],
);

assert.equal(getDateRangeTimezone('Asia/Tokyo'), 'Asia/Tokyo');
assert.equal(getDateRangeTimezone('  Asia/Tokyo  '), 'Asia/Tokyo');
assert.equal(
  getDateRangeTimezone(),
  Intl.DateTimeFormat().resolvedOptions().timeZone,
);
assert.doesNotThrow(() => getDateRangeTimezone('Invalid/Timezone'));
assert.equal(
  getDateRangeTimezone('Invalid/Timezone'),
  Intl.DateTimeFormat().resolvedOptions().timeZone,
);

const browserTimezone = getDateRangeTimezone();
assert.doesNotThrow(() => resolveDateRange(
  { rangeType: 'today' },
  { referenceNow: timezoneBoundaryNow, timezone: 'Invalid/Timezone' },
));
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'today' },
    { referenceNow: timezoneBoundaryNow, timezone: 'Invalid/Timezone' },
  ),
  resolveDateRange(
    { rangeType: 'today' },
    { referenceNow: timezoneBoundaryNow, timezone: browserTimezone },
  ),
);

console.log('ops analysis date range domain tests passed');
