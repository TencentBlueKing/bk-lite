export const AGGREGATE_OTHER_ROUTE = '其他';

export function rumRouteLabel(
  route: string | null | undefined,
  translate: (key: string, fallback?: string) => string,
): string {
  if (!route) return '—';
  if (route === AGGREGATE_OTHER_ROUTE) return translate('rum.views.otherRoute', '其他（超出路由上限）');
  return route;
}
