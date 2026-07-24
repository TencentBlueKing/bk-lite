import type { UploadFile } from 'antd';

import type { Patch } from '@/app/patch-manager/types';

export interface WindowsPackageUploadState {
  visible: boolean;
  disabled: boolean;
  showRemoveIcon: boolean;
  fileList: UploadFile[];
}

/** Windows 手工补丁编辑时的文件展示与替换权限。 */
export function getWindowsPackageUploadState(patch: Patch | null): WindowsPackageUploadState {
  const visible = !!patch && patch.os_type === 'windows' && patch.sources.length === 0;
  if (!visible || !patch) {
    return { visible: false, disabled: true, showRemoveIcon: false, fileList: [] };
  }

  const canReplace = patch.pkg_status === 'download_failed';
  const fileList: UploadFile[] = patch.package_info ? [{
    uid: `windows-package-${patch.id}`,
    name: patch.package_info.file_name,
    status: canReplace ? 'error' : 'done',
    size: patch.package_info.file_size,
  }] : [];

  return {
    visible: true,
    disabled: !canReplace,
    showRemoveIcon: canReplace,
    fileList,
  };
}
