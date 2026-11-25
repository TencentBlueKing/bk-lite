import type { MenuItem } from '@/types/index';

export interface RoutePermissions {
  [url: string]: string[];
}

const normalizeMenuUrl = (url: string) => url.replace(/\/+$/, '') || '/';

export const collectMenuUrls = (menus: MenuItem[], acc: string[] = []): string[] => {
  menus.forEach((item) => {
    if (item.url) {
      acc.push(item.url);
    }
    if (item.children?.length) {
      collectMenuUrls(item.children, acc);
    }
  });
  return acc;
};

/** A hidden url must not grant every longer menu that merely shares its prefix. */
export const isStrictMenuPrefix = (url: string, menuUrls: string[]): boolean => {
  const base = normalizeMenuUrl(url);
  return menuUrls.some((other) => {
    const path = normalizeMenuUrl(other);
    return path !== base && path.startsWith(`${base}/`);
  });
};

const hiddenItemIsGranted = (
  menu: MenuItem,
  permissionMap: { [key: string]: string[] },
  parentMenu: MenuItem | undefined,
  menuUrls: string[],
) => {
  if (!menu.isNotMenuItem) return false;
  if (
    Object.prototype.hasOwnProperty.call(permissionMap, menu.name) ||
    Boolean(parentMenu && Object.prototype.hasOwnProperty.call(permissionMap, parentMenu.name))
  ) {
    return true;
  }
  // A top-level hidden page that does not cover a longer menu stays open.
  // Ops Console home has no permission code of its own.
  return !parentMenu && Boolean(menu.url) && !isStrictMenuPrefix(menu.url, menuUrls);
};

export const extractPermissions = (
  menus: MenuItem[],
  accumulated: RoutePermissions = {},
  parentMenu?: MenuItem,
  menuUrls?: string[],
): RoutePermissions => {
  const urls = menuUrls ?? collectMenuUrls(menus);
  menus.forEach((item) => {
    const skipHiddenPrefix = Boolean(item.url && item.isNotMenuItem && isStrictMenuPrefix(item.url, urls));
    if (!skipHiddenPrefix && item.url && item.operation?.length) {
      accumulated[item.url] = item.operation;
    } else if (!skipHiddenPrefix && item.url && item.withParentPermission && parentMenu) {
      accumulated[item.url] = parentMenu.operation || [];
    }
    if (!skipHiddenPrefix && item.url && item.isNotMenuItem) {
      accumulated[item.url] = ['View', ...(parentMenu?.operation || [])];
    }
    if (item.children) {
      extractPermissions(item.children, accumulated, item, urls);
    }
  });
  return accumulated;
};

/**
 * Builtin pages that follow a parent permission (`withParentPermission`) keep
 * that relationship after they are copied into a custom menu. The saved copy
 * does not store the flag, so match the builtin menu by url or name.
 */
export const buildParentPermissionIndex = (menus: MenuItem[]): Map<string, string> => {
  const index = new Map<string, string>();
  const walk = (items: MenuItem[], ownerName?: string) => {
    items.forEach((item) => {
      if (item.withParentPermission && ownerName) {
        if (item.url) index.set(item.url, ownerName);
        if (item.name) index.set(`name:${item.name}`, ownerName);
      }
      if (item.children?.length) {
        walk(item.children, item.withParentPermission ? ownerName : item.name);
      }
    });
  };
  walk(menus);
  return index;
};

const inheritedOwnerName = (
  menu: MenuItem,
  inheritedByKey?: ReadonlyMap<string, string>,
) => {
  if (!inheritedByKey) return undefined;
  if (menu.url && inheritedByKey.has(menu.url)) return inheritedByKey.get(menu.url);
  if (menu.name && inheritedByKey.has(`name:${menu.name}`)) return inheritedByKey.get(`name:${menu.name}`);
  return undefined;
};

const hasNamedPermission = (
  permissionMap: { [key: string]: string[] },
  name: string | undefined,
) => Boolean(name && Object.prototype.hasOwnProperty.call(permissionMap, name));

export const filterMenusByPermission = (
  permissionMap: { [key: string]: string[] },
  menus: MenuItem[],
  routeClientId?: string,
  parentMenu?: MenuItem,
  inheritedByKey?: ReadonlyMap<string, string>,
  menuUrls?: string[],
): MenuItem[] => {
  const urls = menuUrls ?? collectMenuUrls(menus);
  const childHasOwnGrant = (child: MenuItem) =>
    hasNamedPermission(permissionMap, child.name) ||
    hasNamedPermission(permissionMap, inheritedOwnerName(child, inheritedByKey));

  return menus
    .filter((menu) => {
      if (menu.children && menu.children.length > 0 && !menu.url) {
        const hasChildPermission = menu.children.some(
          (child) => childHasOwnGrant(child) || Boolean(child.children?.length),
        );
        if (!hasChildPermission) {
          console.warn(`Directory ${menu.name} has no accessible children`);
          return false;
        }
        return true;
      }

      const hasParentPermission = parentMenu && menu.withParentPermission;
      const hasChildPermission = menu.children?.some((child) => childHasOwnGrant(child));
      const hasPermission =
        hasNamedPermission(permissionMap, menu.name) ||
        hasNamedPermission(permissionMap, inheritedOwnerName(menu, inheritedByKey)) ||
        hiddenItemIsGranted(menu, permissionMap, parentMenu, urls) ||
        hasParentPermission ||
        hasChildPermission;

      if (!hasPermission) {
        console.warn(`No permission for menu: ${menu.name}`);
        return false;
      }

      if (routeClientId && menu.url) {
        const normalizedUrl = menu.url.replace(/\/+$/, '') || '/';
        const clientRoot = `/${routeClientId}`;
        const urlBelongsToClient =
          normalizedUrl === clientRoot || normalizedUrl.startsWith(`${clientRoot}/`);
        if (!urlBelongsToClient) {
          console.warn(`Menu ${menu.name} URL does not contain routeClientId: ${routeClientId}`);
          return false;
        }
      }

      return true;
    })
    .map((menu) => {
      if (menu.children && menu.children.length > 0 && !menu.url) {
        const filteredChildren = filterMenusByPermission(
          permissionMap,
          menu.children,
          routeClientId,
          menu,
          inheritedByKey,
          urls,
        );
        const firstChildWithUrl = filteredChildren.find(child => child.url);
        return {
          ...menu,
          isDirectory: true,
          icon: firstChildWithUrl?.icon || menu.icon,
          url: firstChildWithUrl?.url || menu.url,
          children: filteredChildren
        };
      }

      const inheritedName = inheritedOwnerName(menu, inheritedByKey);
      const operation = hasNamedPermission(permissionMap, menu.name)
        ? permissionMap[menu.name]
        : inheritedName
          ? permissionMap[inheritedName]
          : permissionMap[menu.name];
      return {
        ...menu,
        operation,
        children: menu.children
          ? filterMenusByPermission(permissionMap, menu.children, routeClientId, menu, inheritedByKey, urls)
          : []
      };
    });
};
