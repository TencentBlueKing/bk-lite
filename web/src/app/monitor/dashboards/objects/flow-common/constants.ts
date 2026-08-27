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

export const resolveInstanceTypeFromObjectName = (objectName?: string | null): string | null => {
  const normalized = String(objectName || '').trim();
  if (!normalized) return null;
  return MONITOR_OBJECT_TO_INSTANCE_TYPE[normalized as FlowSupportedObjectName] || null;
};

export const isFlowSupportedObjectName = (objectName?: string | null): boolean =>
  FLOW_SUPPORTED_OBJECT_NAMES.includes(String(objectName || '').trim() as FlowSupportedObjectName);
