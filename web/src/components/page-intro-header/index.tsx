import React from 'react';
import PageHeaderShell from '@/components/page-header-shell';

export interface PageIntroHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  leading?: React.ReactNode;
  actions?: React.ReactNode;
  spacing?: 'default' | 'compact';
  className?: string;
  headerRowClassName?: string;
  contentClassName?: string;
  titleRowClassName?: string;
  titleClassName?: string;
  descriptionRowClassName?: string;
  descriptionClassName?: string;
  actionsClassName?: string;
}

const PageIntroHeader: React.FC<PageIntroHeaderProps> = ({
  title,
  description,
  leading,
  actions,
  spacing = 'default',
  className = '',
  headerRowClassName = 'flex w-full flex-col gap-3 lg:flex-row lg:items-start lg:justify-between',
  contentClassName = 'min-w-0 flex-1',
  titleRowClassName,
  titleClassName = 'm-0 text-[20px] font-semibold text-[var(--color-text-1)]',
  descriptionRowClassName = 'mt-1',
  descriptionClassName = 'm-0 text-[13px] text-[var(--color-text-3)]',
  actionsClassName = 'w-full lg:ml-auto lg:w-auto',
}) => {
  const spacingClassName = spacing === 'compact' ? 'mb-[10px]' : 'mb-4';

  return (
    <PageHeaderShell
      as="h1"
      title={title}
      subtitle={description}
      leading={leading}
      actions={actions}
      className={`${spacingClassName} ${className}`.trim()}
      headerRowClassName={headerRowClassName}
      contentClassName={contentClassName}
      titleRowClassName={titleRowClassName}
      titleClassName={titleClassName}
      subtitleRowClassName={descriptionRowClassName}
      subtitleClassName={descriptionClassName}
      actionsClassName={actionsClassName}
    />
  );
};

export default PageIntroHeader;
