import assert from 'node:assert/strict';
import { isControllerOperationDisabled } from '../src/app/node-manager/utils/nodeOperation.ts';

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
  isControllerOperationDisabled([linuxManualNode, windowsManualNode]),
  true,
  'controller operation should still require a single non-Windows operating system'
);

assert.equal(
  isControllerOperationDisabled([]),
  true,
  'controller operation should be disabled when no node is selected'
);

console.log('node-operation tests passed');
