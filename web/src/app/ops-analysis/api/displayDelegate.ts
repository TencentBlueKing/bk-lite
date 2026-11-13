const DISPLAY_PREFIX = '/ops-analysis/display/';

export function delegatedSceneBase(
  pathname: string | null | undefined,
  shareSessionId: string | undefined,
  scene: string,
  authenticatedPath: string,
) {
  if (pathname?.startsWith(DISPLAY_PREFIX)) {
    return `/operation_analysis/api/screen_display/current/${scene}`;
  }
  if (shareSessionId) {
    return `/operation_analysis/api/dashboard_share/session/${shareSessionId}/${scene}`;
  }
  return authenticatedPath;
}

const AUTHENTICATED_NETWORK_STATUS_TOPOLOGY_PATH =
  '/operation_analysis/api/scene_widgets/network_status_topology/';

export function networkStatusTopologyApiPath(pathname?: string | null) {
  const base = delegatedSceneBase(
    pathname,
    undefined,
    'network_status_topology',
    AUTHENTICATED_NETWORK_STATUS_TOPOLOGY_PATH,
  );
  return base.endsWith('/') ? base : `${base}/`;
}
