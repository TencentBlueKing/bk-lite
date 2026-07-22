'use client';

import React from 'react';
import Introduction from '@/components/introduction';
import ManagementTableShell from '@/components/management-table-shell';

type ManagementTableShellProps = React.ComponentProps<typeof ManagementTableShell>;

export interface IntroductionTableWorkspaceShellProps
  extends Omit<ManagementTableShellProps, 'topSection'> {
  title: string;
  message: string;
  introductionClassName?: string;
  introductionMinWidth?: number | string;
}

const IntroductionTableWorkspaceShell: React.FC<
  IntroductionTableWorkspaceShellProps
> = ({
  title,
  message,
  introductionClassName,
  introductionMinWidth,
  containerClassName = 'h-full w-full px-4 pb-4',
  panelClassName = 'rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4 shadow-sm',
  searchClassName = 'items-center justify-between',
  ...tableShellProps
}) => {
  return (
    <div className={containerClassName}>
      <Introduction
        title={title}
        message={message}
        minWidth={introductionMinWidth}
        className={introductionClassName}
      />
      <ManagementTableShell
        {...tableShellProps}
        containerClassName="h-auto w-full"
        panelClassName={panelClassName}
        searchClassName={searchClassName}
      />
    </div>
  );
};

export default IntroductionTableWorkspaceShell;
