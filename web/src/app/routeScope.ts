const DASHBOARD_EXECUTION_RENDER_ROUTE =
  /^\/ops-analysis\/render\/execution\/\d+\/?$/;

export const isDashboardExecutionRenderRoute = (
  pathname: string | null,
) => Boolean(pathname && DASHBOARD_EXECUTION_RENDER_ROUTE.test(pathname));

export const isScreenDisplayPath = (pathname: string | null | undefined) =>
  Boolean(pathname && pathname.startsWith('/ops-analysis/display/'));

export const isScreenDisplayRequest = (url?: string | null) =>
  Boolean(url && url.includes('/operation_analysis/api/screen_display/'));
