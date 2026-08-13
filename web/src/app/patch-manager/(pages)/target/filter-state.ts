import type { Key } from 'react';

import type { OSType } from '@/app/patch-manager/types';

export interface TargetFilterQuery {
  baselineId?: number;
  complianceStatus?: string;
}

export type SelectedTargetOsType = OSType | 'mixed' | 'incomplete' | undefined;

interface TargetOsRecord {
  key: string;
  osType: OSType;
}

export function resolveSelectedTargetOsType(
  selectedKeys: readonly Key[],
  rows: readonly TargetOsRecord[],
): SelectedTargetOsType {
  if (selectedKeys.length === 0) return undefined;
  const osTypes = new Set<OSType>();
  for (const key of selectedKeys) {
    const row = rows.find((item) => item.key === String(key));
    if (!row) return 'incomplete';
    osTypes.add(row.osType);
  }
  return osTypes.size === 1 ? [...osTypes][0] : 'mixed';
}

export function parseBaselineFilter(searchParams: URLSearchParams): number | undefined {
  const value = Number(searchParams.get('baseline_id'));
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

export function buildTargetFilterSearch(
  current: URLSearchParams,
  filters: TargetFilterQuery,
): URLSearchParams {
  const next = new URLSearchParams(current.toString());
  if (filters.baselineId) next.set('baseline_id', String(filters.baselineId));
  else next.delete('baseline_id');
  if (filters.complianceStatus) next.set('compliance_status', filters.complianceStatus);
  else next.delete('compliance_status');
  return next;
}
