import React, { useState, useEffect, ReactNode } from 'react';
import {
  CaretRightOutlined,
  CaretDownOutlined,
  HolderOutlined,
} from '@ant-design/icons';

interface AccordionProps {
  title: string;
  children: ReactNode;
  className?: string;
  titleClassName?: string;
  contentClassName?: string;
  isOpen?: boolean;
  icon?: JSX.Element;
  sortable?: boolean;
  onToggle?: (isOpen: boolean) => void;
  onDragStart?: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragOver?: (e: React.DragEvent<HTMLDivElement>) => void;
  onDrop?: (e: React.DragEvent<HTMLDivElement>) => void;
}

const Collapse: React.FC<AccordionProps> = ({
  title,
  children,
  isOpen = true,
  icon,
  className = '',
  titleClassName = '',
  contentClassName = '',
  sortable = false,
  onToggle,
  onDragStart,
  onDragOver,
  onDrop,
}) => {
  const [open, setOpen] = useState(isOpen);
  const collapseClass = `text-[12px] ${className}`;

  useEffect(() => {
    setOpen(isOpen);
  }, [isOpen]);

  const toggleAccordion = () => {
    const newOpenState = !open;
    setOpen(newOpenState);
    if (onToggle) {
      onToggle(newOpenState);
    }
  };

  return (
    <div
      className={collapseClass}
      draggable={sortable}
      onDragStart={sortable ? onDragStart : undefined}
      onDragOver={sortable ? onDragOver : undefined}
      onDrop={sortable ? onDrop : undefined}
    >
      <div
        className={`flex justify-between items-center p-[10px] bg-[var(--color-fill-1)] cursor-pointer collapse-title ${titleClassName}`}
        onClick={toggleAccordion}
      >
        <div className="flex items-center">
          {sortable && (
            <HolderOutlined className="font-[800] text-[16px] mr-[6px] cursor-move" />
          )}
          <span className="text-[var(--color-text-3)] mr-[6px]">
            {open ? <CaretDownOutlined /> : <CaretRightOutlined />}
          </span>
          <span className="font-semibold text-[14px] title">{title}</span>
        </div>
        {icon && (
          <div
            className="ml-[6px] text-[14px]"
            onClick={(e) => e.stopPropagation()}
          >
            {icon}
          </div>
        )}
      </div>
      {open && (
        <div className={`py-[10px] collapse-content ${contentClassName}`}>
          {children}
        </div>
      )}
    </div>
  );
};

export default Collapse;
