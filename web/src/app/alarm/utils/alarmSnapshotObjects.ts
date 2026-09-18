import type { MonitorObjectSnapshot } from '@/app/alarm/types/alarms';

export interface AlarmSnapshotObject {
  key: string;
  label: string;
  monitorId: string;
  instUuid: string;
  nodeId: string;
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
      nodeId: readStableId(item.node_id),
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

export function alarmHasAnyNodeId(
  objects: MonitorObjectSnapshot[] | null | undefined,
): boolean {
  return listAlarmSnapshotObjects(objects).some((item) => Boolean(item.nodeId));
}

export function readAlarmLogAlertId(form: Record<string, unknown> | null | undefined): string {
  if (!form) return '';
  const direct = readStableId(form.log_alert_id);
  if (direct) return direct;
  const labels = form.labels;
  if (labels && typeof labels === 'object') {
    return readStableId((labels as Record<string, unknown>).log_alert_id);
  }
  return '';
}

export function readAlarmServiceId(form: Record<string, unknown> | null | undefined): string {
  if (!form) return '';
  if (readStableId(form.resource_type) !== 'apm_service') {
    return '';
  }
  return readStableId(form.resource_id);
}

export interface IncidentAssetOption {
  instUuid: string;
  label: string;
}

export function listIncidentAssetOptions(
  alerts: Array<{ monitor_objects?: MonitorObjectSnapshot[] }> | null | undefined,
): IncidentAssetOption[] {
  const labelByUuid = new Map<string, string>();
  const order: string[] = [];
  for (const alert of alerts || []) {
    for (const item of alert.monitor_objects || []) {
      const instUuid = readStableId(item.cmdb_id);
      if (!instUuid) continue;
      if (!labelByUuid.has(instUuid)) {
        order.push(instUuid);
        labelByUuid.set(instUuid, '');
      }
      if (labelByUuid.get(instUuid)) continue;
      const resourceName = readStableId(item.resource_name);
      if (!resourceName) continue;
      const resourceType = readStableId(item.resource_type);
      labelByUuid.set(
        instUuid,
        resourceType ? `${resourceType}：${resourceName}` : resourceName,
      );
    }
  }
  // 快照没冻结资产名时才回落 uuid，保证选项仍可区分。
  return order.map((instUuid) => ({
    instUuid,
    label: labelByUuid.get(instUuid) || instUuid,
  }));
}
