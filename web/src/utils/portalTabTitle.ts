import { mapClientName } from '@/utils/route';

export const PORTAL_BRANDING_CACHE_KEY = 'bk-portal-branding';
export const PORTAL_CLIENT_NAMES_CACHE_KEY = 'bk-portal-client-names';

export type PortalClientNameMap = Record<string, string>;

export const readJsonCache = <T,>(key: string): T | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
};

export const writeJsonCache = (key: string, value: unknown) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore quota / private mode failures.
  }
};

export const buildClientNameMap = (
  apps: Array<{ name?: string; display_name?: string }>
): PortalClientNameMap => {
  const nextMap: PortalClientNameMap = {};
  for (const app of apps) {
    const name = app.name?.trim();
    const displayName = app.display_name?.trim();
    if (name && displayName) {
      nextMap[name] = displayName;
    }
  }
  return nextMap;
};

export const resolveRouteClientId = (pathname?: string | null): string => {
  const routeSegment = pathname?.split('/').filter(Boolean)[0];
  if (!routeSegment || routeSegment === 'auth') {
    return '';
  }
  return mapClientName(routeSegment);
};

export const buildPortalTabTitle = ({
  portalName,
  moduleName,
  slogan,
}: {
  portalName: string;
  moduleName?: string;
  slogan: string;
}) => {
  if (moduleName) {
    return `${moduleName} - ${portalName}`;
  }
  return `${portalName} - ${slogan}`;
};

export const resolvePortalTabTitle = ({
  pathname,
  portalName,
  brandingReady,
  apps,
  clientsLoading,
  slogan,
  fallbackPortalName,
}: {
  pathname?: string | null;
  portalName: string;
  brandingReady: boolean;
  apps: Array<{ name?: string; display_name?: string }>;
  clientsLoading: boolean;
  slogan: string;
  fallbackPortalName: string;
}): string | null => {
  const routeClientId = resolveRouteClientId(pathname);
  const cachedNames = readJsonCache<PortalClientNameMap>(PORTAL_CLIENT_NAMES_CACHE_KEY) || {};
  const cachedBranding = readJsonCache<{ portalName?: string }>(PORTAL_BRANDING_CACHE_KEY);
  const moduleName =
    apps.find((app) => app.name === routeClientId)?.display_name?.trim()
    || cachedNames[routeClientId];
  const resolvedPortalName =
    (brandingReady ? portalName : undefined)
    || cachedBranding?.portalName
    || portalName
    || fallbackPortalName;

  if (moduleName && resolvedPortalName) {
    return buildPortalTabTitle({
      portalName: resolvedPortalName,
      moduleName,
      slogan,
    });
  }

  // Keep bootstrap/current title while module list is still loading.
  if (routeClientId && !moduleName && clientsLoading) {
    return null;
  }

  if (!brandingReady && !cachedBranding?.portalName) {
    return null;
  }

  return buildPortalTabTitle({
    portalName: resolvedPortalName,
    moduleName,
    slogan,
  });
};

/** Runs before React hydration to avoid tab title flicker on revisit. */
export const PORTAL_TAB_TITLE_BOOTSTRAP_SCRIPT = `
(function () {
  try {
    var branding = JSON.parse(sessionStorage.getItem('${PORTAL_BRANDING_CACHE_KEY}') || 'null');
    var names = JSON.parse(sessionStorage.getItem('${PORTAL_CLIENT_NAMES_CACHE_KEY}') || '{}');
    var segment = location.pathname.split('/').filter(Boolean)[0];
    if (!segment || segment === 'auth') return;
    var map = { 'node-manager': 'node', 'patch-manager': 'patch' };
    var clientId = map[segment] || segment;
    var moduleName = names[clientId];
    var portalName = branding && branding.portalName;
    if (moduleName && portalName) {
      document.title = moduleName + ' - ' + portalName;
    }
  } catch (e) {}
})();
`;
