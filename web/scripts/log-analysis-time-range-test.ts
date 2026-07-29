import assert from 'node:assert/strict';

import {
  calculateLogTimeInterval,
  getDashboardQueryLimit,
} from '../src/app/log/(pages)/analysis/dashBoard/timeRangeUtils';

const minute = 60 * 1000;
const hour = 60 * minute;
const day = 24 * hour;

assert.equal(calculateLogTimeInterval(0, 15 * minute), '1m');
assert.equal(calculateLogTimeInterval(0, hour), '1m');
assert.equal(calculateLogTimeInterval(0, 6 * hour), '5m');
assert.equal(calculateLogTimeInterval(0, 12 * hour), '10m');
assert.equal(calculateLogTimeInterval(0, day), '30m');
assert.equal(calculateLogTimeInterval(0, 7 * day), '2h');
assert.equal(calculateLogTimeInterval(0, 30 * day), '12h');
assert.equal(calculateLogTimeInterval(12 * hour, 0), '10m');

assert.equal(
  getDashboardQueryLimit('* | stats by (_time:${_time}) count() as total'),
  1000
);
assert.equal(getDashboardQueryLimit('* | stats count() as total'), 100);
assert.equal(getDashboardQueryLimit(undefined), 100);

console.log('log analysis time range tests passed');
