'use client';

import type { ReactNode } from 'react';

import Permission from '@/components/permission';

interface RumPermissionProps {
  /** Menu resource name under /rum, e.g. applications / sessions / monitors. */
  resource: string;
  action?: 'View' | 'Operate';
  children: ReactNode;
  fallback?: ReactNode;
  className?: string;
}

/**
 * Permission host adapter: maps RUM menu resources to BK-Lite route permissions.
 * Menu entries use `name` in constants/menu.json; permissions are `{name}-View|Operate`.
 */
export default function RumPermission({
  resource,
  action = 'Operate',
  children,
  fallback,
  className,
}: RumPermissionProps) {
  const permissionPath = resource.startsWith('/rum/')
    ? resource
    : `/rum/${resource.replace(/^\/+/, '')}`;

  return (
    <Permission
      requiredPermissions={[action]}
      permissionPath={permissionPath}
      fallback={fallback}
      className={className}
    >
      {children}
    </Permission>
  );
}
