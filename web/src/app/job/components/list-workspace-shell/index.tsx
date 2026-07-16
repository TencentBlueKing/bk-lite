import React from 'react';
import type { FieldConfig, SearchFilters } from '@/components/search-combination/types';
import PageFormHeaderCard from '@/components/page-form-header-card';
import SearchCombinationToolbar from '@/components/search-combination-toolbar';
import WorkspacePanel from '@/components/workspace-panel';
import CustomTable from '@/components/custom-table';

type CustomTableProps = React.ComponentProps<typeof CustomTable>;

export interface JobListWorkspaceShellProps {
  title: string;
  description: string;
  fieldConfigs: FieldConfig[];
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
  onSearchChange: (filters: SearchFilters) => void;
  className?: string;
  contentClassName?: string;
}

const JobListWorkspaceShell: React.FC<JobListWorkspaceShellProps> = ({
  title,
  description,
  fieldConfigs,
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
  onSearchChange,
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
      <PageFormHeaderCard
        title={title}
        description={description}
        className="mb-4 shrink-0"
      />

      <WorkspacePanel
        className="flex flex-1 min-h-0 flex-col"
        toolbar={(
          <SearchCombinationToolbar
            fieldConfigs={fieldConfigs}
            onSearchChange={onSearchChange}
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
