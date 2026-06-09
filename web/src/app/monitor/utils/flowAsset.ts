import type { Key } from 'react';

export interface FlowExistingAssetItem {
  instance_id?: string;
  id?: string;
  instance_name?: string;
  name?: string;
  cloud_region_id?: number | string;
  ip?: string;
  organizations?: Key[];
  organization?: Key[];
  fallback_sampling_rate?: number | string | null;
}

export interface FlowAssetFormPatch {
  instance_id: string;
  name?: string;
  cloud_region_id?: number;
  ip?: string;
  organizations?: Key[];
  fallback_sampling_rate: number;
}

export const FLOW_FALLBACK_SAMPLING_RATE_DEFAULT = 1000;

export const normalizeFlowFallbackSamplingRate = (
  value: FlowExistingAssetItem['fallback_sampling_rate']
): number => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsedValue = Number(value);
    if (Number.isFinite(parsedValue)) {
      return parsedValue;
    }
  }
  return FLOW_FALLBACK_SAMPLING_RATE_DEFAULT;
};

export const normalizeFlowCloudRegionId = (
  value: FlowExistingAssetItem['cloud_region_id']
): number | undefined => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsedValue = Number(value);
    if (Number.isFinite(parsedValue)) {
      return parsedValue;
    }
  }
  return undefined;
};

export const buildExistingFlowAssetFormPatch = (
  value: string,
  selectedAsset?: FlowExistingAssetItem
): FlowAssetFormPatch => ({
  instance_id: value,
  name: selectedAsset?.instance_name || selectedAsset?.name,
  cloud_region_id: normalizeFlowCloudRegionId(selectedAsset?.cloud_region_id),
  ip: selectedAsset?.ip,
  organizations: selectedAsset?.organizations || selectedAsset?.organization,
  fallback_sampling_rate: normalizeFlowFallbackSamplingRate(
    selectedAsset?.fallback_sampling_rate
  )
});
