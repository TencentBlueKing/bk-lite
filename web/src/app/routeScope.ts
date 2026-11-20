const DASHBOARD_EXECUTION_RENDER_ROUTE =
  /^\/ops-analysis\/render\/execution\/\d+\/?$/;

export const isDashboardExecutionRenderRoute = (
  pathname: string | null,
) => Boolean(pathname && DASHBOARD_EXECUTION_RENDER_ROUTE.test(pathname));

export const isScreenDisplayPath = (pathname: string | null | undefined) =>
  Boolean(pathname && pathname.startsWith('/ops-analysis/display/'));

/** 分享入口页自己先换一次性 state，再进入登录。继续页和会话页仍走平台登录。 */
export const isDashboardShareEntryPath = (pathname: string | null | undefined) =>
  Boolean(
    pathname
    && /^\/ops-analysis\/share\/(?!continue\/?$)(?!session(?:\/|$))[^/]+\/?$/.test(pathname),
  );

export const isScreenDisplayRequest = (url?: string | null) =>
  Boolean(url && url.includes('/operation_analysis/api/screen_display/'));
