import type { LatestRequestGuard } from '@/context/latestRequestGuard';

export function commitCollectToolSubmit(
  guard: LatestRequestGuard,
  requestId: number,
  apply: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, apply);
}

export function commitCollectToolPoll(
  guard: LatestRequestGuard,
  requestId: number,
  apply: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, apply);
}

export function commitCollectToolFailure(
  guard: LatestRequestGuard,
  requestId: number,
  apply: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, apply);
}
