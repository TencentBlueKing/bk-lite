import React from 'react';
import { Spin } from 'antd';
import type { SearchProps } from 'antd/es/input/Search';
import CustomTable from '@/components/custom-table';
import SearchActionBar from '@/components/search-action-bar';
import ToolbarSplitShell from '@/components/toolbar-split-shell';

type CustomTableRowSelection = React.ComponentProps<typeof CustomTable>['rowSelection'];
type CustomTablePagination = React.ComponentProps<typeof CustomTable>['pagination'];
type CustomTableExtraProps = Omit<
  React.ComponentProps<typeof CustomTable>,
  'columns' | 'dataSource' | 'rowKey' | 'pagination' | 'scroll' | 'loading' | 'rowSelection' | 'locale'
>;

export interface ManagementTableShellProps {
  topSection?: React.ReactNode;
  loading?: boolean;
  toolbar?: React.ReactNode;
  searchProps?: SearchProps;
  actions?: React.ReactNode;
  columns: unknown[];
  dataSource: unknown[];
  rowKey: string | ((record: any) => React.Key);
  pagination?: CustomTablePagination;
  scroll?: { x?: number | string; y?: number | string };
  rowSelection?: CustomTableRowSelection;
  tableProps?: CustomTableExtraProps;
  emptyText?: React.ReactNode;
  modal?: React.ReactNode;
  children?: React.ReactNode;
  containerClassName?: string;
  panelClassName?: string;
  toolbarContainerVariant?: 'default' | 'spaced' | 'divided';
  toolbarContainerClassName?: string;
  tableContainerClassName?: string;
  searchClassName?: string;
}

const joinClassName = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const ManagementTableShell: React.FC<ManagementTableShellProps> = ({
  topSection,
  loading = false,
  toolbar,
  searchProps,
  actions,
  columns,
  dataSource,
  rowKey,
  pagination,
  scroll,
  rowSelection,
  tableProps,
  emptyText,
  modal,
  children,
  containerClassName = 'h-full w-full',
  panelClassName = 'rounded-md bg-[var(--color-bg)] p-4',
  toolbarContainerVariant = 'default',
  toolbarContainerClassName = '',
  tableContainerClassName = '',
  searchClassName = 'gap-2',
}) => {
  const toolbarContainerVariantClassName =
    toolbarContainerVariant === 'spaced'
      ? 'mb-5'
      : toolbarContainerVariant === 'divided'
        ? 'mb-5 border-b border-[var(--color-border-1)] pb-4'
        : '';

  const toolbarContainerClassNames = joinClassName(
    toolbarContainerVariantClassName,
    toolbarContainerClassName,
  );

  return (
    <div className={containerClassName}>
      {topSection ? <div className="mb-4">{topSection}</div> : null}

      <div className={panelClassName}>
        {toolbar ? (
          <div className={toolbarContainerClassNames}>
            {toolbar}
          </div>
        ) : searchProps ? (
          <div className={toolbarContainerClassNames}>
            <SearchActionBar
              searchProps={searchProps}
              actions={actions}
              className={searchClassName}
            />
          </div>
        ) : actions ? (
          <div className={toolbarContainerClassNames}>
            <ToolbarSplitShell
              className={`mb-4 ${searchClassName}`.trim()}
              trailing={actions}
            />
          </div>
        ) : null}

        {modal}

        <div className={tableContainerClassName}>
          <Spin spinning={loading}>
            <CustomTable
              {...tableProps}
              columns={columns as any}
              dataSource={dataSource as any[]}
              rowKey={rowKey as any}
              pagination={pagination as any}
              scroll={scroll}
              rowSelection={rowSelection}
              locale={emptyText ? { emptyText } : undefined}
            />
          </Spin>
        </div>

        {children}
      </div>
    </div>
  );
};

export default ManagementTableShell;
