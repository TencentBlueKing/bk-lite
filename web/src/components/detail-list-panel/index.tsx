'use client';

import React from 'react';
import CopyableDetailList, {
  type CopyableDetailListItem,
} from '@/components/copyable-detail-list';

interface DetailListPanelProps {
  items: CopyableDetailListItem[];
  className?: string;
  listClassName?: string;
  labelWidthClassName?: string;
  placeholder?: string;
}

const DetailListPanel: React.FC<DetailListPanelProps> = ({
  items,
  className = 'overflow-hidden rounded-[8px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]',
  listClassName = '',
  labelWidthClassName = 'w-24',
  placeholder = '-',
}) => {
  return (
    <div className={className}>
      <CopyableDetailList
        items={items}
        className={listClassName}
        labelWidthClassName={labelWidthClassName}
        placeholder={placeholder}
      />
    </div>
  );
};

export default DetailListPanel;
