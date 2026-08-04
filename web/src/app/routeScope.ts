const DASHBOARD_EXECUTION_RENDER_ROUTE =
  /^\/ops-analysis\/render\/execution\/\d+\/?$/;

export const isDashboardExecutionRenderRoute = (
  pathname: string | null,
) => Boolean(pathname && DASHBOARD_EXECUTION_RENDER_ROUTE.test(pathname));
