export const FLOW_SUPPORTED_OBJECT_NAMES = [
  'Switch',
  'Router',
  'Firewall',
  'Loadbalance',
] as const;

export type FlowSupportedObjectName = (typeof FLOW_SUPPORTED_OBJECT_NAMES)[number];

export const MONITOR_OBJECT_TO_INSTANCE_TYPE: Record<FlowSupportedObjectName, string> = {
  Switch: 'switch',
  Router: 'router',
  Firewall: 'firewall',
  Loadbalance: 'loadbalance',
};

export type FlowProtocol = 'netflow' | 'sflow';

export const CONVERSATION_TOP_N = 10;
export const PROTOCOL_TOP_N = 10;

export const resolveInstanceTypeFromObjectName = (objectName?: string | null): string | null => {
  const normalized = String(objectName || '').trim();
  if (!normalized) return null;
  return MONITOR_OBJECT_TO_INSTANCE_TYPE[normalized as FlowSupportedObjectName] || null;
};

export const isFlowSupportedObjectName = (objectName?: string | null): boolean =>
  FLOW_SUPPORTED_OBJECT_NAMES.includes(String(objectName || '').trim() as FlowSupportedObjectName);

/** NetFlow/sFlow 盘绑定 Switch/Router 等网络设备，而非名为 NetFlow/sFlow 的监控对象。 */
export function resolveFlowHostMonitorObject<
  T extends { id?: unknown; name?: string; display_name?: string; instance_count?: number },
>(objects: T[], preferredId?: string | null): T | undefined {
  const byId = preferredId
    ? objects.find((obj) => String(obj.id) === String(preferredId))
    : undefined;
  if (byId && isFlowSupportedObjectName(byId.name)) {
    return byId;
  }

  const withInstances = objects.find(
    (obj) =>
      isFlowSupportedObjectName(obj.name) &&
      (obj.instance_count == null || obj.instance_count > 0),
  );
  if (withInstances) return withInstances;

  return objects.find((obj) => isFlowSupportedObjectName(obj.name));
}
