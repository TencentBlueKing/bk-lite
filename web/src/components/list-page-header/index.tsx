'use client';

import type { ReactNode } from 'react';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface ListPageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

/** 列表页头：左侧标题+简介与右侧搜索/操作同一行。说明最多两行。 */
export default function ListPageHeader({
  title,
  description,
  actions,
}: ListPageHeaderProps) {
  return (
    <div className="mb-4 flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-3">
      <div className="min-w-0 flex-1">
        <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{title}</div>
        {description ? (
          <EllipsisWithTooltip
            className="mt-1 line-clamp-2 text-xs leading-snug text-[var(--color-text-3)]"
            text={description}
          />
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
