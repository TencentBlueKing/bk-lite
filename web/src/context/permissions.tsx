import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import useApiClient from '@/utils/request';
import { useMenus } from '@/context/menus';
import { MenuItem } from '@/types/index';
import { getClientIdFromRoute, mapClientName } from '@/utils/route';

interface Permissions {
  [url: string]: string[];
}

interface PermissionsContextValue {
  menus: MenuItem[];
  permissions: Permissions;
  loading: boolean;
  hasPermission: (url: string) => boolean;
}

const defaultPermissions: Permissions = {};

const PermissionsContext = createContext<PermissionsContextValue>({
  menus: [],
  permissions: defaultPermissions,
  loading: true,
  hasPermission: () => false,
});

export const PermissionsProvider = ({ children }: { children: ReactNode }) => {
  const { configMenus, loading: menuLoading } = useMenus();
  const { get, isLoading: apiLoading } = useApiClient();
  const [menuItems, setMenuItems] = useState<MenuItem[]>([]);
  const [permissions, setPermissions] = useState<Permissions>(defaultPermissions);
  const [loading, setLoading] = useState(true);

  const extractPermissions = (
    menus: MenuItem[],
    accumulated: Permissions = {},
    parentMenu?: MenuItem
  ): Permissions => {
    for (const item of menus) {
      if (item.url && item.operation?.length) {
        accumulated[item.url] = item.operation;
      } else if (item.url && item.withParentPermission && parentMenu) {
        accumulated[item.url] = parentMenu.operation || [];
      }
      if (item.url && item.isNotMenuItem) {
        accumulated[item.url] = ['View', ...(parentMenu?.operation || [])];
      }
      if (item.children) {
        extractPermissions(item.children, accumulated, item);
      }
    }
    return accumulated;
  };

  const collectPermissionOperations = (permissions: MenuItem[]): { [key: string]: string[] } => {
    const permissionMap: { [key: string]: string[] } = {};

    const collectOperations = (items: MenuItem[]) => {
      items.forEach((item) => {
        permissionMap[item.name] = item.operation || [];
        if (item.children) {
          collectOperations(item.children);
        }
      });
    };

    collectOperations(permissions);
    return permissionMap;
  };

  const filterMenusByPermission = (
    permissionMap: { [key: string]: string[] },
    menus: MenuItem[],
    routeClientId?: string,
    parentMenu?: MenuItem
  ): MenuItem[] => {
    return menus
      .filter((menu) => {
        const hasParentPermission = parentMenu && menu.withParentPermission;
        const hasChildPermission = menu.children?.some((child) =>
          permissionMap.hasOwnProperty(child.name)
        );
        const hasPermission =
          permissionMap.hasOwnProperty(menu.name) ||
          menu.isNotMenuItem ||
          hasParentPermission ||
          hasChildPermission;
          
        if (!hasPermission) {
          console.warn(`No permission for menu: ${menu.name}`);
          return false;
        }
        
        // Filter by routeClientId if provided and menu has URL
        if (routeClientId && menu.url) {
          const urlContainsClientId = menu.url.includes(`/${routeClientId}/`);
          if (!urlContainsClientId) {
            console.warn(`Menu ${menu.name} URL does not contain routeClientId: ${routeClientId}`);
            return false;
          }
        }
        
        return true;
      })
      .map((menu) => ({
        ...menu,
        operation: permissionMap[menu.name],
        children: menu.children
          ? filterMenusByPermission(permissionMap, menu.children, routeClientId, menu)
          : []
      }));
  };

  const fetchMenus = useCallback(async () => {
    if (!apiLoading && !menuLoading) {
      setLoading(true);
      try {
        const routeClientId = getClientIdFromRoute();
        const clientName = mapClientName(routeClientId);
        let allMenuData: MenuItem[] = [];
        
        if (clientName) {
          const menuData = await get('/core/api/get_user_menus/', { params: { name: clientName } });
          allMenuData = menuData || [];
        }
        
        const permissionMap = collectPermissionOperations(allMenuData);
        const filteredMenus = filterMenusByPermission(permissionMap, configMenus, routeClientId);
        const parsedPermissions = extractPermissions(filteredMenus);
        setMenuItems(filteredMenus);
        setPermissions(parsedPermissions);
        setLoading(false);
      } catch (err) {
        console.error('Failed to fetch menus:', err);
        setLoading(false);
      }
    }
  }, [get, apiLoading, menuLoading, configMenus]);

  useEffect(() => {
    fetchMenus();
  }, [apiLoading, menuLoading]);

  const hasPermission = useCallback(
    (url: string) => {
      return Object.keys(permissions).some((permissionUrl) => permissionUrl.startsWith(url));
    },
    [permissions]
  );

  return (
    <PermissionsContext.Provider value={{ menus: menuItems, permissions, loading, hasPermission }}>
      {children}
    </PermissionsContext.Provider>
  );
};

export const usePermissions = () => {
  const context = useContext(PermissionsContext);
  if (!context) {
    throw new Error('usePermissions must be used within a PermissionsProvider');
  }
  return context;
};
