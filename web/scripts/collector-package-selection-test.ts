import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  buildCollectorPackageListParams,
  describeCollectorInstallTarget,
  selectCollectorPackageVersions
} from '../src/app/node-manager/utils/collectorPackageSelection.ts';

const linuxNode = {
  id: 'linux-1',
  operating_system: 'linux',
  cpu_architecture: 'x86_64'
};
const windowsNode = {
  id: 'windows-1',
  operating_system: 'windows',
  cpu_architecture: 'x86_64'
};
const armNode = {
  id: 'linux-arm',
  operating_system: 'linux',
  cpu_architecture: 'aarch64'
};

const packages = [
  {
    id: 6,
    version: '1.28.0',
    os: 'windows',
    cpu_architecture: 'x86_64',
    name: 'telegraf.exe'
  },
  {
    id: 9,
    version: '1.28.0',
    os: 'linux',
    cpu_architecture: 'x86_64',
    name: 'telegraf'
  },
  {
    id: 4,
    version: '1.30.0',
    os: 'linux',
    cpu_architecture: 'arm64',
    name: 'telegraf-arm'
  },
  {
    id: 11,
    version: '1.30.0',
    os: 'linux',
    cpu_architecture: 'amd64',
    name: 'telegraf-amd64'
  },
  {
    id: 3,
    version: '1.10.0',
    os: 'linux',
    cpu_architecture: 'x86_64',
    name: 'telegraf-old'
  }
];

const linuxTarget = describeCollectorInstallTarget([linuxNode]);
assert.equal(linuxTarget.ok, true);
if (linuxTarget.ok) {
  assert.equal(linuxTarget.os, 'linux');
  assert.equal(linuxTarget.cpuArchitecture, 'x86_64');
  assert.deepEqual(
    buildCollectorPackageListParams({
      objectName: 'Telegraf',
      os: linuxTarget.os,
      cpuArchitecture: linuxTarget.cpuArchitecture
    }),
    {
      object: 'Telegraf',
      os: 'linux',
      cpu_architecture: 'x86_64',
      type: 'collector'
    }
  );
}

assert.equal(
  buildCollectorPackageListParams({
    objectName: 'Telegraf',
    os: '',
    cpuArchitecture: ''
  }),
  null,
  'empty os/arch must not build a package list request'
);

const selection = selectCollectorPackageVersions(packages, 'linux', 'x86_64');
assert.deepEqual(
  selection.options.map((option) => option.value),
  [11, 9, 3],
  'default order is newest linux/x86_64 package, never the windows package'
);
assert.equal(selection.defaultPackageId, 11);
assert.deepEqual(
  selection.options.map((option) => option.label),
  [
    '1.30.0 (linux / x86_64)',
    '1.28.0 (linux / x86_64)',
    '1.10.0 (linux / x86_64)'
  ]
);
assert.equal(
  new Set(selection.options.map((option) => option.label.split(' ')[0])).size,
  selection.options.length,
  'version labels stay unique after dropping other architectures'
);

const armSelection = selectCollectorPackageVersions(packages, 'Linux', 'aarch64');
assert.deepEqual(
  armSelection.options.map((option) => option.value),
  [4]
);

const mixedOs = describeCollectorInstallTarget([linuxNode, windowsNode]);
assert.equal(mixedOs.ok, false);
if (!mixedOs.ok) {
  assert.equal(mixedOs.reason, 'mixed_operating_system');
}

const mixedArch = describeCollectorInstallTarget([linuxNode, armNode]);
assert.equal(mixedArch.ok, false);
if (!mixedArch.ok) {
  assert.equal(mixedArch.reason, 'mixed_cpu_architecture');
}

const modalSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/node-manager/(pages)/cloudregion/node/collectorOperation/collectorModal.tsx'
  ),
  'utf8'
);
assert.match(
  modalSource,
  /buildCollectorPackageListParams/,
  'install/update must build package query params from the known node target'
);
assert.match(
  modalSource,
  /describeCollectorInstallTarget/,
  'opening the modal must derive os/arch from the selected nodes'
);
assert.doesNotMatch(
  modalSource,
  /os:\s*system/,
  'package list must not read os from the just-set system state'
);
assert.doesNotMatch(
  modalSource,
  /cpu_architecture:\s*cpuArchitecture/,
  'package list must not read architecture from the just-set state'
);
assert.doesNotMatch(
  modalSource,
  /sorted\[0\]/,
  'default version must not be the first row of an unfiltered package list'
);

console.log('collector-package-selection tests passed');
