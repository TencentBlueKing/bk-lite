'use client';

import React, { useState } from 'react';
import type { FunctionMenuItem } from '@/components/system-manager-application-menu/types';
import MenuPageItem from '@/components/system-manager-menu-page-item';

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
    <MenuPageItem
      page={page}
      tempName={tempName}
      setTempName={setTempName}
      isEditing={isEditing}
      onSaveEdit={handleSave}
      onCancelEdit={handleCancel}
      onStartEdit={handleStartEdit}
      onRemove={onRemove}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      draggable
      variant="card"
    />
  );
};

export default MenuPageCard;
