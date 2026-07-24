import assert from 'node:assert/strict';

import { getWindowsPackageUploadState } from '../src/app/patch-manager/components/windows-package-upload-state';
import type { Patch } from '../src/app/patch-manager/types';

const basePatch: Patch = {
  id: 1,
  title: 'Windows 手工补丁',
  os_type: 'windows',
  patch_type: 'security',
  severity: 'important',
  cve_list: [],
  pkg_status: 'ready',
  applicable_scope: {},
  windows_detail: {
    kb_number: 'KB5072653',
    product_list: ['Windows 10 22H2'],
    architectures: ['x64'],
    ms_bulletin: '',
  },
  sources: [],
  source_type: null,
  released_at: null,
  last_synced_at: null,
  team: [1],
  created_at: '2026-07-24T00:00:00Z',
  updated_at: '2026-07-24T00:00:00Z',
  package_info: {
    file_name: 'windows10.0-kb5072653-x64.msu',
    file_size: 404829,
    sha256: '33f564e9',
    extension: '.msu',
  },
};

const ready = getWindowsPackageUploadState(basePatch);
assert.equal(ready.visible, true);
assert.equal(ready.disabled, true);
assert.equal(ready.showRemoveIcon, false);
assert.equal(ready.fileList[0]?.name, 'windows10.0-kb5072653-x64.msu');
assert.equal(ready.fileList[0]?.status, 'done');

const failed = getWindowsPackageUploadState({ ...basePatch, pkg_status: 'download_failed' });
assert.equal(failed.visible, true);
assert.equal(failed.disabled, false);
assert.equal(failed.showRemoveIcon, true);
assert.equal(failed.fileList[0]?.status, 'error');

const processing = getWindowsPackageUploadState({ ...basePatch, pkg_status: 'downloading' });
assert.equal(processing.disabled, true);
assert.equal(processing.showRemoveIcon, false);

const wsus = getWindowsPackageUploadState({ ...basePatch, sources: [8], source_type: 'wsus' });
assert.equal(wsus.visible, false);
assert.deepEqual(wsus.fileList, []);

console.log('Windows 手工补丁编辑文件状态约束通过');
