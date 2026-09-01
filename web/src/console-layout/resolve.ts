import { isMenuPathMatch, findMatchedMenuPath } from '@/utils/menuHelpers';
import { getClientIdFromRoute, mapClientName } from '@/utils/route';
import type { MenuItem } from '@/types/index';
import {
  APP_TOP_NAV_CHIP_WIDTH_PX,
  APP_TOP_NAV_MORE_WIDTH_PX,
  DEFAULT_CONSOLE_CHROME_LAYOUT,
  type ConsoleChromeLayout,
} from './contract';

export const isConsoleChromeException = (pathname: string | null | undefined): boolean => {
  if (!pathname) {
    return false;
  }
  return (
    pathname.startsWith('/auth/signin')
    || pathname.startsWith('/auth/signout')
    || pathname === '/no-permission'
    || pathname === '/no-found'
    || pathname.startsWith('/opspilot/studio/chat')
    || pathname.startsWith('/ops-analysis/share/')
    || pathname.startsWith('/ops-analysis/render/execution/')
    || pathname.startsWith('/monitor/view/dashboard/')
    || pathname.startsWith('/ops-console')
  );
};

export const resolveEffectiveChromeLayout = (
  stored: ConsoleChromeLayout,
  pathname: string | null | undefined,
): ConsoleChromeLayout => {
  if (isConsoleChromeException(pathname)) {
    return DEFAULT_CONSOLE_CHROME_LAYOUT;
  }
  return stored;
};

export const isDetailChromeContext = (
  pathname: string | null | undefined,
  menus: MenuItem[],
): boolean => {
  if (!pathname) {
    return false;
  }
  const matchedPath = findMatchedMenuPath(menus, pathname);
  if (!matchedPath?.length) {
    return false;
  }
  return Boolean(matchedPath[0].hasDetail && matchedPath.length > 1);
};

export const shouldShowAppTopSideNav = (
  stored: ConsoleChromeLayout,
  pathname: string | null | undefined,
  menus: MenuItem[],
): boolean => {
  if (resolveEffectiveChromeLayout(stored, pathname) !== 'app-top') {
    return false;
  }
  return getVisibleFirstLayerMenus(menus).length > 0;
};

export const shouldShowClassicSegmentedNav = (
  stored: ConsoleChromeLayout,
  pathname: string | null | undefined,
  menus: MenuItem[],
  shouldRenderSecondLayer: boolean,
): boolean => (
  resolveEffectiveChromeLayout(stored, pathname) === 'classic' && shouldRenderSecondLayer
);

export const getVisibleFirstLayerMenus = (menus: MenuItem[]): MenuItem[] => (
  menus.filter((item) => item.url && !item.isNotMenuItem)
);

export interface AppTopSideNavGroup {
  item: MenuItem;
  children: MenuItem[];
}

export const buildAppTopSideNavGroups = (
  menus: MenuItem[],
  _pathname?: string | null,
): AppTopSideNavGroup[] => {
  return getVisibleFirstLayerMenus(menus).map((item) => ({
    item,
    children: [],
  }));
};

export const shouldOpenAppInNewTab = (
  app: { url: string; is_build_in?: boolean },
  currentOrigin: string,
): boolean => {
  if (app.is_build_in === false) {
    return true;
  }
  try {
    return new URL(app.url, currentOrigin).origin !== currentOrigin;
  } catch {
    return true;
  }
};

export type AppNavTarget =
  | { mode: 'same-tab'; href: string }
  | { mode: 'new-tab'; href: string };

export const resolveAppNavigation = (
  app: { url: string; is_build_in?: boolean },
  currentOrigin: string,
): AppNavTarget => {
  if (shouldOpenAppInNewTab(app, currentOrigin)) {
    return { mode: 'new-tab', href: app.url };
  }
  try {
    const url = new URL(app.url, currentOrigin);
    return {
      mode: 'same-tab',
      href: `${url.pathname}${url.search}${url.hash}` || '/',
    };
  } catch {
    return { mode: 'new-tab', href: app.url };
  }
};

const appRoutePrefix = (appUrl: string, currentOrigin: string): string | null => {
  try {
    const url = new URL(appUrl, currentOrigin || 'http://local.invalid');
    const first = url.pathname.split('/').filter(Boolean)[0];
    return first ? `/${first}` : null;
  } catch {
    return null;
  }
};

export const isAppNavActive = (
  app: { url: string; name?: string },
  pathname: string,
  currentOrigin: string,
): boolean => {
  const routeClientId = mapClientName(getClientIdFromRoute(pathname));
  if (app.name && mapClientName(app.name) === routeClientId) {
    return true;
  }
  const prefix = appRoutePrefix(app.url, currentOrigin);
  return Boolean(prefix && isMenuPathMatch(prefix, pathname));
};

export const findActiveApp = <T extends { url: string; name?: string }>(
  apps: T[],
  pathname: string,
  currentOrigin: string,
): T | undefined => {
  return apps
    .filter((app) => isAppNavActive(app, pathname, currentOrigin))
    .sort((a, b) => {
      const prefixA = appRoutePrefix(a.url, currentOrigin)?.length ?? 0;
      const prefixB = appRoutePrefix(b.url, currentOrigin)?.length ?? 0;
      if (prefixA !== prefixB) {
        return prefixB - prefixA;
      }
      if (a.name && b.name) {
        return b.name.length - a.name.length;
      }
      return 0;
    })[0];
};

export const splitOverflowApps = <T extends { url: string }>(
  apps: T[],
  visibleCount: number,
  activeUrl?: string | null,
): { visible: T[]; overflow: T[] } => {
  if (visibleCount <= 0 || apps.length <= visibleCount) {
    return { visible: [...apps], overflow: [] };
  }

  const visible = apps.slice(0, visibleCount);
  const overflow = apps.slice(visibleCount);
  if (!activeUrl) {
    return { visible, overflow };
  }

  const activeInOverflowIndex = overflow.findIndex((app) => app.url === activeUrl);
  if (activeInOverflowIndex < 0) {
    return { visible, overflow };
  }

  const [activeApp] = overflow.splice(activeInOverflowIndex, 1);
  const displaced = visible.pop();
  visible.push(activeApp);
  if (displaced) {
    overflow.unshift(displaced);
  }
  return { visible, overflow };
};

export const countVisibleAppSlots = (containerWidth: number, appCount: number): number => {
  if (containerWidth <= 0 || appCount <= 0) {
    return 0;
  }
  if (appCount * APP_TOP_NAV_CHIP_WIDTH_PX <= containerWidth) {
    return appCount;
  }
  return Math.max(
    1,
    Math.floor((containerWidth - APP_TOP_NAV_MORE_WIDTH_PX) / APP_TOP_NAV_CHIP_WIDTH_PX),
  );
};
