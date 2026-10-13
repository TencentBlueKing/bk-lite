import React from 'react';
import type { SearchProps } from 'antd/es/input/Search';
import SearchActionBar from '@/components/search-action-bar';
import TopSection from '@/components/top-section';
import WorkspacePanel from '@/components/workspace-panel';
import CustomTable from '@/components/custom-table';

type CustomTableProps = React.ComponentProps<typeof CustomTable>;

export interface JobListWorkspaceShellProps {
  title: string;
  description: string;
  searchProps: SearchProps;
  filters?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  tableDataSource?: CustomTableProps['dataSource'];
  tableColumns?: CustomTableProps['columns'];
  tableRowKey?: CustomTableProps['rowKey'];
  tablePagination?: CustomTableProps['pagination'];
  tableRowSelection?: CustomTableProps['rowSelection'];
  tableScroll?: CustomTableProps['scroll'];
  tableLoading?: boolean;
  tableProps?: Omit<
    CustomTableProps,
    | 'dataSource'
    | 'columns'
    | 'rowKey'
    | 'pagination'
    | 'rowSelection'
    | 'scroll'
    | 'loading'
  >;
  className?: string;
  contentClassName?: string;
}

const JobListWorkspaceShell: React.FC<JobListWorkspaceShellProps> = ({
  title,
  description,
  searchProps,
  filters,
  actions,
  children,
  tableDataSource,
  tableColumns,
  tableRowKey,
  tablePagination,
  tableRowSelection,
  tableScroll,
  tableLoading = false,
  tableProps,
  className = 'flex h-full w-full flex-col overflow-hidden',
  contentClassName = 'flex-1 min-h-0',
}) => {
  const resolvedContent = children ?? (
    <CustomTable
      {...tableProps}
      dataSource={tableDataSource}
      columns={tableColumns}
      rowKey={tableRowKey}
      pagination={tablePagination}
      rowSelection={tableRowSelection}
      scroll={tableScroll}
      loading={tableLoading}
    />
  );

  return (
    <div className={className}>
      <TopSection
        title={title}
        content={description}
        className="mb-4 shrink-0"
      />

      <WorkspacePanel
        className="flex flex-1 min-h-0 flex-col"
        toolbar={(
          <SearchActionBar
            spacing="flush"
            searchProps={searchProps}
            filters={filters}
            actions={actions}
          />
        )}
      >
        <div className={contentClassName}>
          {resolvedContent}
        </div>
      </WorkspacePanel>
    </div>
  );
};

export default JobListWorkspaceShell;
