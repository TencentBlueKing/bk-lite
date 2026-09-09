export interface AlertRefreshFilters {
  level: string[];
  state: string[];
}

export interface AlertRefreshQueryState {
  activeTab: string;
  filters: AlertRefreshFilters;
  myAlert: boolean;
}

export interface AlertRefreshExtra {
  tab?: string;
  filtersConfig?: AlertRefreshFilters;
  myAlert?: boolean;
}

export interface AlertRefreshQuerySnapshot {
  current: AlertRefreshQueryState;
}

const cloneFilters = (filters: AlertRefreshFilters): AlertRefreshFilters => ({
  level: [...filters.level],
  state: [...filters.state]
});

const cloneQueryState = (
  state: AlertRefreshQueryState
): AlertRefreshQueryState => ({
  activeTab: state.activeTab,
  filters: cloneFilters(state.filters),
  myAlert: state.myAlert
});

export const createAlertRefreshQuerySnapshot = (
  initial: AlertRefreshQueryState
): AlertRefreshQuerySnapshot => ({
  current: cloneQueryState(initial)
});

export const updateAlertRefreshQuerySnapshot = (
  snapshot: AlertRefreshQuerySnapshot,
  next: AlertRefreshQueryState
): void => {
  snapshot.current = cloneQueryState(next);
};

export const resolveAlertRefreshQuery = (
  snapshot: AlertRefreshQuerySnapshot,
  extra?: AlertRefreshExtra
): AlertRefreshQueryState => ({
  activeTab: extra?.tab ?? snapshot.current.activeTab,
  filters: extra?.filtersConfig
    ? cloneFilters(extra.filtersConfig)
    : snapshot.current.filters,
  myAlert: extra?.myAlert ?? snapshot.current.myAlert
});
