'use client';

import { useEffect, useMemo } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import { MenuItem } from '@/types/index';
import { getClientIdFromRoute } from '@/utils/route';

const menuBelongsToClient = (menuUrl: string, clientId: string) => {
  const normalized = menuUrl.replace(/\/+$/, '') || '/';
  const root = `/${clientId}`;
  return normalized === root || normalized.startsWith(`${root}/`);
};

export const useRedirectFirstChild = () => {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { menus } = usePermissions();

  const currentMenu = useMemo(() => {
    if (!pathname || !menus) return null;

    // 递归查找匹配的菜单项
    const findMatchedMenu = (items: MenuItem[]): MenuItem | null => {
      for (const menu of items) {
        // 如果是容器节点（没有 url、isDirectory 或 isNotMenuItem），直接递归查找子菜单
        if (!menu.url || menu.isDirectory || menu.isNotMenuItem) {
          if (menu.children?.length) {
            const childMatch = findMatchedMenu(menu.children);
            if (childMatch) {
              return childMatch;
            }
          }
          continue;
        }

        // 1. 精确匹配
        if (menu.url === pathname) {
          return menu;
        }

        // 2. 前缀匹配
        if (pathname.startsWith(menu.url)) {
          // 如果有子菜单，继续在子菜单中查找更精确的匹配
          if (menu.children?.length) {
            const childMatch = findMatchedMenu(menu.children);
            // 如果子菜单中找到了匹配，返回子菜单匹配项
            if (childMatch) {
              return childMatch;
            }
          }
          // 如果子菜单中没找到，返回当前菜单
          return menu;
        }
      }
      return null;
    };

    return findMatchedMenu(menus);
  }, [pathname, menus]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams || undefined);
    const withQuery = (path: string) => `${path}?${params.toString()}`;

    if (currentMenu?.children?.length) {
      const firstChildPath = currentMenu.children[0].url;
      if (firstChildPath) {
        router.replace(withQuery(firstChildPath));
      }
      return;
    }

    // The stub page is not a parent in the current menu. Enter the first real page.
    if (!pathname || !menus?.length) return;
    const clientId = getClientIdFromRoute(pathname);
    const nextUrl = menus.find((item) => {
      if (!item.url || item.isNotMenuItem) return false;
      const normalized = item.url.replace(/\/+$/, '') || '/';
      if (normalized === pathname) return false;
      return menuBelongsToClient(item.url, clientId);
    })?.url;
    if (nextUrl) {
      router.replace(withQuery(nextUrl));
    }
  }, [router, searchParams, currentMenu, menus, pathname]);
};
