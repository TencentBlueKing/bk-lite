import type { LatestRequestGuard } from '@/context/latestRequestGuard';

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
