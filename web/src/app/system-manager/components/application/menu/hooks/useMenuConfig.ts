import { useState, useEffect } from 'react';
import type { SourceMenuNode, FunctionMenuItem } from '@/app/system-manager/types/menu';
import type { MenuItem } from '@/types/index';

export interface MenuGroup {
  id: string;
  name: string;
  icon?: string;
  children: FunctionMenuItem[];
}

export interface MixedItem {
  type: 'group' | 'page';
  id: string;
  data: MenuGroup | FunctionMenuItem;
}

/**
 * Check if menu is in detail page mode (hides children but preserves them in data)
 */
const isDetailPageMode = (menu: MenuItem): boolean => {
  return menu.hasDetail === true;
};

export const useMenuConfig = (
  configMenus: MenuItem[],
  clientId: string,
  menuId: string,
  t: (key: string) => string
) => {
  const [sourceMenus, setSourceMenus] = useState<SourceMenuNode[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [mixedItems, setMixedItems] = useState<MixedItem[]>([]);
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);

  useEffect(() => {
    if (configMenus.length > 0) {
      loadSourceMenusFromConfig();
    }
  }, [configMenus, clientId]);

  const loadSourceMenusFromConfig = () => {
    const appMenus = configMenus.filter(menu => {
      if (!menu.url || !clientId) return false;
      const urlParts = menu.url.split('/').filter(Boolean);
      const appName = urlParts[0];
      return appName === clientId;
    });

    const convertToSourceMenu = (menuItems: MenuItem[]): SourceMenuNode[] => {
      return menuItems
        .filter(menu => menu.url && menu.children && menu.children.length > 0)
        .map(menu => {
          const isDetail = isDetailPageMode(menu);
          
          // Detail mode: hide children in UI but preserve them in hiddenChildren for save
          if (isDetail) {
            return {
              name: menu.name,
              display_name: menu.display_name || menu.title || menu.name,
              url: menu.url,
              icon: menu.icon,
              type: 'menu' as const,
              tour: menu.tour,
              isDetailMode: true,
              hiddenChildren: menu.children
                ?.filter((child: MenuItem) => !child.isNotMenuItem && child.url)
                .map((child: MenuItem) => ({
                  name: child.name,
                  display_name: child.display_name || child.title || child.name,
                  url: child.url,
                  icon: child.icon,
                  type: 'page' as const,
                  tour: child.tour,
                })),
              children: []
            };
          }
          
          return {
            name: menu.name,
            display_name: menu.display_name || menu.title || menu.name,
            url: menu.url,
            icon: menu.icon,
            type: 'menu' as const,
            tour: menu.tour,
            isDetailMode: false,
            children: menu.children
              ?.filter((child: MenuItem) => !child.isNotMenuItem && child.url)
              .map((child: MenuItem) => ({
                name: child.name,
                display_name: child.display_name || child.title || child.name,
                url: child.url,
                icon: child.icon,
                type: 'page' as const,
                tour: child.tour,
              }))
          };
        })
        .filter(menu => menu.isDetailMode || (menu.children && menu.children.length > 0));
    };

    const sourceMenuData = convertToSourceMenu(appMenus);
    setSourceMenus(sourceMenuData);
  };

  const handleCheck = (checkedKeys: any) => {
    const newCheckedKeys = checkedKeys as string[];
    setSelectedKeys(newCheckedKeys);

    const addedKeys = newCheckedKeys.filter(key => !selectedKeys.includes(key));
    
    if (addedKeys.length > 0) {
      const newPages: FunctionMenuItem[] = [];
      
      sourceMenus.forEach(menu => {
        if (menu.isDetailMode && addedKeys.includes(menu.name)) {
          const exists = mixedItems.some(item => {
            if (item.type === 'page') {
              return (item.data as FunctionMenuItem).name === menu.name;
            } else if (item.type === 'group') {
              return (item.data as MenuGroup).children.some(c => c.name === menu.name);
            }
            return false;
          });
          
          if (!exists) {
            newPages.push({
              name: menu.name,
              display_name: menu.display_name,
              url: menu.url,
              icon: menu.icon,
              type: 'page',
              isExisting: false,
              originName: menu.display_name,
              tour: menu.tour,
              isDetailMode: true,
              hiddenChildren: menu.hiddenChildren,
            });
          }
        }
        
        if (!menu.isDetailMode) {
          menu.children?.forEach(child => {
            if (addedKeys.includes(child.name)) {
              const exists = mixedItems.some(item => {
                if (item.type === 'page') {
                  return (item.data as FunctionMenuItem).name === child.name;
                } else if (item.type === 'group') {
                  return (item.data as MenuGroup).children.some(c => c.name === child.name);
                }
                return false;
              });
              
              if (!exists) {
                newPages.push({
                  name: child.name,
                  display_name: child.display_name,
                  url: child.url,
                  icon: child.icon,
                  type: child.type,
                  isExisting: false,
                  originName: `${menu.display_name}/${child.display_name}`,
                  tour: child.tour,
                });
              }
            }
          });
        }
      });

      if (newPages.length > 0) {
        const newItems: MixedItem[] = newPages.map(page => ({
          type: 'page',
          id: page.name,
          data: page
        }));
        setMixedItems(prev => [...prev, ...newItems]);
      }
    }

    const removedKeys = selectedKeys.filter(key => !newCheckedKeys.includes(key));
    if (removedKeys.length > 0) {
      setMixedItems(prev => {
        return prev
          .map(item => {
            if (item.type === 'group') {
              const group = item.data as MenuGroup;
              const newChildren = group.children.filter(child => !removedKeys.includes(child.name));
              return {
                ...item,
                data: { ...group, children: newChildren }
              };
            }
            return item;
          })
          .filter(item => {
            if (item.type === 'page') {
              return !removedKeys.includes((item.data as FunctionMenuItem).name);
            }
            return true;
          });
      });
    }
  };

  const handleAddGroup = () => {
    const newGroup: MenuGroup = {
      id: `group_${Date.now()}`,
      name: t('system.menu.newGroup'),
      children: []
    };
    const newItem: MixedItem = {
      type: 'group',
      id: newGroup.id,
      data: newGroup
    };
    setMixedItems([...mixedItems, newItem]);
  };

  const handleDeleteGroup = (groupId: string) => {
    const item = mixedItems.find(i => i.id === groupId);
    if (item && item.type === 'group') {
      const group = item.data as MenuGroup;
      const pageNamesInGroup = group.children.map(page => page.name);
      
      setSelectedKeys(prev => prev.filter(key => !pageNamesInGroup.includes(key)));
      setMixedItems(prev => prev.filter(i => i.id !== groupId));
    }
  };

  const handleRenameGroup = (groupId: string, newName: string) => {
    setMixedItems(prev => prev.map(item => {
      if (item.type === 'group' && item.id === groupId) {
        return {
          ...item,
          data: { ...(item.data as MenuGroup), name: newName }
        };
      }
      return item;
    }));
  };

  const handleRemovePageFromGroup = (groupId: string, pageName: string) => {
    setSelectedKeys(prev => prev.filter(k => k !== pageName));
    
    setMixedItems(prev => prev.map(item => {
      if (item.type === 'group' && item.id === groupId) {
        const group = item.data as MenuGroup;
        const newGroup = {
          ...group,
          children: group.children.filter(c => c.name !== pageName)
        };
        return { ...item, data: newGroup };
      }
      return item;
    }));
  };

  const handleRemoveUngroupedPage = (pageName: string) => {
    setMixedItems(prev => prev.filter(item => item.id !== pageName));
    setSelectedKeys(prev => prev.filter(k => k !== pageName));
  };

  const handleRenameUngroupedPage = (pageName: string, newDisplayName: string) => {
    setMixedItems(prev => prev.map(item => {
      if (item.type === 'page' && item.id === pageName) {
        return {
          ...item,
          data: {
            ...(item.data as FunctionMenuItem),
            display_name: newDisplayName,
          }
        };
      }
      return item;
    }));
  };

  const handleRenamePageInGroup = (groupId: string, pageName: string, newDisplayName: string) => {
    setMixedItems(prev => prev.map(item => {
      if (item.type === 'group' && item.id === groupId) {
        const group = item.data as MenuGroup;
        const newChildren = group.children.map(child => 
          child.name === pageName ? { ...child, display_name: newDisplayName } : child
        );
        const newGroup = { ...group, children: newChildren };
        return { ...item, data: newGroup };
      }
      return item;
    }));
  };

  return {
    sourceMenus,
    selectedKeys,
    mixedItems,
    editingGroupId,
    setMixedItems,
    setSelectedKeys,
    setEditingGroupId,
    handleCheck,
    handleAddGroup,
    handleDeleteGroup,
    handleRenameGroup,
    handleRemovePageFromGroup,
    handleRemoveUngroupedPage,
    handleRenameUngroupedPage,
    handleRenamePageInGroup,
  };
};
