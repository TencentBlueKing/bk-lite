'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import sideMenuStyle from './index.module.scss';
import { ArrowLeftOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { MenuItem } from '@/types/index';

export type SideMenuIntroLayout = 'separate' | 'unified';

interface SideMenuProps {
  menuItems: MenuItem[];
  activeKeyword?: boolean;
  keywordName?: string;
  children?: React.ReactNode;
  showBackButton?: boolean;
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  onBackButtonClick?: () => void;
  /**
   * separate: 实体 intro 与菜单分两张卡（默认，工作台/知识库等）
   * unified: 合成左侧一块，intro 与菜单用分割线隔开（智能体详情）
   */
  introLayout?: SideMenuIntroLayout;
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
  introLayout = 'separate',
}) => {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isUnified = introLayout === 'unified';

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

  const renderIcon = (item: MenuItem) => {
    if (item.iconNode) {
      return (
        <span className="mr-2 flex h-4 w-4 items-center justify-center text-[16px] leading-none">
          {item.iconNode}
        </span>
      );
    }

    if (!item.icon) return null;
    return <Icon type={item.icon} className="text-xl pr-1.5" />;
  };

  const renderMenuList = (listPaddingClass = 'p-3') => (
    <ul className={`space-y-0.5 ${listPaddingClass}`}>
      {menuItems.map((item) => {
        const active = isActive(item.url, item.name);
        return (
          <li key={item.url} className={`rounded-md ${active ? sideMenuStyle.active : ''}`}>
            <Link
              href={buildUrlWithParams(item.url)}
              className={`group flex h-10 items-center rounded-md px-3 py-2 text-sm transition-colors ${
                active ? 'font-medium' : 'font-normal'
              }`}
            >
              {renderIcon(item)}
              {item.title}
            </Link>
          </li>
        );
      })}
    </ul>
  );

  const backButton = showBackButton ? (
    <button
      className="absolute bottom-4 left-4 flex items-center py-2 rounded-md text-sm"
      onClick={onBackButtonClick}
    >
      <ArrowLeftOutlined className="mr-2" />
    </button>
  ) : null;

  if (isUnified) {
    return (
      <aside className={`flex h-full w-[216px] flex-shrink-0 flex-col pr-4 ${sideMenuStyle.sideMenu}`}>
        <div className={`relative flex flex-1 flex-col overflow-hidden rounded-md ${sideMenuStyle.nav}`}>
          {children ? (
            <>
              <div className="px-4 pb-2 pt-4">{children}</div>
              <div
                className="mx-4 my-1.5 border-t border-[var(--color-border-2)] opacity-80"
                role="separator"
              />
            </>
          ) : null}
          <nav className="relative flex-1">
            {renderMenuList('p-3 pt-1.5')}
            {showProgress ? taskProgressComponent : null}
            {backButton}
          </nav>
        </div>
      </aside>
    );
  }

  return (
    <aside className={`flex h-full w-[216px] flex-shrink-0 flex-col pr-4 ${sideMenuStyle.sideMenu}`}>
      {children && (
        <div className={`mb-3 min-h-[80px] rounded-md p-4 ${sideMenuStyle.introduction}`}>
          {children}
        </div>
      )}
      <nav className={`relative flex-1 rounded-md ${sideMenuStyle.nav}`}>
        {renderMenuList('p-3')}
        {showProgress ? taskProgressComponent : null}
        {backButton}
      </nav>
    </aside>
  );
};

export default SideMenu;
