import { useSession } from 'next-auth/react';
import { usePathname } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import { useMemo } from 'react';

const useBtnPermissions = () => {
  const { data: session, status } = useSession();
  const currentPath = usePathname();
  const { permissions } = usePermissions();

  // 使用 useMemo 避免条件化 Hook 调用
  const hasPermission = useMemo(() => {
    if (status === 'loading' || !session || !permissions) {
      return () => false;
    }

    const routePermissions = currentPath ? permissions[currentPath] || [] : [];

    return (requiredPermissions: string[]): boolean => {
      const userPermissions = new Set<string>();
      routePermissions.forEach((permission: string) => {
        userPermissions.add(permission);
      });

      return requiredPermissions.some((permission) =>
        userPermissions.has(permission)
      );
    };
  }, [status, session, permissions, currentPath]);

  return { hasPermission };
};

export default useBtnPermissions;
