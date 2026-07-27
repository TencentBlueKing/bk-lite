import assert from 'node:assert/strict';
import { buildSearchParams, resolvePromqlWindow, toPromqlWindow } from '../src/app/monitor/dashboards/shared/utils';

assert.equal(toPromqlWindow(15 * 60 * 1000), '15m');
assert.equal(toPromqlWindow(60 * 60 * 1000), '1h');
assert.equal(toPromqlWindow(2 * 24 * 60 * 60 * 1000), '2d');
assert.equal(toPromqlWindow(90 * 1000), '90s');
assert.equal(toPromqlWindow(0), '15m');

assert.equal(
  resolvePromqlWindow({ timeRange: [1_700_000_000_000, 1_700_000_000_000 + 15 * 60 * 1000], originValue: 0 }),
  '15m'
);
assert.equal(
  resolvePromqlWindow({ timeRange: [1_700_000_000_000, 1_700_000_000_000 + 60 * 60 * 1000], originValue: 0 }),
  '1h'
);

const params = buildSearchParams(
  'clamp_min(increase(docker_container_status_restart_count{__$labels__}[__$window__]), 0)',
  'counts',
  ['docker-local'],
  ['instance_id'],
  { timeRange: [1_700_000_000_000, 1_700_000_000_000 + 15 * 60 * 1000], originValue: 0 }
);

assert.match(params.query, /\[15m\]/);
assert.doesNotMatch(params.query, /__\$window__/);
assert.doesNotMatch(params.query, /__\$labels__/);

const rateParams = buildSearchParams(
  'sum(rate(docker_container_net_rx_bytes{__$labels__}[__$window__])) by (instance_id)',
  'byteps',
  ['docker-local'],
  ['instance_id'],
  { timeRange: [1_700_000_000_000, 1_700_000_000_000 + 60 * 60 * 1000], originValue: 0 }
);
assert.match(rateParams.query, /\[1h\]/);
assert.doesNotMatch(rateParams.query, /\[5m\]/);

console.log('monitor-promql-window-test: ok');
