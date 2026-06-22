import assert from 'node:assert/strict';
import {
  getMetricDimensionNames,
  sanitizeGroupBy
} from '../src/app/monitor/utils/metricDimensions';

const mixedDimensions = [
  'device',
  { name: 'interface', description: 'Interface' },
  '',
  null,
  { name: '  ' },
  { name: 'mount' }
];

assert.deepEqual(getMetricDimensionNames(mixedDimensions), [
  'device',
  'interface',
  'mount'
]);

assert.deepEqual(sanitizeGroupBy(['instance_id', null, '', 'device', 'device']), [
  'instance_id',
  'device'
]);

console.log('monitor metric dimension helpers ok');
