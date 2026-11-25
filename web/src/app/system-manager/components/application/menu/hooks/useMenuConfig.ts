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

const toSourcePage = (menu: MenuItem, isNotMenuItem?: boolean): SourceMenuNode => ({
  name: menu.name,
  display_name: menu.display_name || menu.title || menu.name,
  url: menu.url,
  icon: menu.icon,
  type: 'page',
  tour: menu.tour,
  ...(isNotMenuItem ? { isNotMenuItem: true } : {}),
});

const visiblePages = (menu: MenuItem) =>
  (menu.children || []).filter((child) => !child.isNotMenuItem && child.url);

/**
 * Pages shown in the custom-menu source picker.
 * A visible top-level page stays selectable even when it has no visible children.
 * Hidden entries (isNotMenuItem) stay out.
 */
export const buildSourceMenus = (configMenus: MenuItem[], clientId: string): SourceMenuNode[] => {
  const appMenus = configMenus.filter((menu) => {
    if (!menu.url || !clientId || menu.isNotMenuItem) return false;
    const appName = menu.url.split('/').filter(Boolean)[0];
    return appName === clientId;
  });

  return appMenus.flatMap((menu): SourceMenuNode[] => {
    const base = {
      name: menu.name,
      display_name: menu.display_name || menu.title || menu.name,
      url: menu.url,
      icon: menu.icon,
      type: 'menu' as const,
      tour: menu.tour,
    };
    if (isDetailPageMode(menu)) {
      return [{
        ...base,
        isDetailMode: true,
        sourceHasDetail: true,
        hiddenChildren: visiblePages(menu).map((child) => toSourcePage(child)),
        children: [],
      }];
    }
    const visible = visiblePages(menu);
    if (visible.length > 0) {
      return [{
        ...base,
        isDetailMode: false,
        children: visible.map((child) => toSourcePage(child)),
      }];
    }
    const hidden = (menu.children || []).filter((child) => child.url);
    return [{
      ...base,
      isDetailMode: true,
      sourceHasDetail: false,
      hiddenChildren: hidden.map((child) => toSourcePage(child, child.isNotMenuItem)),
      children: [],
    }];
  });
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
    setSourceMenus(buildSourceMenus(configMenus, clientId));
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
              sourceHasDetail: menu.sourceHasDetail,
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
