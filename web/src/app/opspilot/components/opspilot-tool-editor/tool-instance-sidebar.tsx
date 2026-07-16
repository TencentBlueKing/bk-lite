'use client';

import React, { useEffect, useRef } from 'react';
import { DeleteOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import SectionHeader from '@/components/section-header';
import ToolEditorEmptyState from './tool-editor-empty-state';

export interface ToolInstanceSidebarItem {
  id: string;
  title: string;
  description: string;
}

export interface ToolInstanceSidebarProps {
  title: string;
  addLabel: string;
  emptyDescription: string;
  items: ToolInstanceSidebarItem[];
  selectedId: string | null;
  onAdd: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  selectedVariant?: 'default' | 'strong';
}

const ToolInstanceSidebar: React.FC<ToolInstanceSidebarProps> = ({
  title,
  addLabel,
  emptyDescription,
  items,
  selectedId,
  onAdd,
  onSelect,
  onDelete,
  selectedVariant = 'default',
}) => {
  const listRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(items.length);

  useEffect(() => {
    if (items.length > prevLengthRef.current && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
    prevLengthRef.current = items.length;
  }, [items.length]);

  const getItemClassName = (isActive: boolean) => {
    const activeClassName =
      selectedVariant === 'strong'
        ? 'border-2 border-[var(--color-primary)] bg-[var(--color-primary-bg)]'
        : 'border border-[var(--color-primary)] bg-[var(--color-primary-bg)]';

    return `w-full rounded p-3 text-left transition ${
      isActive
        ? activeClassName
        : 'border border-[var(--color-border)] bg-[var(--color-bg-1)]'
    }`;
  };

  return (
    <div className="flex w-[260px] flex-col rounded border border-[var(--color-border)] p-3">
      <SectionHeader
        className="mb-3"
        title={title}
        titleClassName="m-0 text-sm font-medium text-[var(--color-text-1)]"
        actions={(
          <Button type="primary" ghost size="small" onClick={onAdd}>
            {addLabel}
          </Button>
        )}
      />
      <div className="flex-1 space-y-2 overflow-y-auto" ref={listRef}>
        {items.length === 0 ? (
          <ToolEditorEmptyState description={emptyDescription} />
        ) : (
          items.map((item) => {
            const isActive = item.id === selectedId;
            return (
              <button
                key={item.id}
                type="button"
                className={getItemClassName(isActive)}
                onClick={() => onSelect(item.id)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{item.title}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                      {item.description}
                    </div>
                  </div>
                  <DeleteOutlined
                    className="mt-1 text-[var(--color-text-3)] hover:text-[var(--color-error)]"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDelete(item.id);
                    }}
                  />
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};

export default ToolInstanceSidebar;
