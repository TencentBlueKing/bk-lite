import assert from 'node:assert/strict';

import {
  buildDefaultManualPluginConfig,
  normalizeDashboardDisplay
} from '../src/app/monitor/hooks/integration/configContracts';

const legacyItems = normalizeDashboardDisplay(['kafka_up_gauge']);
assert.deepEqual(legacyItems, [
  {
    indexId: 'kafka_up_gauge',
    displayDimension: []
  }
]);

const standardItem = {
  indexId: 'interfaces',
  displayDimension: ['ifName'],
  displayType: 'table'
};
const standardItems = normalizeDashboardDisplay([standardItem]);
assert.equal(standardItems[0], standardItem);
assert.deepEqual(standardItems[0], standardItem);

const manualConfig = buildDefaultManualPluginConfig();
assert.equal(manualConfig.formItems, null);
assert.deepEqual(manualConfig.defaultForm, {});
assert.deepEqual(manualConfig.getParams({}), {
  instance_id: '',
  instance_name: ''
});
assert.equal(manualConfig.getConfigText({}), '');

console.log('monitor config contracts passed');
