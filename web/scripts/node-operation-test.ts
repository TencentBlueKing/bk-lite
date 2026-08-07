import assert from 'node:assert/strict';
import {
  buildControllerUninstallRequestNode,
  buildControllerUninstallRow,
  isControllerOperationDisabled
} from '../src/app/node-manager/utils/nodeOperation.ts';

const linuxAutoNode = {
  key: 'linux-auto',
  operating_system: 'linux',
  install_method: 'auto'
};

const linuxManualNode = {
  key: 'linux-manual',
  operating_system: 'linux',
  install_method: 'manual'
};

const windowsManualNode = {
  key: 'windows-manual',
  operating_system: 'windows',
  install_method: 'manual'
};

assert.equal(
  isControllerOperationDisabled([linuxManualNode]),
  false,
  'manual installed Linux nodes should support controller uninstall'
);

assert.equal(
  isControllerOperationDisabled([linuxAutoNode, linuxManualNode]),
  false,
  'controller operation should not be disabled by mixed install methods'
);

assert.equal(
  isControllerOperationDisabled([windowsManualNode]),
  false,
  'Windows nodes should support controller uninstall'
);

assert.equal(
  isControllerOperationDisabled([linuxManualNode, windowsManualNode]),
  true,
  'controller operation should require a single operating system'
);

assert.equal(
  isControllerOperationDisabled([]),
  true,
  'controller operation should be disabled when no node is selected'
);

const windowsUninstallRow = buildControllerUninstallRow(windowsManualNode);
assert.equal(windowsUninstallRow.node_id, 'windows-manual');
assert.equal(windowsUninstallRow.port, 5986);
assert.equal(windowsUninstallRow.username, 'Administrator');

const windowsUninstallRequest = buildControllerUninstallRequestNode({
  ...windowsUninstallRow,
  password: 'credential'
});
assert.equal(windowsUninstallRequest.node_id, 'windows-manual');
assert.equal(windowsUninstallRequest.port, 5986);
assert.equal(windowsUninstallRequest.winrm_scheme, 'https');
assert.equal(windowsUninstallRequest.winrm_transport, 'ntlm');
assert.equal(windowsUninstallRequest.winrm_cert_validation, true);

console.log('node-operation tests passed');
