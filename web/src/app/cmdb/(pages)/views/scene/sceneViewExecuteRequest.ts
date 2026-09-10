import type { LatestRequestGuard } from '@/context/latestRequestGuard';

export function beginSceneViewExecute(guard: LatestRequestGuard): number {
  return guard.begin();
}

export function commitSceneViewExecuteSuccess(
  guard: LatestRequestGuard,
  requestId: number,
  apply: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, apply);
}

export function commitSceneViewExecuteSettled(
  guard: LatestRequestGuard,
  requestId: number,
  settle: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, settle);
}
