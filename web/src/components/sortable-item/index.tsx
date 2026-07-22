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
    position: 'relative',
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
