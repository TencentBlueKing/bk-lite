'use client';

import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { Button, Input, Skeleton } from 'antd';
import { PlusOutlined, EditOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useMenus } from '@/context/menus';
import type { FunctionMenuItem } from '@/app/system-manager/types/menu';
import SourceMenuTree from '@/app/system-manager/components/application/menu/sourceTree';
import MenuGroupCard from '@/app/system-manager/components/application/menu/groupCard';
import MenuPageCard from '@/app/system-manager/components/application/menu/pageCard';
import { useMenuConfig, type MenuGroup } from '@/app/system-manager/components/application/menu/hooks/useMenuConfig';
import { useDragDrop } from '@/app/system-manager/components/application/menu/hooks/useDragDrop';
import { useMenuDetailLoader, useMenuSave, useMenuNameEdit } from '@/app/system-manager/components/application/menu/hooks/useMenuConfigPage';

const MenuConfigPage = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const clientId = searchParams.get('clientId') || '';
  const menuId = searchParams.get('menuId') || '';

  const { configMenus, loading: menusLoading } = useMenus();
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

  const {
    menuName,
    isEditingName,
    tempMenuName,
    setMenuName,
    setTempMenuName,
    handleStartEditName,
    handleSaveNameEdit,
    handleCancelEditName,
  } = useMenuNameEdit();

  const { detailLoading, loadMenuDetail } = useMenuDetailLoader(
    menuId,
    sourceMenus,
    setMenuName,
    setMixedItems,
    setSelectedKeys,
    t
  );

  const { saveLoading, handleSaveMenu } = useMenuSave(menuId, clientId, menuName, mixedItems, t);

  useEffect(() => {
    loadMenuDetail();
  }, [menuId, sourceMenus]);

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
            <Button size="small" icon={<PlusOutlined />} onClick={handleAddGroup}>
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
                    <div
                      className="absolute -top-1.5 left-0 right-0 flex items-center pointer-events-none"
                      style={{ zIndex: 10 }}
                    >
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
                        onPageDragStart={(e, pageIndex, page) =>
                          handleDragStart(e, 'groupChild', { groupId: item.id, pageIndex, ...page })
                        }
                        onPageDragOver={(e, pageIndex) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setDragOverPageIndex({ groupId: item.id, pageIndex });
                        }}
                        onPageDrop={(e, pageIndex) => {
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
                        onRename={(newName) =>
                          handleRenameUngroupedPage((item.data as FunctionMenuItem).name, newName)
                        }
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
