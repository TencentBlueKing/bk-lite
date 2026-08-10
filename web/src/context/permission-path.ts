type RoutePermissions = Record<string, readonly string[]>;

const normalizeRoutePath = (path: string) => {
  const pathname = path.split(/[?#]/, 1)[0] || '/';
  return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
};

const isSameOrDescendant = (path: string, ancestor: string) =>
  path === ancestor || (ancestor !== '/' && path.startsWith(`${ancestor}/`));

export const hasRoutePermission = (permissions: RoutePermissions, requestedUrl: string) => {
  const requestedPath = normalizeRoutePath(requestedUrl);
  return Object.keys(permissions).some((permissionUrl) => {
    const permissionPath = normalizeRoutePath(permissionUrl);
    return (
      isSameOrDescendant(requestedPath, permissionPath) ||
      isSameOrDescendant(permissionPath, requestedPath)
    );
  });
};
