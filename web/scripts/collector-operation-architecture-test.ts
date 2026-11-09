import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  buildCollectorOperationListParams,
  collectorOperationBlockedMessageKey,
  getCollectorOperationSelection,
  isCollectorOperationMenuDisabled
} from '../src/app/node-manager/utils/nodeOperation.ts';
import { EXECUTOR_TYPE_TAG } from '../src/app/node-manager/utils/collectorConfig.ts';

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

assert.deepEqual(
  buildCollectorOperationListParams({
    operatingSystem: armSelection.operatingSystem,
    cpuArchitecture: armSelection.cpuArchitecture,
    typeTag: EXECUTOR_TYPE_TAG
  }),
  {
    node_operating_system: 'linux',
    cpu_architecture: 'arm64'
  },
  'executor operations should not hide candidates behind an app tag filter'
);

const unknownSelection = getCollectorOperationSelection([unknownArchNode]);
assert.equal(
  unknownSelection.disabled,
  true,
  'unknown architecture should block collector operation selection'
);
assert.equal(unknownSelection.reason, 'unknown_architecture');
assert.equal(
  isCollectorOperationMenuDisabled(unknownSelection),
  false,
  'unknown architecture keeps the collector menu clickable'
);

const linuxAmd64 = {
  key: 'linux-amd64',
  id: 'linux-amd64',
  operating_system: 'linux',
  cpu_architecture: 'amd64'
};
const linuxX64 = {
  key: 'linux-x64',
  id: 'linux-x64',
  operating_system: 'linux',
  cpu_architecture: 'x86_64'
};
const linuxAarch64 = {
  key: 'linux-aarch64',
  id: 'linux-aarch64',
  operating_system: 'linux',
  cpu_architecture: 'aarch64'
};
const windowsX64 = {
  key: 'windows-x64',
  id: 'windows-x64',
  operating_system: 'windows',
  cpu_architecture: 'x86_64'
};

const aliasSelection = getCollectorOperationSelection([linuxAmd64, linuxX64]);
assert.equal(aliasSelection.disabled, false, 'amd64 and x86_64 are one architecture');
if (!aliasSelection.disabled) {
  assert.equal(aliasSelection.cpuArchitecture, 'x86_64');
}
assert.equal(isCollectorOperationMenuDisabled(aliasSelection), false);

const armAliasSelection = getCollectorOperationSelection([armNode, linuxAarch64]);
assert.equal(armAliasSelection.disabled, false, 'arm64 and aarch64 are one architecture');
if (!armAliasSelection.disabled) {
  assert.equal(armAliasSelection.cpuArchitecture, 'arm64');
}

const mixedOsSelection = getCollectorOperationSelection([linuxX64, windowsX64]);
assert.equal(mixedOsSelection.disabled, true);
if (mixedOsSelection.disabled) {
  assert.equal(mixedOsSelection.reason, 'mixed_operating_system');
}
assert.equal(
  isCollectorOperationMenuDisabled(mixedOsSelection),
  false,
  'mixed operating systems keep the collector menu clickable'
);
assert.equal(
  collectorOperationBlockedMessageKey(mixedOsSelection),
  'node-manager.cloudregion.node.collectorOperationMixedOperatingSystem'
);

const mixedArchSelection = getCollectorOperationSelection([linuxX64, armNode]);
assert.equal(mixedArchSelection.disabled, true);
if (mixedArchSelection.disabled) {
  assert.equal(mixedArchSelection.reason, 'mixed_cpu_architecture');
}
assert.equal(
  isCollectorOperationMenuDisabled(mixedArchSelection),
  false,
  'mixed CPU architectures keep the collector menu clickable'
);
assert.equal(
  collectorOperationBlockedMessageKey(mixedArchSelection),
  'node-manager.cloudregion.node.collectorOperationMixedCpuArchitecture'
);

const emptySelection = getCollectorOperationSelection([]);
assert.equal(isCollectorOperationMenuDisabled(emptySelection), true);

const pageSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/node-manager/(pages)/cloudregion/node/page.tsx'
  ),
  'utf8'
);
const menuGate = pageSource.slice(
  pageSource.indexOf('const enableOperateCollecter'),
  pageSource.indexOf('const enableOperateController')
);
assert.match(
  menuGate,
  /isCollectorOperationMenuDisabled\(\s*getCollectorOperationSelection/,
  'collector menu disabled state must use the shared clickable-block rule'
);
assert.doesNotMatch(
  menuGate,
  /reason !== 'unknown_architecture'/,
  'mixed selections must not stay disabled beside unknown architecture'
);
assert.match(
  pageSource,
  /disabled=\{enableOperateCollecter\}/,
  'collector dropdown must read the shared disabled flag'
);

const clickHandler = pageSource.slice(
  pageSource.indexOf('const handleCollectorMenuClick'),
  pageSource.indexOf('const SidecarmenuProps')
);
const blockedBranch = clickHandler.indexOf('if (selection.disabled === true)');
const showModal = clickHandler.indexOf('showModal');
assert.ok(blockedBranch >= 0 && showModal > blockedBranch);
assert.match(
  clickHandler.slice(blockedBranch, showModal),
  /collectorOperationBlockedMessageKey\(selection\)/,
  'mixed click must resolve the existing toast key'
);
assert.match(
  clickHandler.slice(blockedBranch, showModal),
  /message\.error/,
  'mixed click must toast before leaving the handler'
);
assert.match(
  clickHandler.slice(blockedBranch, showModal),
  /return;/,
  'mixed click must return before opening the install modal'
);

console.log('collector-operation-architecture tests passed');
