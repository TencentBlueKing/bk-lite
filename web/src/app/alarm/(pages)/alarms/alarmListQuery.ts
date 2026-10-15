import type { SearchFilterCondition } from '@/app/alarm/types/alarms';

export function withAlarmSearchCondition<T extends Record<string, unknown>>(
  params: T,
  condition: SearchFilterCondition | null | undefined,
): T {
  if (!condition?.field) return params;
  if (condition.field === 'status') {
    if (condition.value) return { ...params, status: condition.value };
    return params;
  }
  return { ...params, [condition.field]: condition.value };
}
