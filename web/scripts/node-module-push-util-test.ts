import assert from 'node:assert/strict';
import {
  getSoldModulePushTargets,
  hasSuccessfulModuleLink,
} from '../src/app/node-manager/utils/modulePush';

assert.deepEqual(getSoldModulePushTargets([]), ['cmdb', 'monitor']);
assert.deepEqual(getSoldModulePushTargets(null), ['cmdb', 'monitor']);
assert.deepEqual(
  getSoldModulePushTargets([{ name: 'cmdb' } as any]),
  ['cmdb']
);
assert.deepEqual(
  getSoldModulePushTargets([
    { name: 'cmdb' } as any,
    { name: 'monitor' } as any,
  ]),
  ['cmdb', 'monitor']
);
assert.deepEqual(getSoldModulePushTargets([{ name: 'node' } as any]), []);

assert.equal(hasSuccessfulModuleLink('42', {}, 'cmdb'), true);
assert.equal(
  hasSuccessfulModuleLink('', { cmdb: { state: 'ok' } }, 'cmdb'),
  true
);
assert.equal(
  hasSuccessfulModuleLink('', { cmdb: { state: 'skipped' } }, 'cmdb'),
  false
);
assert.equal(hasSuccessfulModuleLink('', {}, 'monitor'), false);

console.log('modulePush util tests passed');
