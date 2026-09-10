import type { LatestRequestGuard } from '@/context/latestRequestGuard';

export function beginTraceSearchRequest(
  guard: LatestRequestGuard,
  currentRequestId: number,
  cursor?: string,
): number {
  if (cursor) {
    return currentRequestId;
  }
  return guard.begin();
}

export function commitTraceSearchSuccess(
  guard: LatestRequestGuard,
  requestId: number,
  apply: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, apply);
}

export function commitTraceSearchFailure(
  guard: LatestRequestGuard,
  requestId: number,
  reportError: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, reportError);
}

export function commitTraceSearchSettled(
  guard: LatestRequestGuard,
  requestId: number,
  settle: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, settle);
}
