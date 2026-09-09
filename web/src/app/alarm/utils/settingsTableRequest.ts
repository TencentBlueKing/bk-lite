import type { LatestRequestGuard } from '@/context/latestRequestGuard';

export interface SettingsTableListPayload<T> {
  items?: T[] | null;
  count?: number | null;
}

export interface SettingsTableListView<T> {
  dataList: T[];
  listCount: number;
  paginationTotal: number;
}

export function buildSettingsTableListView<T>(
  payload: SettingsTableListPayload<T>,
): SettingsTableListView<T> {
  const dataList = payload.items || [];
  return {
    dataList,
    listCount: dataList.length,
    paginationTotal: payload.count || 0,
  };
}

export function commitSettingsTableListSuccess<T>(
  guard: LatestRequestGuard,
  requestId: number,
  payload: SettingsTableListPayload<T>,
  apply: (next: SettingsTableListView<T>) => void,
): boolean {
  return guard.commitIfCurrent(requestId, () => {
    apply(buildSettingsTableListView(payload));
  });
}

export function commitSettingsTableListFailure(
  guard: LatestRequestGuard,
  requestId: number,
  reportError: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, reportError);
}

export function commitSettingsTableListSettled(
  guard: LatestRequestGuard,
  requestId: number,
  settle: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, settle);
}
