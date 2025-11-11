'use client';

import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { Button, Input, message, Skeleton } from 'antd';
import { PlusOutlined, EditOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useMenus } from '@/context/menus';
import { useRoleApi } from '@/app/system-manager/api/application';
import type { FunctionMenuItem } from '@/app/system-manager/types/menu';
import SourceMenuTree from '@/app/system-manager/components/application/menu/sourceTree';
import MenuGroupCard from '@/app/system-manager/components/application/menu/groupCard';
import MenuPageCard from '@/app/system-manager/components/application/menu/pageCard';
import { useMenuConfig } from '@/app/system-manager/components/application/menu/hooks/useMenuConfig';
import { useDragDrop, type MenuGroup } from '@/app/system-manager/components/application/menu/hooks/useDragDrop';

const MenuConfigPage = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const clientId = searchParams.get('clientId') || '';
  const menuId = searchParams.get('menuId') || '';
  
  const { configMenus, loading: menusLoading } = useMenus();
  const { updateCustomMenu, getCustomMenuDetail } = useRoleApi();

  const [menuName, setMenuName] = useState('');
  const [isEditingName, setIsEditingName] = useState(false);
  const [tempMenuName, setTempMenuName] = useState('');
  const [saveLoading, setSaveLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [dragOverPageIndex, setDragOverPageIndex] = useState<{ groupId: string; pageIndex: number } | null>(null);

  const {
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
  } = useMenuConfig(configMenus, clientId, menuId, t);

  const {
    dragOverIndex,
    isDragging,
    handleDragStart,
    handleDragOver,
    handleDragEnd,
    handleDropToMixedList,
    handleDropToGroup,
  } = useDragDrop(mixedItems, setMixedItems, t);

  useEffect(() => {
    const loadMenuDetail = async () => {
      if (!menuId || sourceMenus.length === 0) return;
      
      setDetailLoading(true);
      try {
        const detail = await getCustomMenuDetail({ id: menuId });
        
        if (detail.display_name) {
          setMenuName(detail.display_name);
        }
        
        if (detail.menus && Array.isArray(detail.menus)) {
          const findOriginName = (pageName: string): string | undefined => {
            for (const menu of sourceMenus) {
              const child = menu.children?.find(c => c.name === pageName);
              if (child) {
                return `${menu.display_name}/${child.display_name}`;
              }
            }
            return undefined;
          };

          // 检查菜单是否为详情页模式
          const findSourceMenu = (menuName: string) => {
            return sourceMenus.find(m => m.name === menuName);
          };

          const loadedMixedItems = detail.menus.map((menu: any, index: number) => {
            // 检查是否为详情页模式
            const sourceMenu = findSourceMenu(menu.name);
            const isDetail = sourceMenu?.isDetailMode;
            
            // 如果是详情页模式且有子菜单，不展示，只保存父级
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
                  hiddenChildren: menu.children.map((child: any) => ({
                    name: child.name,
                    display_name: child.title || child.name,
                    url: child.url,
                    icon: child.icon,
                    type: 'page' as const,
                  })), // 使用保存的子菜单数据
                }
              };
            }
            
            // 普通目录模式
            if (menu.children && Array.isArray(menu.children)) {
              return {
                type: 'group' as const,
                id: `group-${index}`,
                data: {
                  id: `group-${index}`,
                  name: menu.title || menu.name,
                  icon: menu.icon,
                  children: menu.children.map((child: any) => {
                    // 检查子页面是否也是详情页模式
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
                        hiddenChildren: child.children.map((hidden: any) => ({
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
                  })
                }
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
                }
              };
            }
          });
          
          setMixedItems(loadedMixedItems);
          
          const allPageNames: string[] = [];
          detail.menus.forEach((menu: any) => {
            const sourceMenu = findSourceMenu(menu.name);
            const isDetail = sourceMenu?.isDetailMode;
            
            // 如果是详情页模式，只选中父级
            if (isDetail) {
              if (menu.name) {
                allPageNames.push(menu.name);
              }
            } else {
              // 普通模式，选中所有子菜单
              if (menu.children && Array.isArray(menu.children)) {
                menu.children.forEach((child: any) => {
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
    };
    
    loadMenuDetail();
  }, [menuId, sourceMenus]);

  const handleStartEditName = () => {
    setTempMenuName(menuName);
    setIsEditingName(true);
  };

  const handleSaveNameEdit = () => {
    if (tempMenuName.trim()) {
      setMenuName(tempMenuName.trim());
    }
    setTempMenuName('');
    setIsEditingName(false);
  };

  const handleCancelEditName = () => {
    setTempMenuName('');
    setIsEditingName(false);
  };

  const handleSaveMenu = async () => {
    if (!menuId) {
      message.error(t('system.menu.menuIdRequired'));
      return;
    }

    const finalMenuName = menuName;
    if (!finalMenuName.trim()) {
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
          children: group.children.map(child => {
            // 如果是详情页模式，需要展开保存隐藏的子菜单
            if (child.isDetailMode && child.hiddenChildren) {
              return {
                title: child.display_name,
                name: child.name,
                url: child.url,
                icon: child.icon,
                ...(child.tour && { tour: child.tour }),
                hasDetail: true,
                children: child.hiddenChildren.map(hidden => ({
                  title: hidden.display_name,
                  name: hidden.name,
                  url: hidden.url,
                  icon: hidden.icon,
                  ...(hidden.tour && { tour: hidden.tour }),
                }))
              };
            }
            return {
              title: child.display_name,
              name: child.name,
              url: child.url,
              icon: child.icon,
              ...(child.tour && { tour: child.tour }),
            };
          })
        };
      } else {
        const page = item.data as FunctionMenuItem;
        
        // 如果是详情页模式，保存时需要包含隐藏的子菜单
        if (page.isDetailMode && page.hiddenChildren) {
          return {
            title: page.display_name,
            name: page.name,
            url: page.url,
            icon: page.icon,
            ...(page.tour && { tour: page.tour }),
            hasDetail: true,
            children: page.hiddenChildren.map(child => ({
              title: child.display_name,
              name: child.name,
              url: child.url,
              icon: child.icon,
              ...(child.tour && { tour: child.tour }),
            }))
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
        display_name: finalMenuName,
        menus: menus,
      });
      
      message.success(t('common.success'));
    } catch (error) {
      console.error('Failed to save menu:', error);
      message.error(t('common.failed'));
    } finally {
      setSaveLoading(false);
    }
  };

  return (
    <div className="flex w-full gap-4" style={{ height: 'calc(100vh - 185px)' }}>
      <SourceMenuTree
        sourceMenus={sourceMenus}
        selectedKeys={selectedKeys}
        loading={menusLoading}
        disabled={detailLoading}
        onCheck={handleCheck}
      />

      <div className="flex-1 bg-[var(--color-bg)] rounded-lg overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-[var(--color-border-2)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isEditingName ? (
              <>
                <Input
                  autoFocus
                  value={tempMenuName}
                  onChange={(e) => setTempMenuName(e.target.value)}
                  onPressEnter={handleSaveNameEdit}
                  onBlur={handleSaveNameEdit}
                  placeholder={t('system.menu.menuName')}
                  className="w-48"
                  size="small"
                />
                <Button
                  size="small"
                  type="text"
                  icon={<CloseOutlined style={{ fontSize: '12px' }} />}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleCancelEditName();
                  }}
                  className="text-[var(--color-text-3)] hover:text-[var(--color-text-2)]"
                  style={{ padding: '0 4px', minWidth: '24px', height: '24px' }}
                />
              </>
            ) : (
              <>
                <h3 className="m-0 text-sm font-medium">{menuName}</h3>
                <Button
                  size="small"
                  type="text"
                  icon={<EditOutlined style={{ fontSize: '12px' }} />}
                  onClick={handleStartEditName}
                  className="text-[var(--color-text-3)] hover:text-[var(--color-text-2)]"
                  style={{ padding: '0 4px', minWidth: '24px', height: '24px' }}
                />
              </>
            )}
          </div>
          <div className="flex gap-2">
            <Button 
              type="primary" 
              size="small"
              icon={<SaveOutlined />}
              onClick={handleSaveMenu}
              loading={saveLoading}
            >
              {t('common.save')}
            </Button>
            <Button 
              size="small"
              icon={<PlusOutlined />}
              onClick={handleAddGroup}
            >
              {t('system.menu.addGroup')}
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {detailLoading ? (
            <div className="flex flex-col gap-3">
              <Skeleton active paragraph={{ rows: 3 }} />
              <Skeleton active paragraph={{ rows: 3 }} />
              <Skeleton active paragraph={{ rows: 2 }} />
            </div>
          ) : mixedItems.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[var(--color-text-3)] text-sm">
              {t('system.menu.emptyGroup')}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {mixedItems.map((item, index) => (
                <div key={item.id} className="relative">
                  <div
                    onDragOver={(e) => handleDragOver(e, index)}
                    onDrop={(e) => {
                      e.stopPropagation();
                      handleDropToMixedList(e, index);
                    }}
                    className="absolute -top-4 left-0 right-0 h-8"
                    style={{ zIndex: 5 }}
                  />
                  
                  {isDragging && dragOverIndex === index && (
                    <div className="absolute -top-1.5 left-0 right-0 flex items-center pointer-events-none" style={{ zIndex: 10 }}>
                      <div className="flex-1 h-0.5 bg-[var(--color-primary-6)] relative">
                        <div className="absolute left-0 top-1/2 w-1.5 h-1.5 bg-[var(--color-primary-6)] rounded-full transform -translate-y-1/2" />
                        <div className="absolute right-0 top-1/2 w-1.5 h-1.5 bg-[var(--color-primary-6)] rounded-full transform -translate-y-1/2" />
                      </div>
                    </div>
                  )}
                  
                  <div>
                    {item.type === 'group' ? (
                      <MenuGroupCard
                        group={item.data as MenuGroup}
                        isEditing={editingGroupId === item.id}
                        onDragStart={(e) => handleDragStart(e, 'group', item.data)}
                        onDragEnd={() => {
                          handleDragEnd();
                          setDragOverPageIndex(null);
                        }}
                        onRename={(name) => handleRenameGroup(item.id, name)}
                        onEdit={() => setEditingGroupId(item.id)}
                        onDelete={() => handleDeleteGroup(item.id)}
                        onCancelEdit={() => setEditingGroupId(null)}
                        onDropToGroup={(e) => {
                          handleDropToGroup(e, item.id);
                          setDragOverPageIndex(null);
                        }}
                        onRemovePage={(pageName) => handleRemovePageFromGroup(item.id, pageName)}
                        onRenamePage={(pageName, newName) => handleRenamePageInGroup(item.id, pageName, newName)}
                        onPageDragStart={(e, pageIndex, page) => handleDragStart(e, 'groupChild', { groupId: item.id, pageIndex, ...page })}
                        onPageDragOver={(e, pageIndex) => {
                          e.preventDefault();
                          e.stopPropagation();
                          console.log('页面 DragOver:', pageIndex);
                          setDragOverPageIndex({ groupId: item.id, pageIndex });
                        }}
                        onPageDrop={(e, pageIndex) => {
                          console.log('页面 Drop 事件触发, pageIndex:', pageIndex, 'groupId:', item.id);
                          e.preventDefault();
                          e.stopPropagation();
                          handleDropToGroup(e, item.id, pageIndex);
                          setDragOverPageIndex(null);
                        }}
                        isDragging={isDragging}
                        dragOverPageIndex={dragOverPageIndex?.groupId === item.id ? dragOverPageIndex.pageIndex : null}
                      />
                    ) : (
                      <MenuPageCard
                        page={item.data as FunctionMenuItem}
                        onDragStart={(e) => handleDragStart(e, 'page', item.data)}
                        onDragEnd={handleDragEnd}
                        onRemove={() => handleRemoveUngroupedPage((item.data as FunctionMenuItem).name)}
                        onRename={(newName) => handleRenameUngroupedPage((item.data as FunctionMenuItem).name, newName)}
                      />
                    )}
                  </div>
                </div>
              ))}
              
              <div
                onDragOver={(e) => handleDragOver(e, mixedItems.length)}
                onDrop={(e) => {
                  e.stopPropagation();
                  handleDropToMixedList(e, mixedItems.length);
                }}
                className="h-12 relative"
              >
                {isDragging && dragOverIndex === mixedItems.length && (
                  <div className="absolute top-0 left-0 right-0 flex items-center pointer-events-none">
                    <div className="flex-1 h-0.5 bg-[var(--color-primary-6)] relative">
                      <div className="absolute left-0 top-1/2 w-1.5 h-1.5 bg-[var(--color-primary-6)] rounded-full transform -translate-y-1/2" />
                      <div className="absolute right-0 top-1/2 w-1.5 h-1.5 bg-[var(--color-primary-6)] rounded-full transform -translate-y-1/2" />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MenuConfigPage;
