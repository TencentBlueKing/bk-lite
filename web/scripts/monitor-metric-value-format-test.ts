import assert from 'node:assert/strict';

import { formatMetricValue } from '../src/app/monitor/utils/formatMetricValue';

assert.equal(formatMetricValue('32', 'counts'), '32');
assert.equal(formatMetricValue('0.00', 'counts'), '0');
assert.equal(formatMetricValue('1.5', 'counts'), '1.5');
assert.equal(formatMetricValue('32', 'percent'), '32.00');
assert.equal(formatMetricValue('unknown', 'counts'), 'unknown');

console.log('monitor metric value format tests passed');
