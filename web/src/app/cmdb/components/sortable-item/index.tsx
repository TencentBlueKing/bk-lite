'use client';

import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

export interface SortableItemProps {
  id: string;
  index: number;
  children: React.ReactNode;
  disabled?: boolean;
}

/**
 * 可排序列表项组件
 * 基于 @dnd-kit/sortable 实现拖拽排序
 * 
 * 使用说明：
 * - 子元素的第一个元素会被注入拖拽属性（作为拖拽手柄）
 * - 通常第一个子元素应该是 HolderOutlined 图标
 */
const SortableItem: React.FC<SortableItemProps> = ({
  id,
  index,
  children,
  disabled = false,
}) => {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id, disabled });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    marginTop: index ? 10 : 0,
    display: 'flex',
    width: '100%',
    minWidth: 0,
  };

  return (
    <li ref={setNodeRef} style={style}>
      {React.Children.map(children, (child, idx) =>
        idx === 0 && React.isValidElement(child)
          ? React.cloneElement(child, { ...attributes, ...listeners } as React.HTMLAttributes<HTMLElement>)
          : child
      )}
    </li>
  );
};

export default SortableItem;
