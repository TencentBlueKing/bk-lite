'use client';

import React, { useState } from 'react';
import { Button, Input } from 'antd';
import { FileOutlined, DeleteOutlined, EditOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import type { FunctionMenuItem } from '@/app/system-manager/types/menu';

interface MenuPageCardProps {
  page: FunctionMenuItem;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onRemove: () => void;
  onRename?: (newName: string) => void;
}

const MenuPageCard: React.FC<MenuPageCardProps> = ({
  page,
  onDragStart,
  onDragEnd,
  onRemove,
  onRename,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [tempName, setTempName] = useState('');

  const handleStartEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setTempName(page.display_name);
    setIsEditing(true);
  };

  const handleSave = () => {
    if (tempName.trim() && tempName !== page.display_name) {
      onRename?.(tempName.trim());
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setTempName('');
    setIsEditing(false);
  };

  return (
    <div
      draggable={!isEditing}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className="flex items-center justify-between px-3 py-2 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded hover:bg-[var(--color-bg-1)] hover:border-[var(--color-primary-6)] transition-all group overflow-hidden"
      style={{ cursor: isEditing ? 'default' : 'move' }}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {page.icon ? <Icon type={page.icon} className="flex-shrink-0" /> : <FileOutlined className="text-[var(--color-text-3)] flex-shrink-0" />}
        
        {isEditing ? (
          <div className="flex items-center gap-1 flex-1">
            <Input
              value={tempName}
              onChange={(e) => setTempName(e.target.value)}
              onPressEnter={handleSave}
              size="small"
              className="flex-1"
              autoFocus
            />
            <Button
              type="text"
              size="small"
              icon={<CheckOutlined />}
              onClick={handleSave}
              className="text-green-500"
            />
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined />}
              onClick={handleCancel}
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
              onClick={handleStartEdit}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-3)] hover:text-[var(--color-text-2)]"
              style={{ padding: '0 4px', minWidth: '24px', height: '24px' }}
            />
          </>
        )}
      </div>
      
      {!isEditing && (
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={onRemove}
          className="opacity-0 group-hover:opacity-100 transition-opacity"
        />
      )}
    </div>
  );
};

export default MenuPageCard;
