import assert from 'node:assert/strict';
import {
  buildCollectorOperationListParams,
  getCollectorOperationSelection
} from '../src/app/node-manager/utils/nodeOperation.ts';

const armNode = {
  key: 'linux-arm',
  id: 'linux-arm',
  operating_system: 'linux',
  cpu_architecture: 'arm64'
};

const unknownArchNode = {
  key: 'linux-unknown',
  id: 'linux-unknown',
  operating_system: 'linux',
  cpu_architecture: ''
};

const armSelection = getCollectorOperationSelection([armNode]);
assert.equal(armSelection.disabled, false, 'known ARM64 node should allow collector operations');
assert.equal(armSelection.operatingSystem, 'linux');
assert.equal(armSelection.cpuArchitecture, 'arm64');

assert.deepEqual(
  buildCollectorOperationListParams({
    operatingSystem: armSelection.operatingSystem,
    cpuArchitecture: armSelection.cpuArchitecture,
    typeTag: 'monitor'
  }),
  {
    node_operating_system: 'linux',
    cpu_architecture: 'arm64',
    tags: 'monitor'
  },
  'collector operation query should include structured CPU architecture'
);

const unknownSelection = getCollectorOperationSelection([unknownArchNode]);
assert.equal(
  unknownSelection.disabled,
  true,
  'unknown architecture should block collector operation selection'
);
assert.equal(unknownSelection.reason, 'unknown_architecture');

console.log('collector-operation-architecture tests passed');
