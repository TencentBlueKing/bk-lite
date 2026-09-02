const DEFAULT_CLIENT_ID = 'ops-console';

/** Portal landing after sign-in and for the `/` route. */
export const PORTAL_HOME_PATH = '/ops-console/home';

const clientIdFromPathname = (pathname: string): string => {
  const pathSegments = pathname.split('/').filter(Boolean);

  if (pathSegments.length > 0 && pathSegments[0] === 'auth') {
    return DEFAULT_CLIENT_ID;
  }

  if (pathSegments.length > 0) {
    return pathSegments[0];
  }

  return DEFAULT_CLIENT_ID;
};

export const getClientIdFromRoute = (pathname?: string | null): string => {
  const resolved = pathname === undefined
    ? (typeof window === 'undefined' ? '' : window.location.pathname)
    : pathname || '';

  if (!resolved) {
    return DEFAULT_CLIENT_ID;
  }

  return clientIdFromPathname(resolved);
};

export const isAppClientMenuRoute = (pathname: string | null | undefined): boolean => {
  if (!pathname || pathname === '/') {
    return false;
  }
  return !(
    pathname.startsWith('/auth/')
    || pathname === '/no-permission'
    || pathname === '/no-found'
  );
};

export const isWaitingForClientMenus = (
  pathname: string | null | undefined,
  menuClientId: string | null,
): boolean => {
  if (!isAppClientMenuRoute(pathname)) {
    return false;
  }
  return menuClientId !== getClientIdFromRoute(pathname);
};

export const mapClientName = (routeClientId: string): string => {
  const clientNameMap: { [key: string]: string } = {
    'node-manager': 'node',
    'patch-manager': 'patch',
  };

  return clientNameMap[routeClientId] || routeClientId;
};
