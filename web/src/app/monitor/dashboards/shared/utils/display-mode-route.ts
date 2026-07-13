export type DashboardDisplayMode = 'dashboard' | 'metrics';

const DISPLAY_MODE_PARAM = 'view';

export const getDashboardDisplayModeFromParams = (
  params: URLSearchParams
): DashboardDisplayMode => (
  params.get(DISPLAY_MODE_PARAM) === 'metrics' ? 'metrics' : 'dashboard'
);

export const setDashboardDisplayModeInParams = (
  params: URLSearchParams,
  mode: DashboardDisplayMode
) => {
  const next = new URLSearchParams(params.toString());
  if (mode === 'metrics') {
    next.set(DISPLAY_MODE_PARAM, 'metrics');
  } else {
    next.delete(DISPLAY_MODE_PARAM);
  }
  return next;
};

export const preserveDashboardDisplayMode = (
  nextParams: URLSearchParams,
  currentParams: URLSearchParams
) => setDashboardDisplayModeInParams(
  nextParams,
  getDashboardDisplayModeFromParams(currentParams)
);
