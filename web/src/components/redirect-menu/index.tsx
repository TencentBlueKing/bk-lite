'use client';
import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { useScreenAwareRouter } from '@/console-layout';
import { useOptionalClientData } from '@/context/client';
import { usePermissions } from '@/context/permissions';
import type { MenuItem } from '@/types/index';
import { getClientIdFromRoute, mapClientName, PORTAL_HOME_PATH } from '@/utils/route';

const menuBelongsToClient = (menuUrl: string, clientId: string) => {
  const normalized = menuUrl.replace(/\/+$/, '') || '/';
  const root = `/${clientId}`;
  return normalized === root || normalized.startsWith(`${root}/`);
};

const menuPathname = (url: string) => {
  const pathname = url.split(/[?#]/, 1)[0] || '/';
  return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
};

const findMenuUrl = (items: MenuItem[], path: string): string | null => {
  for (const item of items) {
    if (item.url && menuPathname(item.url) === path) {
      return item.url;
    }
    if (item.children?.length) {
      const nested = findMenuUrl(item.children, path);
      if (nested) {
        return nested;
      }
    }
  }
  return null;
};

export default function RedirectToFirstMenu() {
  const router = useScreenAwareRouter();
  const pathname = usePathname();
  const { menus } = usePermissions();
  const clientState = useOptionalClientData();
  const requestedRef = useRef<string | null>(null);

  useEffect(() => {
    if (pathname === '/') {
      if (requestedRef.current !== PORTAL_HOME_PATH) {
        requestedRef.current = PORTAL_HOME_PATH;
        router.replace(PORTAL_HOME_PATH);
      }
      return;
    }

    const clientId = getClientIdFromRoute(pathname);
    const firstUrl = menus?.find((item) => item.url)?.url;
    if (!firstUrl || !menuBelongsToClient(firstUrl, clientId)) {
      return;
    }

    const apps = clientState
      ? (clientState.appConfigList.length > 0 ? clientState.appConfigList : clientState.clientData)
      : [];
    const waitingForApps = Boolean(
      clientState && (clientState.loading || clientState.appConfigLoading) && apps.length === 0,
    );
    if (waitingForApps) {
      return;
    }

    const registeredUrl = apps.find((item) => item.name === mapClientName(clientId))?.url ?? '';
    const registeredPath = registeredUrl ? menuPathname(registeredUrl) : '';
    const registeredHit = registeredPath && registeredPath !== `/${clientId}`
      ? findMenuUrl(menus, registeredPath)
      : null;
    const destination = registeredHit || firstUrl;

    // A second replace for the same target aborts the navigation still in
    // flight, so the landing page stays blank and header clicks never commit.
    if (requestedRef.current === destination) {
      return;
    }
    requestedRef.current = destination;
    router.replace(destination);
  }, [clientState, menus, pathname, router]);

  return null;
}
