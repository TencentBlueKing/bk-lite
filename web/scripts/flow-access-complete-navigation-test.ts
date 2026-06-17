import * as assert from 'node:assert/strict';
import { buildFlowAssetListUrl } from '../src/app/monitor/utils/flowNavigation';

assert.equal(buildFlowAssetListUrl('15'), '/monitor/integration/asset?objId=15');
assert.equal(buildFlowAssetListUrl(15), '/monitor/integration/asset?objId=15');
assert.equal(buildFlowAssetListUrl(''), '/monitor/integration/asset');
assert.equal(buildFlowAssetListUrl(undefined), '/monitor/integration/asset');

console.log('flow access complete navigation tests passed');
