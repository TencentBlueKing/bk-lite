import * as assert from 'node:assert/strict';
import {
  buildFlowExistingAssetOptions,
  buildExistingFlowAssetFormPatch,
  filterFlowExistingAssetsByCloudRegion,
  normalizeFlowFallbackSamplingRate
} from '../src/app/monitor/utils/flowAsset';

const patch = buildExistingFlowAssetFormPatch("('switch-1',)", {
  instance_id: "('switch-1',)",
  instance_name: 'Core Switch',
  cloud_region_id: '1',
  ip: '10.0.0.12',
  organization: [7, 8],
  fallback_sampling_rate: '2000'
});

assert.deepEqual(patch, {
  instance_id: "('switch-1',)",
  name: 'Core Switch',
  cloud_region_id: 1,
  ip: '10.0.0.12',
  organizations: [7, 8],
  fallback_sampling_rate: 2000
});

const defaultedPatch = buildExistingFlowAssetFormPatch("('switch-2',)", {
  instance_id: "('switch-2',)",
  name: 'Edge Switch'
});

assert.equal(defaultedPatch.fallback_sampling_rate, 1000);

const currentShapePatch = buildExistingFlowAssetFormPatch("('router-1',)", {
  instance_id: "('router-1',)",
  name: 'Core Router',
  cloud_region_id: 2,
  ip: '10.0.0.13',
  organizations: [9],
  fallback_sampling_rate: 0
});

assert.deepEqual(currentShapePatch, {
  instance_id: "('router-1',)",
  name: 'Core Router',
  cloud_region_id: 2,
  ip: '10.0.0.13',
  organizations: [9],
  fallback_sampling_rate: 0
});

assert.equal(normalizeFlowFallbackSamplingRate('invalid'), 1000);
assert.equal(normalizeFlowFallbackSamplingRate(null), 1000);

const assets = [
  {
    instance_id: "('switch-1',)",
    instance_name: 'Core Switch',
    cloud_region_id: '1',
    ip: '10.0.0.12'
  },
  {
    instance_id: "('router-1',)",
    instance_name: 'Core Router',
    cloud_region_id: 2,
    ip: '10.0.0.13'
  }
];

assert.deepEqual(
  filterFlowExistingAssetsByCloudRegion(assets, 1).map((item) => item.instance_id),
  ["('switch-1',)"]
);
assert.deepEqual(
  filterFlowExistingAssetsByCloudRegion(assets, '2').map((item) => item.instance_id),
  ["('router-1',)"]
);
assert.deepEqual(filterFlowExistingAssetsByCloudRegion(assets, undefined), assets);

assert.deepEqual(buildFlowExistingAssetOptions(assets), [
  {
    value: "('switch-1',)",
    label: 'Core Switch / 10.0.0.12'
  },
  {
    value: "('router-1',)",
    label: 'Core Router / 10.0.0.13'
  }
]);

console.log('flow asset existing selection tests passed');
