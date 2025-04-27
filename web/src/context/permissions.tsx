import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import useApiClient from '@/utils/request';
import { useClientData } from '@/context/client';
import { useMenus } from '@/context/menus';
import { MenuItem } from '@/types/index';

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
  const { myClientData, loading: clientLoading } = useClientData();
  const [menuItems, setMenuItems] = useState<MenuItem[]>([]);
  const [permissions, setPermissions] = useState<Permissions>(defaultPermissions);
  const [loading, setLoading] = useState(true);

  const extractPermissions = (menus: MenuItem[], accumulated: Permissions = {}): Permissions => {
    for (const item of menus) {
      if (item.url && item.operation?.length) {
        accumulated[item.url] = item.operation;
      }
      if (item.url && item.isNotMenuItem) {
        accumulated[item.url] = ['View'];
      }
      if (item.children) {
        extractPermissions(item.children, accumulated);
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
    menus: MenuItem[]
  ): MenuItem[] => {
    return menus
      .filter((menu) => {
        const hasPermission = permissionMap.hasOwnProperty(menu.name) || menu.isNotMenuItem;
        if (!hasPermission) {
          console.warn(`No permission for menu: ${menu.name}`);
        }
        return hasPermission;
      })
      .map((menu) => ({
        ...menu,
        operation: permissionMap[menu.name],
        children: menu.children
          ? filterMenusByPermission(permissionMap, menu.children)
          : []
      }));
  };

  const fetchMenus = useCallback(async () => {
    if (!clientLoading && !apiLoading && !menuLoading) {
      setLoading(true);
      try {
        let allMenuData: MenuItem[] = [];
        if (myClientData && myClientData.length > 0) {
          const menuPromises = myClientData.map(client =>
            get('/core/api/get_user_menus/', { params: { id: client.id } })
          );
          const menuResults = await Promise.all(menuPromises);
          allMenuData = menuResults.flat();
        }
        const permissionMap = collectPermissionOperations(allMenuData);
        const filteredMenus = filterMenusByPermission(permissionMap, configMenus);
        const parsedPermissions = extractPermissions(filteredMenus);
        setMenuItems(filteredMenus);
        setPermissions(parsedPermissions);
        setLoading(false);
      } catch (err) {
        console.error('Failed to fetch menus:', err);
        setLoading(false);
      }
    }
  }, [get, apiLoading, clientLoading, menuLoading, myClientData, configMenus]);

  useEffect(() => {
    if (!clientLoading && myClientData.length) {
      fetchMenus();
    }
  }, [clientLoading, apiLoading, menuLoading]);

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
