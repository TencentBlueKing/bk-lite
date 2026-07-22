'use client';

import React from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import sideMenuStyle from './index.module.scss';
import SideMenuShell from './sideMenuShell';
import SideMenuNavList from './sideMenuNavList';
import { MenuItem } from '@/types/index';

interface SideMenuProps {
  menuItems: MenuItem[];
  activeKeyword?: boolean;
  keywordName?: string;
  children?: React.ReactNode;
  showBackButton?: boolean;
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  onBackButtonClick?: () => void;
  renderBeforeItem?: (item: MenuItem) => React.ReactNode;
  renderAfterItem?: (item: MenuItem) => React.ReactNode;
  onItemClick?: (item: MenuItem) => void;
  className?: string;
  introClassName?: string;
  navClassName?: string;
  listClassName?: string;
  itemClassName?: string;
  activeItemClassName?: string;
  linkClassName?: string;
}

const SideMenu: React.FC<SideMenuProps> = ({
  menuItems,
  children,
  activeKeyword = false,
  keywordName = '',
  showBackButton = true,
  showProgress = false,
  taskProgressComponent,
  onBackButtonClick,
  renderBeforeItem,
  renderAfterItem,
  onItemClick,
  className,
  introClassName,
  navClassName,
  listClassName,
  itemClassName = 'rounded-md mb-1',
  activeItemClassName = sideMenuStyle.active,
  linkClassName,
}) => {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const buildUrlWithParams = (path: string) => {
    if(activeKeyword) {
      return path;
    }
    const params = new URLSearchParams(searchParams || undefined);
    return `${path}?${params.toString()}`;
  };

  const isActive = (path: string, name: string): boolean => {
    if (activeKeyword) {
      const key = searchParams.get(keywordName) || '';
      if(keywordName === '') return false;
      return key === name;
    }
    if (pathname === null) return false;
    return pathname.startsWith(path);
  };

  return (
    <SideMenuShell
      intro={children}
      showBackButton={showBackButton}
      showProgress={showProgress}
      taskProgressComponent={taskProgressComponent}
      onBackButtonClick={onBackButtonClick}
      className={className || sideMenuStyle.sideMenu}
      introClassName={introClassName || sideMenuStyle.introduction}
      navClassName={navClassName || sideMenuStyle.nav}
    >
      <SideMenuNavList
        menuItems={menuItems}
        buildHref={(item) => buildUrlWithParams(item.url)}
        isItemActive={(item) => isActive(item.url, item.name)}
        onItemClick={onItemClick}
        renderBeforeItem={renderBeforeItem}
        renderAfterItem={renderAfterItem}
        listClassName={listClassName}
        itemClassName={itemClassName}
        activeItemClassName={activeItemClassName}
        linkClassName={linkClassName}
      />
    </SideMenuShell>
  );
};

export default SideMenu;
