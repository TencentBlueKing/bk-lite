export const INSTANCE_LIFECYCLE_TRIGGER_TYPES = [
  'instance_added',
  'attribute_change',
  'instance_deleted',
] as const;

const lifecycleTriggerSet = new Set<string>(INSTANCE_LIFECYCLE_TRIGGER_TYPES);

export function isInstanceLifecycleTrigger(type: string): boolean {
  return lifecycleTriggerSet.has(type);
}

export function lifecycleNeedsWatchFields(triggerTypes: readonly string[]): boolean {
  return triggerTypes.some(isInstanceLifecycleTrigger);
}

export function isInstanceFilterReady(
  filterType: string | undefined,
  value: { query_list?: unknown; instance_uuids?: unknown } | null | undefined,
): boolean {
  if (filterType === 'condition') {
    if (value == null) {
      return true;
    }
    return Array.isArray(value.query_list);
  }
  return Array.isArray(value?.instance_uuids) && value.instance_uuids.length > 0;
}
