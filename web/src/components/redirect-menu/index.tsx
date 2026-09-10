'use client';
import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import { getClientIdFromRoute, PORTAL_HOME_PATH } from '@/utils/route';

const menuBelongsToClient = (menuUrl: string, clientId: string) => {
  const normalized = menuUrl.replace(/\/+$/, '') || '/';
  const root = `/${clientId}`;
  return normalized === root || normalized.startsWith(`${root}/`);
};

export default function RedirectToFirstMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const { menus } = usePermissions();

  useEffect(() => {
    if (pathname === '/') {
      router.replace(PORTAL_HOME_PATH);
      return;
    }

    const clientId = getClientIdFromRoute(pathname);
    const firstUrl = menus?.find((item) => item.url)?.url;
    if (firstUrl && menuBelongsToClient(firstUrl, clientId)) {
      router.replace(firstUrl);
    }
  }, [menus, pathname, router]);

  return null;
}
