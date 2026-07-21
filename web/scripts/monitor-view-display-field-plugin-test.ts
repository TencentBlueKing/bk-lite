import assert from 'node:assert/strict';

import { resolveDisplayMetric } from '../src/app/monitor/(pages)/view/displayFieldMetric';

const metrics = [
  { id: 11, name: 'disk_used_percent', monitor_plugin_name: 'Host' },
  { id: 12, name: 'disk_used_percent', monitor_plugin_name: 'Windows WMI' },
  { id: 13, name: 'disk_used_percent', monitor_plugin_name: 'Host Remote' },
];

assert.equal(
  resolveDisplayMetric(metrics, { plugin: 'Host', metric: 'disk_used_percent' })?.id,
  11,
);
assert.equal(
  resolveDisplayMetric(metrics, { plugin: 'Host Remote', metric: 'disk_used_percent' })?.id,
  13,
);

console.log('monitor view display-field plugin scope validation passed');
