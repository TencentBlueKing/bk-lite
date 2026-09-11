import assert from 'node:assert/strict';

import { TOMCAT_DASHBOARD_CONFIG } from '../src/app/monitor/dashboards/objects/tomcat/config';
import {
  TOMCAT_ERROR_RATE_MIN_REQUEST_RATE,
  tomcatErrorRatePct,
} from '../src/app/monitor/dashboards/objects/tomcat/errorRate';

assert.equal(tomcatErrorRatePct(0.1, 0.1), 100);
assert.equal(tomcatErrorRatePct(0.5, 1), 50);
assert.equal(tomcatErrorRatePct(2, 4), 50);
assert.equal(tomcatErrorRatePct(0, 0), 0);
assert.ok(Number.isFinite(tomcatErrorRatePct(0, 0)));

const errorRateMetric = TOMCAT_DASHBOARD_CONFIG.metrics.find(
  (metric) => metric.name === 'tomcat_connector_error_rate_pct'
);
assert.ok(errorRateMetric);
assert.match(errorRateMetric.query, /1e-6/);
assert.doesNotMatch(
  errorRateMetric.query,
  /clamp_min\(rate\(tomcat_connector_request_count\{__\$labels__\}\[__\$window__\]\),\s*1\)/
);
assert.equal(TOMCAT_ERROR_RATE_MIN_REQUEST_RATE, 1e-6);

console.log('monitor-tomcat-error-rate-test: ok');
