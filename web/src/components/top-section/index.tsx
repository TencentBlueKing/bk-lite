'use client';

import React from 'react';
import Icon from '@/components/icon';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface TopSectionProps {
  title: React.ReactNode;
  content?: React.ReactNode;
  iconType?: string;
  icon?: React.ReactNode;
  iconSrc?: string;
  iconAlt?: string;
  variant?: string;
  className?: string;
}

/** 独立页眉：标题和说明单独成条，高度随两行说明增长。 */
const TopSection: React.FC<TopSectionProps> = ({
  title,
  content,
  iconType,
  icon,
  className = '',
}) => {
  const resolvedIcon = icon ? (
    icon
  ) : iconType ? (
    <Icon type={iconType} className="text-[40px] leading-none" />
  ) : null;

  return (
    <div className={`flex w-full items-center gap-3 rounded-md bg-[var(--color-bg)] px-4 py-4 ${className}`.trim()}>
      {resolvedIcon ? <div className="flex shrink-0 items-center">{resolvedIcon}</div> : null}
      <div className="min-w-0 flex-1">
        <h2 className="m-0 text-base font-semibold leading-tight text-[var(--color-text-1)]">{title}</h2>
        {content ? (
          <EllipsisWithTooltip
            className="mt-1 line-clamp-2 text-xs leading-snug text-[var(--color-text-3)]"
            text={content}
          />
        ) : null}
      </div>
    </div>
  );
};

export default TopSection;
