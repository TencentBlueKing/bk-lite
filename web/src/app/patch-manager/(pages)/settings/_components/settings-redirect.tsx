'use client';

import { useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import type { MenuItem } from '@/types';

const SETTINGS_MENU_NAME = 'patch_settings';

const findSettingsMenu = (menus: MenuItem[]): MenuItem | undefined => {
  for (const menu of menus) {
    if (menu.name === SETTINGS_MENU_NAME) return menu;
    const matchedChild = findSettingsMenu(menu.children ?? []);
    if (matchedChild) return matchedChild;
  }
  return undefined;
};

export const findSettingsTargetUrl = (menus: MenuItem[]) => {
  const settingsMenu = findSettingsMenu(menus);
  return settingsMenu?.children?.find((child) => child.url)?.url;
};

export default function SettingsRedirect() {
  const router = useRouter();
  const { menus, loading } = usePermissions();
  const targetUrl = useMemo(() => findSettingsTargetUrl(menus), [menus]);

  useEffect(() => {
    if (!loading && targetUrl) {
      router.replace(targetUrl);
    }
  }, [loading, router, targetUrl]);

  return null;
}
