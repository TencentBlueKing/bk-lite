'use client';

import { useEffect, useMemo } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import { MenuItem } from '@/types/index';

export const useRedirectFirstChild = () => {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { menus } = usePermissions();

  const currentMenu = useMemo(() => {
    return menus?.find((menu: MenuItem) => menu?.url && pathname?.startsWith(menu.url));
  }, [pathname, menus]);

  useEffect(() => {
    if (currentMenu?.children?.length) {
      const firstChildPath = currentMenu.children[0].url;
      const params = new URLSearchParams(searchParams || undefined);
      const targetUrl = `${firstChildPath}?${params.toString()}`;
      router.replace(targetUrl);
    }
  }, [router, searchParams, currentMenu]);
};
