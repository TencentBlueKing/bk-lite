'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
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
  menuLevel?: number;
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
  menuLevel // 可选参数
}) => {
  const router = useRouter();
  const curRouterName = usePathname();
  const pathname = pagePathName ?? curRouterName;
  const { menus } = usePermissions();
  const [selectedKey, setSelectedKey] = useState<string>(pathname ?? '');
  const [menuItems, setMenuItems] = useState<MenuItem[]>([])

  const getMenuItemsForPath = useCallback((menus: MenuItem[], currentPath: string, targetLevel?: number): MenuItem[] => {
    if (!currentPath || menus.length === 0) return [];

    // Auto mode: find the deepest matching menu layer and return its items
    if (targetLevel === undefined) {
      const findMatchedMenuPath = (items: MenuItem[], path: MenuItem[] = []): MenuItem[] | null => {
        for (const item of items) {
          const currentPath_inner = [...path, item];
          
          if (item.url) {
            if (item.url === currentPath || currentPath.startsWith(item.url)) {
              if (item.children?.length) {
                const childMatch = findMatchedMenuPath(item.children, currentPath_inner);
                if (childMatch) return childMatch;
              }
              return currentPath_inner;
            }
          }

          if (item.children?.length) {
            const found = findMatchedMenuPath(item.children, currentPath_inner);
            if (found) return found;
          }
        }
        return null;
      };

      const menuPath = findMatchedMenuPath(menus);
      
      console.log('Auto mode - Matched menu path:', menuPath?.map(m => m.name || m.title), 'for path:', currentPath);
      
      if (menuPath && menuPath.length > 0) {
        const lastLayer = menuPath[menuPath.length - 1];
        
        if (lastLayer.children?.length) {
          const result = lastLayer.children.filter(m => !m.isNotMenuItem && !m.isDirectory);
          return result;
        }
        else if (menuPath.length >= 2) {
          const secondLastLayer = menuPath[menuPath.length - 2];
          if (secondLastLayer.children?.length) {
            const result = secondLastLayer.children.filter(m => !m.isNotMenuItem && !m.isDirectory);
            return result;
          }
        }
      }

      return [];
    }

    // Target level mode: return menus at specified layer (e.g., menuLevel=1 returns siblings of layer 1)
    if (targetLevel === 1) {
      const findMatchedMenuPath = (items: MenuItem[], path: MenuItem[] = []): MenuItem[] | null => {
        for (const item of items) {
          const currentPath_inner = [...path, item];
          
          if (item.url) {
            if (item.url === currentPath || currentPath.startsWith(item.url)) {
              if (item.children?.length) {
                const childMatch = findMatchedMenuPath(item.children, currentPath_inner);
                if (childMatch) return childMatch;
              }
              return currentPath_inner;
            }
          }

          if (item.children?.length) {
            const found = findMatchedMenuPath(item.children, currentPath_inner);
            if (found) return found;
          }
        }
        return null;
      };

      const menuPath = findMatchedMenuPath(menus);
      
      // Return siblings of layer 1 (children of layer 0)
      if (menuPath && menuPath.length >= 2) {
        const parentLayer = menuPath[0];
        if (parentLayer.children?.length) {
          const result = parentLayer.children.filter(m => !m.isNotMenuItem && !m.isDirectory);
          return result;
        }
      }

      return [];
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
    router.push(key as string);
    setSelectedKey(key as string);
  }, [router]);

  const segmentedOptions = useMemo(() => {
    return menuItems.map(item => ({
      label: (
        <div className="flex items-center justify-center">
          {item.icon && (
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
                options={segmentedOptions}
                value={selectedKey}
                onChange={handleSegmentChange}
              />
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
