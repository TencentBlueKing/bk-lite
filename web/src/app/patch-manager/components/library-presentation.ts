import type {
  PackageStatus,
  PatchSourceType,
} from '@/app/patch-manager/types';

import type { ReadyStatus } from './ready-tag';

export const PACKAGE_STATUS_FILTER_VALUES: PackageStatus[] = [
  'ready',
  'downloading',
  'download_failed',
  'pending',
];

export const LINUX_SOURCE_TYPE_FILTER_VALUES: PatchSourceType[] = [
  'apt_repo',
  'dnf_repo',
  'yum_repo',
];

const PACKAGE_STATUS_PRESENTATION: Record<PackageStatus, ReadyStatus> = {
  ready: 'ready',
  downloading: 'processing',
  download_failed: 'action_required',
  pending: 'processing',
};

export function presentPackageStatus(status?: PackageStatus): ReadyStatus {
  return status ? PACKAGE_STATUS_PRESENTATION[status] : 'unavailable';
}
