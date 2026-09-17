import type { SearchFilterCondition } from '@/app/alarm/types/alarms';
import { normalizeRuleTags } from '@/app/alarm/utils/multivalueRules';
import type { LatestRequestGuard } from '@/context/latestRequestGuard';

export function buildMonitorSourceFilter(id: string): SearchFilterCondition {
  return { field: 'push_source_id', type: 'push_source', value: [id] };
}

export function selectedMonitorSourceIds(
  condition: SearchFilterCondition | { field: string; type?: string; value?: unknown } | null | undefined,
): string[] {
  if (!condition || (condition.field !== 'push_source_id' && condition.type !== 'push_source')) return [];
  const raw = condition.value;
  if (Array.isArray(raw)) return raw.filter((item): item is string => typeof item === 'string');
  return typeof raw === 'string' && raw ? [raw] : [];
}

export function buildIntegrationEventSearchParams(
  condition: SearchFilterCondition | { field: string; type?: string; value?: unknown } | null | undefined,
): Record<string, string> {
  if (!condition?.field) return {};
  if (condition.field === 'push_source_id' || condition.type === 'push_source') {
    const raw = condition.value;
    const ids = Array.isArray(raw)
      ? raw.filter((item): item is string => typeof item === 'string')
      : typeof raw === 'string'
        ? [raw]
        : [];
    const tags = normalizeRuleTags(ids).slice(0, 50);
    if (!tags.length) return {};
    return { push_source_ids: JSON.stringify(tags) };
  }
  if (typeof condition.value === 'string' && condition.value) {
    return { [condition.field]: condition.value };
  }
  return {};
}

export function commitIntegrationEventListSuccess(
  guard: LatestRequestGuard,
  requestId: number,
  apply: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, apply);
}

export function commitIntegrationEventListSettled(
  guard: LatestRequestGuard,
  requestId: number,
  settle: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, settle);
}
