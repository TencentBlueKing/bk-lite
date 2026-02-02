'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import sideMenuStyle from './index.module.scss';
import { ArrowLeftOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
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
    <aside className={`w-[216px] pr-4 flex flex-shrink-0 flex-col h-full ${sideMenuStyle.sideMenu}`}>
      {children && (
        <div className={`${showBackButton ? 'pl-2 pr-4 py-4' : 'p-4'} rounded-md mb-3 h-[80px] ${sideMenuStyle.introduction}`}>
          <div className="flex items-start h-full w-full">
            {showBackButton && (
              <button
                className="flex items-center justify-center w-5 h-5 mt-0.5 mr-1.5 rounded cursor-pointer hover:bg-[var(--color-bg-3)] flex-shrink-0"
                onClick={onBackButtonClick}
              >
                <ArrowLeftOutlined className="text-sm" />
              </button>
            )}
            <div className="flex-1 overflow-hidden">
              {children}
            </div>
          </div>
        </div>
      )}
      <nav className={`flex-1 relative rounded-md ${sideMenuStyle.nav}`}>
        <ul className="p-3">
          {menuItems.map((item) => (
            <li key={item.url} className={`rounded-md mb-1 ${isActive(item.url, item.name) ? sideMenuStyle.active : ''}`}>
              <Link legacyBehavior href={buildUrlWithParams(item.url)}>
                <a className={`group flex items-center h-9 rounded-md py-2 text-sm font-normal px-3`}>
                  {item.icon && <Icon type={item.icon} className="text-xl pr-1.5" />}
                  {item.title}
                </a>
              </Link>
            </li>
          ))}
        </ul>
        {showProgress && (
          <>
            {taskProgressComponent}
          </>
        )}
      </nav>
    </aside>
  );
};

export default SideMenu;
