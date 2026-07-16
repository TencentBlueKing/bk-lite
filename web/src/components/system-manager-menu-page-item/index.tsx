'use client';

import React from 'react';
import { Button, Input } from 'antd';
import {
  FileOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import Icon from '@/components/icon';
import type { FunctionMenuItem } from '@/components/system-manager-application-menu/types';

interface MenuPageItemProps {
  draggable?: boolean;
  draggingCursor?: string;
  editable?: boolean;
  isEditing: boolean;
  onCancelEdit: () => void;
  onDragEnd?: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragOver?: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragStart?: (e: React.DragEvent<HTMLDivElement>) => void;
  onDrop?: (e: React.DragEvent<HTMLDivElement>) => void;
  onRemove?: () => void;
  onSaveEdit: () => void;
  onStartEdit?: (e: React.MouseEvent) => void;
  page: FunctionMenuItem;
  tempName: string;
  setTempName: (value: string) => void;
  variant?: 'card' | 'group';
}

const MenuPageItem: React.FC<MenuPageItemProps> = ({
  draggable = false,
  draggingCursor = 'move',
  editable = true,
  isEditing,
  onCancelEdit,
  onDragEnd,
  onDragOver,
  onDragStart,
  onDrop,
  onRemove,
  onSaveEdit,
  onStartEdit,
  page,
  tempName,
  setTempName,
  variant = 'card',
}) => {
  const shellClassName =
    variant === 'group'
      ? 'flex items-center justify-between px-3 py-2 bg-[var(--color-bg-1)] rounded hover:bg-[var(--color-fill-1)] transition-all group overflow-hidden'
      : 'flex items-center justify-between px-3 py-2 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded hover:bg-[var(--color-bg-1)] hover:border-[var(--color-primary-6)] transition-all group overflow-hidden';

  return (
    <div
      draggable={draggable && !isEditing}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className={shellClassName}
      style={{ cursor: isEditing ? 'default' : draggingCursor }}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {page.icon ? (
          <Icon type={page.icon} className="flex-shrink-0" />
        ) : (
          <FileOutlined className="text-[var(--color-text-3)] flex-shrink-0" />
        )}

        {isEditing ? (
          <div className="flex items-center gap-1 flex-1">
            <Input
              value={tempName}
              onChange={(e) => setTempName(e.target.value)}
              onPressEnter={onSaveEdit}
              size="small"
              className="flex-1"
              autoFocus
            />
            <Button
              type="text"
              size="small"
              icon={<CheckOutlined />}
              onClick={onSaveEdit}
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
            <span className="text-sm truncate">{page.display_name}</span>
            {page.originName ? (
              <span className="text-xs text-[var(--color-text-3)] truncate">
                ({page.originName})
              </span>
            ) : null}
            {editable ? (
              <Button
                type="text"
                size="small"
                icon={<EditOutlined style={{ fontSize: '12px' }} />}
                onClick={onStartEdit}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-3)] hover:text-[var(--color-text-2)]"
                style={{ padding: '0 4px', minWidth: '24px', height: '24px' }}
              />
            ) : null}
          </>
        )}
      </div>

      {!isEditing && onRemove ? (
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={onRemove}
          className="opacity-0 group-hover:opacity-100 transition-opacity"
        />
      ) : null}
    </div>
  );
};

export default MenuPageItem;
