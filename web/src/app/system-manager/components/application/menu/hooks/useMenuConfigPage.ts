'use client';

import { useState, useCallback } from 'react';
import { message } from 'antd';
import { useRoleApi } from '@/app/system-manager/api/application';
import type { FunctionMenuItem, SourceMenuNode } from '@/app/system-manager/types/menu';
import type { MixedItem, MenuGroup } from './useMenuConfig';

interface MenuDetailData {
  display_name?: string;
  menus?: Array<{
    name: string;
    title?: string;
    url?: string;
    icon?: string;
    children?: Array<{
      name: string;
      title?: string;
      url?: string;
      icon?: string;
      children?: Array<{
        name: string;
        title?: string;
        url?: string;
        icon?: string;
      }>;
    }>;
  }>;
}

interface UseMenuDetailLoaderReturn {
  detailLoading: boolean;
  loadMenuDetail: () => Promise<void>;
}

export function useMenuDetailLoader(
  menuId: string,
  sourceMenus: SourceMenuNode[],
  setMenuName: (name: string) => void,
  setMixedItems: (items: MixedItem[]) => void,
  setSelectedKeys: (keys: string[]) => void,
  t: (key: string) => string
): UseMenuDetailLoaderReturn {
  const { getCustomMenuDetail } = useRoleApi();
  const [detailLoading, setDetailLoading] = useState(false);

  const findOriginName = useCallback(
    (pageName: string): string | undefined => {
      for (const menu of sourceMenus) {
        const child = menu.children?.find((c) => c.name === pageName);
        if (child) {
          return `${menu.display_name}/${child.display_name}`;
        }
      }
      return undefined;
    },
    [sourceMenus]
  );

  const findSourceMenu = useCallback(
    (menuName: string) => {
      return sourceMenus.find((m) => m.name === menuName);
    },
    [sourceMenus]
  );

  const loadMenuDetail = useCallback(async () => {
    if (!menuId || sourceMenus.length === 0) return;

    setDetailLoading(true);
    try {
      const detail: MenuDetailData = await getCustomMenuDetail({ id: menuId });

      if (detail.display_name) {
        setMenuName(detail.display_name);
      }

      if (detail.menus && Array.isArray(detail.menus)) {
        const loadedMixedItems: MixedItem[] = detail.menus.map((menu, index) => {
          const sourceMenu = findSourceMenu(menu.name);
          const isDetail = sourceMenu?.isDetailMode;

          if (isDetail && menu.children && Array.isArray(menu.children)) {
            return {
              type: 'page' as const,
              id: menu.name,
              data: {
                name: menu.name,
                display_name: menu.title || menu.name,
                url: menu.url,
                icon: menu.icon,
                type: 'page' as const,
                originName: menu.title || menu.name,
                isDetailMode: true,
                hiddenChildren: menu.children.map((child) => ({
                  name: child.name,
                  display_name: child.title || child.name,
                  url: child.url,
                  icon: child.icon,
                  type: 'page' as const,
                })),
              },
            };
          }

          if (menu.children && Array.isArray(menu.children)) {
            return {
              type: 'group' as const,
              id: `group-${index}`,
              data: {
                id: `group-${index}`,
                name: menu.title || menu.name,
                icon: menu.icon,
                children: menu.children.map((child) => {
                  const childSourceMenu = findSourceMenu(child.name);
                  const isChildDetail = childSourceMenu?.isDetailMode;

                  if (isChildDetail && child.children && Array.isArray(child.children)) {
                    return {
                      name: child.name,
                      display_name: child.title || child.name,
                      url: child.url,
                      icon: child.icon,
                      type: 'page' as const,
                      originName: findOriginName(child.name),
                      isDetailMode: true,
                      hiddenChildren: child.children.map((hidden) => ({
                        name: hidden.name,
                        display_name: hidden.title || hidden.name,
                        url: hidden.url,
                        icon: hidden.icon,
                        type: 'page' as const,
                      })),
                    };
                  }

                  return {
                    name: child.name,
                    display_name: child.title || child.name,
                    url: child.url,
                    icon: child.icon,
                    type: 'page' as const,
                    originName: findOriginName(child.name),
                  };
                }),
              },
            };
          } else {
            return {
              type: 'page' as const,
              id: menu.name,
              data: {
                name: menu.name,
                display_name: menu.title || menu.name,
                url: menu.url,
                icon: menu.icon,
                type: 'page' as const,
                originName: findOriginName(menu.name),
              },
            };
          }
        });

        setMixedItems(loadedMixedItems);

        const allPageNames: string[] = [];
        detail.menus.forEach((menu) => {
          const sourceMenu = findSourceMenu(menu.name);
          const isDetail = sourceMenu?.isDetailMode;

          if (isDetail) {
            if (menu.name) {
              allPageNames.push(menu.name);
            }
          } else {
            if (menu.children && Array.isArray(menu.children)) {
              menu.children.forEach((child) => {
                if (child.name) {
                  allPageNames.push(child.name);
                }
              });
            } else if (menu.name) {
              allPageNames.push(menu.name);
            }
          }
        });

        setSelectedKeys(allPageNames);
      }
    } catch (error) {
      console.error('Failed to load menu detail:', error);
      message.error(t('common.fetchFailed'));
    } finally {
      setDetailLoading(false);
    }
  }, [menuId, sourceMenus, getCustomMenuDetail, findOriginName, findSourceMenu, setMenuName, setMixedItems, setSelectedKeys, t]);

  return {
    detailLoading,
    loadMenuDetail,
  };
}

interface UseMenuSaveReturn {
  saveLoading: boolean;
  handleSaveMenu: () => Promise<void>;
}

export function useMenuSave(
  menuId: string,
  clientId: string,
  menuName: string,
  mixedItems: MixedItem[],
  t: (key: string) => string
): UseMenuSaveReturn {
  const { updateCustomMenu } = useRoleApi();
  const [saveLoading, setSaveLoading] = useState(false);

  const handleSaveMenu = useCallback(async () => {
    if (!menuId) {
      message.error(t('system.menu.menuIdRequired'));
      return;
    }

    if (!menuName.trim()) {
      message.error(t('system.menu.menuNameRequired'));
      return;
    }

    const menus = mixedItems.map((item) => {
      if (item.type === 'group') {
        const group = item.data as MenuGroup;
        return {
          title: group.name,
          name: group.name,
          icon: group.icon,
          children: group.children.map((child) => {
            if (child.isDetailMode && child.hiddenChildren) {
              return {
                title: child.display_name,
                name: child.name,
                url: child.url,
                icon: child.icon,
                ...(child.tour && { tour: child.tour }),
                hasDetail: true,
                children: child.hiddenChildren.map((hidden) => ({
                  title: hidden.display_name,
                  name: hidden.name,
                  url: hidden.url,
                  icon: hidden.icon,
                  ...(hidden.tour && { tour: hidden.tour }),
                })),
              };
            }
            return {
              title: child.display_name,
              name: child.name,
              url: child.url,
              icon: child.icon,
              ...(child.tour && { tour: child.tour }),
            };
          }),
        };
      } else {
        const page = item.data as FunctionMenuItem;

        if (page.isDetailMode && page.hiddenChildren) {
          return {
            title: page.display_name,
            name: page.name,
            url: page.url,
            icon: page.icon,
            ...(page.tour && { tour: page.tour }),
            hasDetail: true,
            children: page.hiddenChildren.map((child) => ({
              title: child.display_name,
              name: child.name,
              url: child.url,
              icon: child.icon,
              ...(child.tour && { tour: child.tour }),
            })),
          };
        }
        return {
          title: page.display_name,
          name: page.name,
          url: page.url,
          icon: page.icon,
          ...(page.tour && { tour: page.tour }),
        };
      }
    });

    setSaveLoading(true);
    try {
      await updateCustomMenu({
        id: menuId,
        app: clientId,
        display_name: menuName,
        menus: menus,
      });

      message.success(t('common.success'));
    } catch (error) {
      console.error('Failed to save menu:', error);
      message.error(t('common.failed'));
    } finally {
      setSaveLoading(false);
    }
  }, [menuId, clientId, menuName, mixedItems, updateCustomMenu, t]);

  return {
    saveLoading,
    handleSaveMenu,
  };
}

interface UseMenuNameEditReturn {
  menuName: string;
  isEditingName: boolean;
  tempMenuName: string;
  setMenuName: (name: string) => void;
  setTempMenuName: (name: string) => void;
  handleStartEditName: () => void;
  handleSaveNameEdit: () => void;
  handleCancelEditName: () => void;
}

export function useMenuNameEdit(): UseMenuNameEditReturn {
  const [menuName, setMenuName] = useState('');
  const [isEditingName, setIsEditingName] = useState(false);
  const [tempMenuName, setTempMenuName] = useState('');

  const handleStartEditName = useCallback(() => {
    setTempMenuName(menuName);
    setIsEditingName(true);
  }, [menuName]);

  const handleSaveNameEdit = useCallback(() => {
    if (tempMenuName.trim()) {
      setMenuName(tempMenuName.trim());
    }
    setTempMenuName('');
    setIsEditingName(false);
  }, [tempMenuName]);

  const handleCancelEditName = useCallback(() => {
    setTempMenuName('');
    setIsEditingName(false);
  }, []);

  return {
    menuName,
    isEditingName,
    tempMenuName,
    setMenuName,
    setTempMenuName,
    handleStartEditName,
    handleSaveNameEdit,
    handleCancelEditName,
  };
}
