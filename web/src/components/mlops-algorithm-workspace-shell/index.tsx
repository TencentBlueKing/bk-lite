'use client';

import React from 'react';
import type { SearchProps } from 'antd/es/input/Search';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import ManagementTableShell from '@/components/management-table-shell';
import MlopsAlgorithmTypeBadge from '@/components/mlops-algorithm-type-badge';
import SearchActionBar from '@/components/search-action-bar';
import ToolbarSplitShell from '@/components/toolbar-split-shell';

type ManagementTableShellProps = React.ComponentProps<typeof ManagementTableShell>;

export interface MlopsAlgorithmWorkspaceShellProps
  extends Omit<ManagementTableShellProps, 'topSection' | 'searchProps' | 'actions'> {
  algorithmType?: string | null;
  description: string | null;
  searchProps?: SearchProps;
  actions?: React.ReactNode;
  refreshAction?: React.ReactNode;
  headerClassName?: string;
  headerContentClassName?: string;
  headerActionsClassName?: string;
}

const MlopsAlgorithmWorkspaceShell: React.FC<MlopsAlgorithmWorkspaceShellProps> = ({
  algorithmType,
  description,
  searchProps,
  actions,
  refreshAction,
  headerClassName = 'items-center gap-2',
  headerContentClassName = 'items-center gap-2 min-w-0 flex-1',
  headerActionsClassName = 'items-center gap-2 shrink-0',
  containerClassName,
  panelClassName = 'rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4 shadow-sm',
  searchClassName,
  ...tableShellProps
}) => {
  const {
    className: searchInputClassName,
    ...restSearchProps
  } = searchProps || {};

  const header = (
    <ToolbarSplitShell
      className={`mb-0 ${headerClassName}`.trim()}
      leadingClassName={headerContentClassName}
      trailingClassName={headerActionsClassName}
      leading={(
        <>
        <MlopsAlgorithmTypeBadge
          algorithmType={algorithmType}
          className="shrink-0"
        />
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={description}
        />
        </>
      )}
      trailing={
        searchProps || actions || refreshAction ? (
          searchProps ? (
            <SearchActionBar
              spacing="flush"
              searchProps={{
                className: `w-60 ${searchInputClassName || ''}`.trim(),
                ...restSearchProps,
              }}
              actions={(
                <>
                  {actions}
                  {refreshAction}
                </>
              )}
            />
          ) : (
            <>
              {actions}
              {refreshAction}
            </>
          )
        ) : undefined
      }
    />
  );

  return (
    <ManagementTableShell
      {...tableShellProps}
      topSection={header}
      containerClassName={containerClassName}
      panelClassName={panelClassName}
      searchClassName={searchClassName}
    />
  );
};

export default MlopsAlgorithmWorkspaceShell;
