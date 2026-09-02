'use client';
import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import { PORTAL_HOME_PATH } from '@/utils/route';

export default function RedirectToFirstMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const { menus, loading } = usePermissions();

  useEffect(() => {
    if (pathname === '/') {
      router.replace(PORTAL_HOME_PATH);
      return;
    }

    if (!loading && menus?.length > 0 && menus[0]?.url) {
      router.replace(menus[0].url);
    }
  }, [loading, menus, pathname, router]);

  return null;
}