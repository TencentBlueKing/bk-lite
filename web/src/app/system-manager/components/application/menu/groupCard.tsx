'use client';

import React, { useState } from 'react';
import { Button, Input } from 'antd';
import { FolderOutlined, FileOutlined, EditOutlined, DeleteOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import type { FunctionMenuItem } from '@/app/system-manager/types/menu';

interface MenuGroup {
  id: string;
  name: string;
  icon?: string;
  children: FunctionMenuItem[];
}

interface MenuGroupCardProps {
  group: MenuGroup;
  isEditing: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onRename: (name: string) => void;
  onEdit: () => void;
  onDelete: () => void;
  onCancelEdit: () => void;
  onDropToGroup: (e: React.DragEvent) => void;
  onRemovePage: (pageName: string) => void;
  onRenamePage?: (pageName: string, newDisplayName: string) => void;
  onPageDragStart: (e: React.DragEvent, pageIndex: number, page: FunctionMenuItem) => void;
  onPageDragOver: (e: React.DragEvent, pageIndex: number) => void;
  onPageDrop: (e: React.DragEvent, pageIndex: number) => void;
  isDragging?: boolean;
  dragOverPageIndex?: number | null;
}

const MenuGroupCard: React.FC<MenuGroupCardProps> = ({
  group,
  isEditing,
  onDragStart,
  onDragEnd,
  onRename,
  onEdit,
  onDelete,
  onCancelEdit,
  onDropToGroup,
  onRemovePage,
  onRenamePage,
  onPageDragStart,
  onPageDragOver,
  onPageDrop,
  isDragging = false,
  dragOverPageIndex = null,
}) => {
  const { t } = useTranslation();
  const [editingPageName, setEditingPageName] = useState<string | null>(null);
  const [tempPageName, setTempPageName] = useState('');
  const [tempGroupName, setTempGroupName] = useState('');

  const handleStartEditPage = (page: FunctionMenuItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setTempPageName(page.display_name);
    setEditingPageName(page.name);
  };

  const handleSavePageName = (pageName: string) => {
    if (tempPageName.trim() && onRenamePage) {
      onRenamePage(pageName, tempPageName.trim());
    }
    setEditingPageName(null);
  };

  const handleCancelEditPage = () => {
    setTempPageName('');
    setEditingPageName(null);
  };

  const handleStartEditGroup = (e: React.MouseEvent) => {
    e.stopPropagation();
    setTempGroupName(group.name);
    onEdit();
  };

  const handleSaveGroupName = () => {
    if (tempGroupName.trim()) {
      onRename(tempGroupName.trim());
    }
    onCancelEdit();
  };

  return (
    <div className="border border-[var(--color-border-2)] rounded-lg overflow-hidden relative transition-all group-card">
      {/* 目录头部 */}
      <div className="bg-[var(--color-fill-1)] px-4 py-2 border-b border-[var(--color-border-2)] flex items-center justify-between hover:bg-[var(--color-fill-2)] transition-colors group">
        <div 
          draggable={!isEditing}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          className="flex items-center gap-2 flex-1"
          style={{ cursor: isEditing ? 'default' : 'move' }}
        >
          <FolderOutlined className="text-[var(--color-primary-6)]" />
          {isEditing ? (
            <div className="flex items-center gap-1 flex-1">
              <Input
                size="small"
                value={tempGroupName}
                onChange={(e) => setTempGroupName(e.target.value)}
                onPressEnter={handleSaveGroupName}
                autoFocus
                className="flex-1 max-w-[300px]"
              />
              <Button
                type="text"
                size="small"
                icon={<CheckOutlined />}
                onClick={handleSaveGroupName}
                className="text-green-500"
              />
              <Button
                type="text"
                size="small"
                icon={<CloseOutlined />}
                onClick={onCancelEdit}
              />
            </div>
          ) : (
            <>
              <span className="font-medium">{group.name}</span>
              <Button
                type="text"
                size="small"
                icon={<EditOutlined style={{ fontSize: '12px' }} />}
                onClick={handleStartEditGroup}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-3)] hover:text-[var(--color-text-2)]"
                style={{ padding: '0 4px', minWidth: '24px', height: '24px' }}
              />
            </>
          )}
        </div>
        {!isEditing && (
          <div className="flex items-center gap-1">
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="opacity-0 group-hover:opacity-100 transition-opacity"
            />
          </div>
        )}
      </div>

      {/* 目录内容 */}
      <div 
        className="p-2"
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          // 拖到空白区域时，添加到末尾（不传 index）
          onDropToGroup(e);
        }}
      >
        {group.children.length === 0 ? (
          <div className="text-center py-4 text-[var(--color-text-3)] text-xs">
            {t('system.menu.emptyPages')}
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {group.children.map((page, pageIndex) => (
              <div key={page.name} className="relative">
                {/* 拖拽插入指示线 */}
                {isDragging && dragOverPageIndex === pageIndex && (
                  <div className="absolute -top-1 left-0 right-0 flex items-center pointer-events-none" style={{ zIndex: 10 }}>
                    <div className="flex-1 h-0.5 bg-[var(--color-primary-6)] relative">
                      <div className="absolute left-0 top-1/2 w-1.5 h-1.5 bg-[var(--color-primary-6)] rounded-full transform -translate-y-1/2" />
                      <div className="absolute right-0 top-1/2 w-1.5 h-1.5 bg-[var(--color-primary-6)] rounded-full transform -translate-y-1/2" />
                    </div>
                  </div>
                )}
                
                <div
                  draggable={editingPageName !== page.name}
                  onDragStart={(e) => {
                    console.log('页面开始拖拽:', page.display_name, 'index:', pageIndex);
                    onPageDragStart(e, pageIndex, page);
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onPageDragOver(e, pageIndex);
                  }}
                  onDrop={(e) => {
                    console.log('groupCard 内部 onDrop 触发, pageIndex:', pageIndex);
                    e.preventDefault();
                    e.stopPropagation();
                    onPageDrop(e, pageIndex);
                  }}
                  className="flex items-center justify-between px-3 py-2 bg-[var(--color-bg-1)] rounded hover:bg-[var(--color-fill-1)] transition-all group overflow-hidden"
                  style={{ cursor: editingPageName === page.name ? 'default' : 'move' }}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    {page.icon ? <Icon type={page.icon} className="flex-shrink-0" /> : <FileOutlined className="text-[var(--color-text-3)] flex-shrink-0" />}
                    
                    {editingPageName === page.name ? (
                      <div className="flex items-center gap-1 flex-1">
                        <Input
                          value={tempPageName}
                          onChange={(e) => setTempPageName(e.target.value)}
                          onPressEnter={() => handleSavePageName(page.name)}
                          size="small"
                          className="flex-1"
                          autoFocus
                        />
                        <Button
                          type="text"
                          size="small"
                          icon={<CheckOutlined />}
                          onClick={() => handleSavePageName(page.name)}
                          className="text-green-500"
                        />
                        <Button
                          type="text"
                          size="small"
                          icon={<CloseOutlined />}
                          onClick={handleCancelEditPage}
                        />
                      </div>
                    ) : (
                      <>
                        <span className="text-sm truncate">{page.display_name}</span>
                        {page.originName && (
                          <span className="text-xs text-[var(--color-text-3)] truncate">({page.originName})</span>
                        )}
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined style={{ fontSize: '12px' }} />}
                          onClick={(e) => handleStartEditPage(page, e)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-3)] hover:text-[var(--color-text-2)]"
                          style={{ padding: '0 4px', minWidth: '24px', height: '24px' }}
                        />
                      </>
                    )}
                  </div>
                  
                  {editingPageName !== page.name && (
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => onRemovePage(page.name)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default MenuGroupCard;
