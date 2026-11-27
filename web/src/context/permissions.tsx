import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useLayoutEffect,
  useCallback,
  useMemo,
  useRef,
  ReactNode,
} from 'react';
import { usePathname } from 'next/navigation';
import useApiClient from '@/utils/request';
import { useMenus } from '@/context/menus';
import { MenuItem } from '@/types/index';
import { createLatestRequestGuard } from '@/context/latestRequestGuard';
import {
  getClientIdFromRoute,
  isAppClientMenuRoute,
  isWaitingForClientMenus,
  mapClientName,
} from '@/utils/route';
import { isSessionExpiredState } from '@/utils/sessionExpiry';
import { hasRoutePermission } from '@/context/permission-path';
import {
  buildParentPermissionIndex,
  collectMenuUrls,
  extractPermissions,
  filterMenusByPermission,
} from '@/context/menuAccess';

interface Permissions {
  [url: string]: string[];
}

interface ClientMenuCacheEntry {
  menus: MenuItem[];
  permissions: Permissions;
}

interface PermissionsContextValue {
  menus: MenuItem[];
  permissions: Permissions;
  loading: boolean;
  hasPermission: (url: string) => boolean;
}

const defaultPermissions: Permissions = {};

const appMenuInvalidators = new Set<() => void>();

/** Drop the in-memory menu cache so the next read uses the latest grants. */
export function invalidateAppMenus() {
  appMenuInvalidators.forEach((invalidate) => invalidate());
}

const PermissionsContext = createContext<PermissionsContextValue>({
  menus: [],
  permissions: defaultPermissions,
  loading: true,
  hasPermission: () => false,
});

export const PermissionsProvider = ({ children }: { children: ReactNode }) => {
  const pathname = usePathname();
  const routeClientId = getClientIdFromRoute(pathname);
  const shouldFetchAppMenus = isAppClientMenuRoute(pathname);
  const { configMenus, loading: menuLoading } = useMenus();
  const { get, isLoading: apiLoading } = useApiClient();
  const [menuItems, setMenuItems] = useState<MenuItem[]>([]);
  const [permissions, setPermissions] = useState<Permissions>(defaultPermissions);
  const [loading, setLoading] = useState(true);
  const [menuClientId, setMenuClientId] = useState<string | null>(null);
  const [requestGuard] = useState(createLatestRequestGuard);
  const clientMenuCacheRef = useRef<Record<string, ClientMenuCacheEntry>>({});

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

  useEffect(() => {
    clientMenuCacheRef.current = {};
  }, [configMenus]);

  // Apply per-app cache before paint so top-bar switches do not keep the previous
  // left rail / loading gate for an extra network round-trip.
  useLayoutEffect(() => {
    if (!shouldFetchAppMenus) {
      return;
    }
    const cached = clientMenuCacheRef.current[routeClientId];
    if (!cached || menuClientId === routeClientId) {
      return;
    }
    setMenuItems(cached.menus);
    setPermissions(cached.permissions);
    setMenuClientId(routeClientId);
    setLoading(false);
  }, [menuClientId, routeClientId, shouldFetchAppMenus]);

  const fetchMenus = useCallback(async () => {
    if (isSessionExpiredState()) {
      setLoading(false);
      return;
    }

    if (!shouldFetchAppMenus) {
      setLoading(false);
      return;
    }

    if (apiLoading || menuLoading) {
      return;
    }

    const cached = clientMenuCacheRef.current[routeClientId];
    if (cached) {
      setMenuItems(cached.menus);
      setPermissions(cached.permissions);
      setMenuClientId(routeClientId);
      setLoading(false);
      return;
    }

    const requestId = requestGuard.begin();
    setMenuItems([]);
    setPermissions(defaultPermissions);
    setMenuClientId(routeClientId);
    setLoading(true);

    try {
      const clientName = mapClientName(routeClientId);
      const [menuData, customMenuData] = await Promise.all([
        clientName
          ? get('/core/api/get_user_menus/', { params: { name: clientName } })
          : Promise.resolve([]),
        routeClientId
          ? get('/system_mgmt/custom_menu_group/get_menus/', {
            params: { app: clientName },
          }).catch((error: unknown) => {
            console.warn('Failed to fetch custom menus, using default configMenus:', error);
            return null;
          })
          : Promise.resolve(null),
      ]);

      let menusToFilter: MenuItem[] = configMenus;
      if (customMenuData && customMenuData.is_build_in === false) {
        menusToFilter = Array.isArray(customMenuData.menus) ? customMenuData.menus : [];
      }

      const permissionMap = collectPermissionOperations(menuData || []);
      const filteredMenus = filterMenusByPermission(
        permissionMap,
        menusToFilter,
        routeClientId,
        undefined,
        buildParentPermissionIndex(configMenus),
      );
      const parsedPermissions = extractPermissions(
        filteredMenus,
        {},
        undefined,
        collectMenuUrls(menusToFilter),
      );
      requestGuard.commitIfCurrent(requestId, () => {
        clientMenuCacheRef.current[routeClientId] = {
          menus: filteredMenus,
          permissions: parsedPermissions,
        };
        setMenuItems(filteredMenus);
        setPermissions(parsedPermissions);
        setMenuClientId(routeClientId);
        setLoading(false);
      });
    } catch (err) {
      console.error('Failed to fetch menus:', err);
      requestGuard.commitIfCurrent(requestId, () => {
        setMenuItems([]);
        setPermissions(defaultPermissions);
        setMenuClientId(routeClientId);
        setLoading(false);
      });
    }
  }, [get, apiLoading, menuLoading, configMenus, routeClientId, shouldFetchAppMenus, requestGuard]);

  const fetchMenusRef = useRef(fetchMenus);
  fetchMenusRef.current = fetchMenus;

  useEffect(() => {
    const invalidate = () => {
      clientMenuCacheRef.current = {};
      void fetchMenusRef.current();
    };
    appMenuInvalidators.add(invalidate);
    return () => {
      appMenuInvalidators.delete(invalidate);
    };
  }, []);

  useEffect(() => {
    fetchMenus();
    return () => requestGuard.invalidate();
  }, [fetchMenus, requestGuard]);

  const hasPermission = useCallback(
    (url: string) => {
      return hasRoutePermission(permissions, url);
    },
    [permissions]
  );

  const waitingForClientMenus = isWaitingForClientMenus(pathname, menuClientId);
  const value = useMemo(
    () => ({
      menus: menuItems,
      permissions,
      loading: loading || waitingForClientMenus,
      hasPermission,
    }),
    [menuItems, permissions, loading, waitingForClientMenus, hasPermission],
  );

  return (
    <PermissionsContext.Provider value={value}>
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
