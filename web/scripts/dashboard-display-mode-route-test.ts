import assert from 'node:assert/strict';
import {
  getDashboardDisplayModeFromParams,
  preserveDashboardDisplayMode,
  setDashboardDisplayModeInParams
} from '../src/app/monitor/dashboards/shared/utils/display-mode-route.ts';

const dashboardParams = new URLSearchParams('monitorObjId=6&name=Pod');
assert.equal(getDashboardDisplayModeFromParams(dashboardParams), 'dashboard');

const metricsParams = setDashboardDisplayModeInParams(dashboardParams, 'metrics');
assert.equal(metricsParams.get('view'), 'metrics');
assert.equal(getDashboardDisplayModeFromParams(metricsParams), 'metrics');
assert.equal(dashboardParams.get('view'), null);

const resetParams = setDashboardDisplayModeInParams(metricsParams, 'dashboard');
assert.equal(resetParams.get('view'), null);
assert.equal(getDashboardDisplayModeFromParams(resetParams), 'dashboard');

const nextObjectParams = preserveDashboardDisplayMode(
  new URLSearchParams('monitorObjId=7&name=Node'),
  new URLSearchParams('monitorObjId=6&name=Pod&view=metrics')
);
assert.equal(nextObjectParams.get('monitorObjId'), '7');
assert.equal(nextObjectParams.get('view'), 'metrics');

const nextDashboardParams = preserveDashboardDisplayMode(
  new URLSearchParams('monitorObjId=7&name=Node'),
  new URLSearchParams('monitorObjId=6&name=Pod')
);
assert.equal(nextDashboardParams.get('view'), null);

console.log('dashboard display mode route tests passed');
