import { PORTAL_HOME_PATH } from '@/utils/route';

export interface HomepageLandingResolution {
  dashboard_id?: number | string | null;
  fallback?: string | null;
}

export interface EffectiveHomepageEntry {
  dashboardId?: number | null;
}

/** 顶栏 Logo：能打开的仪表盘进首页，否则回工作台。 */
export const effectiveHomepageHref = (entry: EffectiveHomepageEntry | null | undefined): string => {
  if (entry?.dashboardId) {
    return `${PORTAL_HOME_PATH}?dashboard_id=${encodeURIComponent(String(entry.dashboardId))}`;
  }
  return PORTAL_HOME_PATH;
};

/** 首次登录提交组织成功后：能进的仪表盘进首页，否则由调用方保持原刷新。 */
export const hrefAfterOrgInit = (
  resolution: HomepageLandingResolution | null | undefined,
): string | null => {
  const dashboardId = resolution?.dashboard_id;
  if (dashboardId !== undefined && dashboardId !== null && String(dashboardId).trim()) {
    return `${PORTAL_HOME_PATH}?dashboard_id=${encodeURIComponent(String(dashboardId))}`;
  }
  return null;
};

const FALLBACK_QUERY = 'homepage_fallback';

const normalizePathname = (pathname: string) => {
  if (pathname.length > 1 && pathname.endsWith('/')) {
    return pathname.replace(/\/+$/, '');
  }
  return pathname || '/';
};

const parseTarget = (targetUrl: string, origin?: string): URL | null => {
  try {
    if (/^[a-z][a-z0-9+.-]*:/i.test(targetUrl)) {
      const absolute = new URL(targetUrl);
      if (!origin) {
        return null;
      }
      if (absolute.origin !== new URL(origin).origin) {
        return null;
      }
      return absolute;
    }
    return new URL(targetUrl, origin || 'http://localhost');
  } catch {
    return null;
  }
};

const dashboardIdFrom = (url: URL) => {
  const value = url.searchParams.get('dashboard_id');
  return value && value.trim() ? value.trim() : '';
};

/** 裸工作台：默认首页路径，且没有有效的 dashboard_id。`/` 视为默认落地。 */
export const isBarePortalHomeTarget = (targetUrl: string, origin?: string): boolean => {
  const url = parseTarget(targetUrl, origin);
  if (!url) {
    return false;
  }
  const pathname = normalizePathname(url.pathname);
  if (pathname !== PORTAL_HOME_PATH && pathname !== '/') {
    return false;
  }
  return !dashboardIdFrom(url);
};

export const homepageLandingHref = (
  targetUrl: string,
  resolution: HomepageLandingResolution | null | undefined,
  origin?: string,
): string => {
  if (!isBarePortalHomeTarget(targetUrl, origin)) {
    return targetUrl;
  }
  const dashboardId = resolution?.dashboard_id;
  if (dashboardId !== undefined && dashboardId !== null && String(dashboardId).trim()) {
    return `${PORTAL_HOME_PATH}?dashboard_id=${encodeURIComponent(String(dashboardId))}`;
  }
  if (resolution?.fallback === 'missing' || resolution?.fallback === 'org') {
    return `${PORTAL_HOME_PATH}?${FALLBACK_QUERY}=${resolution.fallback}`;
  }
  return targetUrl;
};

export const isDashboardHomepagePath = (
  pathname: string | null | undefined,
  search: string | { get: (name: string) => string | null } | null | undefined,
): boolean => {
  if (normalizePathname(pathname || '') !== PORTAL_HOME_PATH) {
    return false;
  }
  const dashboardId = typeof search === 'string'
    ? new URLSearchParams(search.replace(/^\?/, '')).get('dashboard_id')
    : search?.get('dashboard_id');
  return Boolean(dashboardId && dashboardId.trim());
};

/** 是否在门户首页落地路径（含裸工作台与带 dashboard_id 的仪表盘首页）。 */
export const isPortalHomePath = (pathname: string | null | undefined): boolean => {
  const path = normalizePathname(pathname || '');
  return path === PORTAL_HOME_PATH || path === '/';
};

export interface PreferenceLandingState {
  personal_mode: 'follow' | 'workbench' | 'dashboard';
  personal_dashboard_id?: number | null;
  global_mode: 'workbench' | 'dashboard';
  global_dashboard_id?: number | null;
}

/** 根据已保存的偏好算出门户首页落地 URL。 */
export const preferenceLandingHref = (
  state: PreferenceLandingState | null | undefined,
): string => {
  if (!state) {
    return PORTAL_HOME_PATH;
  }
  if (state.personal_mode === 'workbench') {
    return PORTAL_HOME_PATH;
  }
  if (state.personal_mode === 'dashboard' && state.personal_dashboard_id) {
    return `${PORTAL_HOME_PATH}?dashboard_id=${encodeURIComponent(String(state.personal_dashboard_id))}`;
  }
  if (state.global_mode === 'dashboard' && state.global_dashboard_id) {
    return `${PORTAL_HOME_PATH}?dashboard_id=${encodeURIComponent(String(state.global_dashboard_id))}`;
  }
  return PORTAL_HOME_PATH;
};

const normalizeLocationKey = (pathname: string, search: string): string => {
  const path = normalizePathname(pathname || '');
  const params = new URLSearchParams(search.replace(/^\?/, ''));
  const dashboardId = params.get('dashboard_id')?.trim();
  if (dashboardId) {
    return `${path}?dashboard_id=${dashboardId}`;
  }
  return path;
};

/**
 * 当前已在门户首页时，若新偏好落地 URL 与当前不一致则返回目标；
 * 不在首页、或已在目标上则返回 null（不导航）。
 */
export const homepagePreferenceNavigationTarget = (
  pathname: string | null | undefined,
  search: string | null | undefined,
  state: PreferenceLandingState | null | undefined,
): string | null => {
  if (!isPortalHomePath(pathname)) {
    return null;
  }
  const target = preferenceLandingHref(state);
  const current = normalizeLocationKey(pathname || '', search || '');
  const next = normalizeLocationKey(
    target.split('?')[0] || PORTAL_HOME_PATH,
    target.includes('?') ? target.slice(target.indexOf('?')) : '',
  );
  return current === next ? null : target;
};

const readLandingPayload = (payload: unknown): HomepageLandingResolution | null => {
  if (!payload || typeof payload !== 'object') {
    return null;
  }
  const body = payload as { result?: boolean; data?: HomepageLandingResolution };
  if (body.result === false) {
    return null;
  }
  if (body.data && typeof body.data === 'object') {
    return body.data;
  }
  if ('dashboard_id' in body || 'fallback' in body) {
    return body as HomepageLandingResolution;
  }
  return null;
};

/** 仅当登录目标是裸工作台时查询首页配置。失败时保持原目标，避免登录中断。 */
export const resolvePostLoginHref = async (
  targetUrl: string,
  token: string | undefined,
  origin?: string,
): Promise<string> => {
  if (!token || !isBarePortalHomeTarget(targetUrl, origin)) {
    return targetUrl;
  }
  try {
    const response = await fetch('/api/proxy/operation_analysis/api/homepage/landing/', {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
      credentials: 'include',
    });
    if (!response.ok) {
      return targetUrl;
    }
    const resolution = readLandingPayload(await response.json());
    if (!resolution) {
      return targetUrl;
    }
    return homepageLandingHref(targetUrl, resolution, origin);
  } catch {
    return targetUrl;
  }
};
