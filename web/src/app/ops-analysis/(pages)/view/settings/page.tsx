'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { usePermissions } from '@/context/permissions';

export default function AnalysisSetting() {
  const router = useRouter();
  const { menus, loading } = usePermissions();

  useEffect(() => {
    if (loading) return;

    const viewMenu = menus.find((menu) => menu.url === '/ops-analysis/view');

    if (!viewMenu?.children || viewMenu.children.length === 0) return;

    const firstChild = viewMenu.children.find((child) => child.url);

    if (firstChild?.url) {
      router.replace(firstChild.url);
    }
  }, [loading, menus, router]);

  return null;
}
