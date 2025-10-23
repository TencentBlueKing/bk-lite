'use client';

import React, { useState, useEffect, useMemo } from 'react';
import SideMenu from './side-menu';
import sideMenuStyle from './index.module.scss';
import { Segmented } from 'antd';
import { usePathname, useRouter } from 'next/navigation';
import { MenuItem } from '@/types/index';
import Icon from '@/components/icon';
import { usePermissions } from '@/context/permissions';

interface WithSideMenuLayoutProps {
  intro?: React.ReactNode;
  showBackButton?: boolean;
  activeKeyword?: boolean;
  keywordName?: string;
  onBackButtonClick?: () => void;
  children: React.ReactNode;
  topSection?: React.ReactNode;
  showProgress?: boolean;
  showSideMenu?: boolean;
  layoutType?: 'sideMenu' | 'segmented';
  taskProgressComponent?: React.ReactNode;
  pagePathName?: string;
  customMenuItems?: MenuItem[];
}

const WithSideMenuLayout: React.FC<WithSideMenuLayoutProps> = ({
  intro,
  showBackButton,
  onBackButtonClick,
  children,
  topSection,
  showProgress,
  showSideMenu = true,
  activeKeyword = false,
  keywordName = '',
  layoutType = 'sideMenu',
  taskProgressComponent,
  pagePathName,
  customMenuItems
}) => {
  const router = useRouter();
  const curRouterName = usePathname();
  const pathname = pagePathName ?? curRouterName;
  const { menus } = usePermissions();
  const [selectedKey, setSelectedKey] = useState<string>(pathname ?? '');
  const [menuItems, setMenuItems] = useState<MenuItem[]>([])

  const getMenuItemsForPath = (menus: MenuItem[], currentPath: string): MenuItem[] => {
    const matchedMenu = menus.find(menu => menu.url && menu.url !== currentPath && currentPath.startsWith(menu.url));

    if (matchedMenu) {
      if (matchedMenu.children?.length) {
        const validChildren = matchedMenu.children.filter(m => !m.isNotMenuItem);

        if (validChildren.length > 0) {
          const childResult = getMenuItemsForPath(validChildren, currentPath);
          if (childResult.length > 0) {
            return childResult;
          }
        }
      }

      return matchedMenu.children || [];
    }

    return [];
  };

  const updateMenuItems = useMemo(() => {
    if (customMenuItems && customMenuItems.length > 0) {
      return customMenuItems;
    }
    return getMenuItemsForPath(menus, pathname ?? '');
  }, [pathname, menus, customMenuItems]);

  useEffect(() => {
    setMenuItems(updateMenuItems?.filter(menu => !menu.isNotMenuItem));
  }, [updateMenuItems]);

  useEffect(() => {
    let urlKey: string | undefined = curRouterName ?? undefined;
    if (pagePathName) {
      urlKey = menuItems.find(
        (menu) => menu.url && curRouterName && curRouterName.startsWith(menu.url)
      )?.url;
    }
    setSelectedKey(urlKey as string);
  }, [curRouterName, menuItems]);


  const handleSegmentChange = (key: string | number) => {
    router.push(key as string);
    setSelectedKey(key as string);
  };

  return (
    <div className={`flex w-full h-full text-sm ${sideMenuStyle.sideMenuLayout} ${(intro && topSection) ? 'grow' : 'flex-col'}`}>
      {layoutType === 'sideMenu' ? (
        <>
          {(!intro && topSection) && (
            <div className="mb-4 w-full rounded-md">
              {topSection}
            </div>
          )}
          <div className="w-full flex grow flex-1 h-full">
            {showSideMenu && menuItems.length > 0 && (
              <SideMenu
                menuItems={menuItems}
                showBackButton={showBackButton}
                activeKeyword={activeKeyword}
                keywordName={keywordName}
                showProgress={showProgress}
                taskProgressComponent={taskProgressComponent}
                onBackButtonClick={onBackButtonClick}
              >
                {intro}
              </SideMenu>
            )}
            <section className="flex-1 flex flex-col overflow-hidden">
              {(intro && topSection) && (
                <div className={`mb-4 w-full rounded-md ${sideMenuStyle.sectionContainer}`}>
                  {topSection}
                </div>
              )}
              <div className={`p-4 flex-1 rounded-md overflow-auto ${sideMenuStyle.sectionContainer} ${sideMenuStyle.sectionContext}`}>
                {children}
              </div>
            </section>
          </div>
        </>
      ) : (
        <div className={`flex flex-col w-full h-full ${sideMenuStyle.segmented}`}>
          {menuItems.length > 0 ? (
            <>
              <Segmented
                options={menuItems.map(item => ({
                  label: (
                    <div className="flex items-center justify-center">
                      {item.icon && (
                        <Icon type={item.icon} className="mr-2 text-sm" />
                      )} {item.title}
                    </div>
                  ),
                  value: item.url,
                }))}
                value={selectedKey}
                onChange={handleSegmentChange}
              />
              <div className="flex-1 pt-4 rounded-md overflow-auto">
                {children}
              </div>
            </>
          ) : (
            <div className="flex-1 pt-4 rounded-md overflow-auto">
              {children}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default WithSideMenuLayout;
