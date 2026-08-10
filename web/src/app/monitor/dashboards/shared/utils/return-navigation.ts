export const DASHBOARD_RETURN_OBJECT_ID_PARAM = 'return_object_id';
export const DASHBOARD_RETURN_OBJECT_NAME_PARAM = 'return_object_name';
export const DASHBOARD_RETURN_SOURCE_PARAM = 'return_source';

export type DashboardReturnSource = 'view' | 'integration';

type SearchParamsLike = Pick<URLSearchParams, 'get'>;

export interface DashboardReturnContext {
  objectId: string;
  objectName: string;
  source?: DashboardReturnSource;
}

/**
 * Keep dashboard return navigation semantic and deterministic: it restores the
 * monitor-object view that opened the dashboard instead of depending on the
 * browser history stack.
 */
export const getDashboardReturnContext = (params: SearchParamsLike): DashboardReturnContext => ({
  objectId: String(params.get(DASHBOARD_RETURN_OBJECT_ID_PARAM) || '').trim(),
  objectName: String(params.get(DASHBOARD_RETURN_OBJECT_NAME_PARAM) || '').trim(),
  source: params.get(DASHBOARD_RETURN_SOURCE_PARAM) === 'integration' ? 'integration' : 'view'
});

export const withDashboardReturnContext = (
  params: URLSearchParams,
  context: DashboardReturnContext
) => {
  const next = new URLSearchParams(params.toString());
  if (context.objectId) {
    next.set(DASHBOARD_RETURN_OBJECT_ID_PARAM, context.objectId);
    if (context.objectName) {
      next.set(DASHBOARD_RETURN_OBJECT_NAME_PARAM, context.objectName);
    } else {
      next.delete(DASHBOARD_RETURN_OBJECT_NAME_PARAM);
    }
    if (context.source === 'integration') {
      next.set(DASHBOARD_RETURN_SOURCE_PARAM, 'integration');
    } else {
      next.delete(DASHBOARD_RETURN_SOURCE_PARAM);
    }
  } else {
    next.delete(DASHBOARD_RETURN_OBJECT_ID_PARAM);
    next.delete(DASHBOARD_RETURN_OBJECT_NAME_PARAM);
    next.delete(DASHBOARD_RETURN_SOURCE_PARAM);
  }
  return next;
};

export const preserveDashboardReturnContext = (
  nextParams: URLSearchParams,
  currentParams: SearchParamsLike
) => withDashboardReturnContext(nextParams, getDashboardReturnContext(currentParams));

export const getMonitorViewObjectUrl = (objectId?: string | null) => {
  const normalizedObjectId = String(objectId || '').trim();
  return normalizedObjectId
    ? `/monitor/view?object_id=${encodeURIComponent(normalizedObjectId)}`
    : '/monitor/view';
};

export const getDashboardReturnUrl = (params: SearchParamsLike) => {
  const { objectId, source } = getDashboardReturnContext(params);
  if (source === 'integration' && objectId) {
    return `/monitor/integration/asset?objId=${encodeURIComponent(objectId)}`;
  }
  return getMonitorViewObjectUrl(objectId);
};

export const getDashboardReturnLabel = (params: SearchParamsLike) => {
  const { objectName, source } = getDashboardReturnContext(params);
  if (source === 'integration') {
    return objectName ? `返回${objectName}集成资产列表` : '返回集成资产列表';
  }
  return objectName ? `返回${objectName}视图列表` : '返回监控视图';
};

export const getDashboardBreadcrumbItems = (params: SearchParamsLike, title: string) => {
  const { objectId, objectName, source } = getDashboardReturnContext(params);
  if (source === 'integration') {
    return [
      { title: '集成', href: '/monitor/integration' },
      { title: '资产', href: '/monitor/integration/asset' },
      ...(objectName && objectId
        ? [{ title: objectName, href: getDashboardReturnUrl(params) }]
        : []),
      { title }
    ];
  }
  return [
    { title: '监控视图', href: '/monitor/view' },
    ...(objectName && objectId
      ? [{ title: objectName, href: getDashboardReturnUrl(params) }]
      : []),
    { title }
  ];
};

export const getDashboardReturnNavigation = (params: SearchParamsLike, title: string) => ({
  href: getDashboardReturnUrl(params),
  label: getDashboardReturnLabel(params),
  breadcrumbItems: getDashboardBreadcrumbItems(params, title)
});
