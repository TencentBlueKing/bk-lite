import type { MonitorObjectSnapshot } from '@/app/alarm/types/alarms';

export interface AlarmSnapshotObject {
  key: string;
  label: string;
  monitorId: string;
  instUuid: string;
}

const readStableId = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

export function listAlarmSnapshotObjects(
  objects: MonitorObjectSnapshot[] | null | undefined,
): AlarmSnapshotObject[] {
  return (objects || []).map((item, index) => {
    const resourceType = item.resource_type?.trim() || '--';
    const resourceName = item.resource_name?.trim() || '--';
    return {
      key: String(index),
      label: `${resourceType}：${resourceName}`,
      monitorId: readStableId(item.monitor_id),
      instUuid: readStableId(item.cmdb_id),
    };
  });
}

export function alarmHasAnyMonitorId(
  objects: MonitorObjectSnapshot[] | null | undefined,
): boolean {
  return listAlarmSnapshotObjects(objects).some((item) => Boolean(item.monitorId));
}

export function alarmHasAnyInstUuid(
  objects: MonitorObjectSnapshot[] | null | undefined,
): boolean {
  return listAlarmSnapshotObjects(objects).some((item) => Boolean(item.instUuid));
}
