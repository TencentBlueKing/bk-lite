import assert from 'node:assert/strict';

import {
  getCleanupTimeoutMax,
  normalizeCleanupTimeout
} from '../src/app/monitor/(pages)/integration/object/cleanupTimeout';

assert.deepEqual(
  normalizeCleanupTimeout({
    cleanup_timeout_value: 30,
    cleanup_timeout_unit: 'minute'
  }),
  { value: 30, unit: 'minute' }
);

assert.deepEqual(normalizeCleanupTimeout({ cleanup_timeout_days: 7 }), {
  value: 7,
  unit: 'day'
});

assert.deepEqual(normalizeCleanupTimeout({}), { value: 1, unit: 'day' });
assert.equal(getCleanupTimeoutMax('minute'), 1440);
assert.equal(getCleanupTimeoutMax('day'), 365);

console.log('monitor cleanup timeout contract: OK');
