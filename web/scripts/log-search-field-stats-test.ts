import assert from 'node:assert/strict';

import {
  canExpandFieldStats,
  getFieldStatsAttribute,
} from '../src/app/log/(pages)/search/fieldStats';

assert.equal(getFieldStatsAttribute('message'), '_msg');
assert.equal(getFieldStatsAttribute('collect_type'), 'collect_type');

for (const field of ['timestamp', '_time', '_stream', '_stream_id']) {
  assert.equal(canExpandFieldStats(field), false, `${field} 不应提供统计展开入口`);
}

assert.equal(canExpandFieldStats('message'), true);
assert.equal(canExpandFieldStats('collect_type'), true);

console.log('log-search-field-stats validation passed');
