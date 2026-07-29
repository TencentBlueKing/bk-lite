import React from 'react';
import PageHeaderShell from '@/components/page-header-shell';

export interface DashboardWorkspaceHeaderProps {
  title: React.ReactNode;
  controls?: React.ReactNode;
  as?: 'div' | 'h1' | 'h2' | 'h3';
  className?: string;
  headerRowClassName?: string;
  contentClassName?: string;
  titleRowClassName?: string;
  titleClassName?: string;
  controlsClassName?: string;
}

const DashboardWorkspaceHeader: React.FC<DashboardWorkspaceHeaderProps> = ({
  title,
  controls,
  as = 'h2',
  className,
  headerRowClassName = 'flex min-w-0 flex-wrap items-center justify-between gap-3',
  contentClassName,
  titleRowClassName = 'min-w-0',
  titleClassName = 'm-0 whitespace-nowrap text-xl font-semibold text-[var(--color-text-1)]',
  controlsClassName = 'ml-auto flex flex-wrap items-center justify-end gap-2',
}) => (
  <PageHeaderShell
    as={as}
    title={title}
    actions={controls}
    className={className}
    headerRowClassName={headerRowClassName}
    contentClassName={contentClassName}
    titleRowClassName={titleRowClassName}
    titleClassName={titleClassName}
    actionsClassName={controlsClassName}
  />
);

export default DashboardWorkspaceHeader;
