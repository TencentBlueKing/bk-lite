import type { MonitorObjectSnapshot } from '@/app/alarm/types/alarms';

export interface RelatedTopologyCenter {
  instUuid: string;
  label: string;
}

export function listRelatedTopologyCenters(
  objects: MonitorObjectSnapshot[] | null | undefined,
): RelatedTopologyCenter[] {
  const centers: RelatedTopologyCenter[] = [];
  const seen = new Set<string>();
  for (const item of objects || []) {
    const instUuid = typeof item.cmdb_id === 'string' ? item.cmdb_id.trim() : '';
    if (!instUuid || seen.has(instUuid)) {
      continue;
    }
    seen.add(instUuid);
    const resourceType = item.resource_type?.trim() || '--';
    const resourceName = item.resource_name?.trim() || '--';
    centers.push({
      instUuid,
      label: `${resourceType}：${resourceName}`,
    });
  }
  return centers;
}

export function resolveRelatedTopologyTabVisibility(input: {
  declared: boolean;
  centerCount: number;
}): boolean {
  return input.declared && input.centerCount > 0;
}
