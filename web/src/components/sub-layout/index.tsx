'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import SideMenu from './side-menu';
import sideMenuStyle from './index.module.scss';
import { Segmented } from 'antd';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { MenuItem } from '@/types/index';
import Icon from '@/components/icon';
import { usePermissions } from '@/context/permissions';
import {
  getDeepestMatchedMenuItems,
  getFirstLayerSiblingMenuItems,
} from '@/utils/menuHelpers';
import { isScreenModeEnabled, withScreenQuery } from '@/console-layout';

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
  menuLevel?: number;
  /** separate=分卡（默认）；unified=左侧整块+分割线 */
  introLayout?: 'separate' | 'unified';
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
  customMenuItems,
  menuLevel, // 可选参数
  introLayout = 'separate',
}) => {
  const router = useRouter();
  const curRouterName = usePathname();
  const searchParams = useSearchParams();
  const screenMode = isScreenModeEnabled(searchParams);
  const pathname = pagePathName ?? curRouterName;
  const { menus } = usePermissions();
  const [selectedKey, setSelectedKey] = useState<string>(pathname ?? '');
  const [menuItems, setMenuItems] = useState<MenuItem[]>([])

  const getMenuItemsForPath = useCallback((menus: MenuItem[], currentPath: string, targetLevel?: number): MenuItem[] => {
    if (!currentPath || menus.length === 0) return [];

    // Longest-path matching + leaf sibling fallback (see menuHelpers).
    if (targetLevel === undefined) {
      return getDeepestMatchedMenuItems(menus, currentPath);
    }

    if (targetLevel === 1) {
      return getFirstLayerSiblingMenuItems(menus, currentPath);
    }

    return [];
  }, []);

  const updateMenuItems = useMemo(() => {
    if (customMenuItems && customMenuItems.length > 0) {
      return customMenuItems;
    }
    const result = getMenuItemsForPath(menus, pathname ?? '', menuLevel);
    return result;
  }, [pathname, menus, customMenuItems, getMenuItemsForPath, menuLevel]);

  useEffect(() => {
    const filteredItems = updateMenuItems?.filter(menu => {
      const shouldKeep = !menu?.isNotMenuItem;
      return shouldKeep;
    }) || [];
    setMenuItems(filteredItems);

    // Update selectedKey with improved matching logic
    if (filteredItems.length > 0) {
      let urlKey = filteredItems.find((menu) => menu.url === curRouterName)?.url;
      
      if (!urlKey) {
        urlKey = filteredItems.find(
          (menu) => menu.url && curRouterName && curRouterName.startsWith(menu.url)
        )?.url;
      }
      
      if (!urlKey && curRouterName) {
        const pathSegments = curRouterName.split('/').filter(Boolean);
        const lastSegment = pathSegments[pathSegments.length - 1];
        urlKey = filteredItems.find((menu) => menu.name === lastSegment)?.url;
      }
      
      setSelectedKey(urlKey || curRouterName || '');
    } else {
      setSelectedKey(curRouterName || '');
    }
  }, [updateMenuItems, curRouterName, pagePathName]);

  const handleSegmentChange = useCallback((key: string | number) => {
    router.push(withScreenQuery(key as string, isScreenModeEnabled(searchParams)));
    setSelectedKey(key as string);
  }, [router, searchParams]);

  const segmentedOptions = useMemo(() => {
    return menuItems.map(item => ({
      label: (
        <div className="flex items-center justify-center">
          {item.iconNode ? (
            <span className="mr-2 flex h-4 w-4 items-center justify-center text-[14px] leading-none">
              {item.iconNode}
            </span>
          ) : item.icon && (
            <Icon type={item.icon} className="mr-2 text-sm" />
          )} {item.title}
        </div>
      ),
      value: item.url,
    }));
  }, [menuItems]);

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
            {showSideMenu && menuItems.length > 0 && !screenMode && (
              <SideMenu
                menuItems={menuItems}
                showBackButton={showBackButton}
                activeKeyword={activeKeyword}
                keywordName={keywordName}
                showProgress={showProgress}
                taskProgressComponent={taskProgressComponent}
                onBackButtonClick={onBackButtonClick}
                introLayout={introLayout}
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
          {menuItems.length > 0 && !screenMode ? (
            <>
              <div className={sideMenuStyle.segmentedNav}>
                <Segmented
                  className="sub-layout-segmented"
                  options={segmentedOptions}
                  value={selectedKey}
                  onChange={handleSegmentChange}
                />
              </div>
              <div className="flex-1 pt-4 rounded-md overflow-auto">
                {children}
              </div>
            </>
          ) : (
            <div className="flex-1 rounded-md overflow-auto">
              {children}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default WithSideMenuLayout;
