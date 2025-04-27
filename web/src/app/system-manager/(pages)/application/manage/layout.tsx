'use client';

import React, { useState, useEffect, useMemo } from 'react';
import SideMenu from '@/components/sub-layout/side-menu';
import TopSection from '@/components/top-section';
import { useUserApi } from '@/app/system-manager/api/user';
import { MenuItem } from '@/types/index';
import { usePermissions } from '@/context/permissions';
import { usePathname, useSearchParams } from 'next/navigation';

const AppManageLayout = ({ children }: { children: React.ReactNode }) => {
  const pathname = usePathname();
  const { menus } = usePermissions();
  const searchParams = useSearchParams();
  const [clientName, setClientName] = useState('');
  const [clientDescription, setClientDescription] = useState('');
  const [menuItems, setMenuItems] = useState<MenuItem[]>([]);

  const id = searchParams ? searchParams.get('id') : null;
  const { getClientDetail } = useUserApi();

  const updateMenuItems = useMemo(() => {
    const currentMenu = menus.find((menu: MenuItem) => menu?.url && pathname?.startsWith(menu.url));
    return currentMenu?.children || [];
  }, [menus, pathname]);

  useEffect(() => {
    setMenuItems(updateMenuItems);
  }, [updateMenuItems]);

  useEffect(() => {
    fetchClientDetail();
  }, []);

  const fetchClientDetail = async () => {
    const client = await getClientDetail({ params: { id } });
    setClientName(client.name);
    setClientDescription(client.description);
  };

  return (
    <div className="h-full w-full">
      <TopSection title={clientName} content={clientDescription} />
      <div className="flex mt-4 w-full" style={{ height: 'calc(100vh - 185px)' }}>
        <SideMenu showBackButton={false} menuItems={menuItems} />
        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          {children}
        </div>
      </div>
    </div>
  );
};

export default AppManageLayout;
