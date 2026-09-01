'use client';

import type { ReactNode } from 'react';

interface OpsPilotListPageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

/** OpsPilot 列表页头：左侧标题+简介与右侧搜索/操作同一行。 */
export default function OpsPilotListPageHeader({
  title,
  description,
  actions,
}: OpsPilotListPageHeaderProps) {
  return (
    <div className="mb-4 flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-3">
      <div className="min-w-0 flex-1">
        <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{title}</div>
        {description ? (
          <div className="mt-1 text-[11px] leading-snug text-[var(--color-text-3)]">{description}</div>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
