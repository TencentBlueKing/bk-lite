import * as assert from 'node:assert/strict';
import {
  getPluginConfigFetchDecision,
  isSameTemplatePlugin
} from '../src/app/monitor/(pages)/integration/asset/templateConfigDrawerLogic';

const hostRemote = {
  name: 'Host Remote',
  plugin_id: 30,
  collector: 'Telegraf',
  collect_type: 'http',
  status: 'normal',
  collect_mode: 'auto'
};
const windowsWmi = {
  name: 'Windows WMI',
  plugin_id: 48,
  collector: 'Telegraf',
  collect_type: 'http',
  status: 'normal',
  collect_mode: 'auto'
};
const reportedOnly = {
  name: 'Windows WMI',
  plugin_id: 48,
  collector: 'Telegraf',
  collect_type: 'http',
  status: 'normal',
  collect_mode: 'manual'
};

assert.equal(isSameTemplatePlugin(hostRemote, hostRemote), true);
assert.equal(isSameTemplatePlugin(hostRemote, windowsWmi), false);
assert.deepEqual(getPluginConfigFetchDecision(hostRemote, windowsWmi), {
  shouldChangeSelection: true,
  shouldFetchConfig: true
});
assert.deepEqual(getPluginConfigFetchDecision(hostRemote, hostRemote), {
  shouldChangeSelection: false,
  shouldFetchConfig: false
});
assert.deepEqual(getPluginConfigFetchDecision(hostRemote, reportedOnly), {
  shouldChangeSelection: true,
  shouldFetchConfig: false
});

console.log('template config drawer logic tests passed');
