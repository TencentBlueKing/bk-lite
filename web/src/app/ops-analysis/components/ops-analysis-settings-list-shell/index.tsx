import React from 'react';
import SearchActionBar from '@/components/search-action-bar';
import TopSection from '@/components/top-section';
import CustomTable from '@/components/custom-table';

type CustomTableRowSelection = React.ComponentProps<typeof CustomTable>['rowSelection'];
type CustomTablePagination = React.ComponentProps<typeof CustomTable>['pagination'];
type CustomTableExtraProps = Omit<
  React.ComponentProps<typeof CustomTable>,
  'columns' | 'dataSource' | 'rowKey' | 'pagination' | 'scroll' | 'loading' | 'rowSelection'
>;

export interface OpsAnalysisSettingsListShellProps {
  introTitle: React.ReactNode;
  introDescription: React.ReactNode;
  searchValue: string;
  searchPlaceholder: string;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  onSearchValueChange: (value: string) => void;
  onSearch: (value: string) => void;
  onSearchClear: () => void;
  columns?: unknown[];
  dataSource?: unknown[];
  rowKey?: string | ((record: any) => React.Key);
  pagination?: CustomTablePagination;
  scroll?: { x?: number | string; y?: number | string };
  tableLoading?: boolean;
  rowSelection?: CustomTableRowSelection;
  tableProps?: CustomTableExtraProps;
  modal?: React.ReactNode;
}

const OpsAnalysisSettingsListShell: React.FC<OpsAnalysisSettingsListShellProps> = ({
  introTitle,
  introDescription,
  searchValue,
  searchPlaceholder,
  actions,
  children,
  onSearchValueChange,
  onSearch,
  onSearchClear,
  columns,
  dataSource,
  rowKey,
  pagination,
  scroll,
  tableLoading = false,
  rowSelection,
  tableProps,
  modal,
}) => {
  const hasTableContract = Boolean(columns && dataSource && rowKey);

  return (
    <div className="flex h-full w-full flex-col bg-[var(--color-bg-1)]">
      <TopSection
        title={introTitle}
        content={(
          <div className="text-sm text-[var(--color-text-3)]">
            {introDescription}
          </div>
        )}
        className="mb-4"
      />

      <div className="px-6 pb-0">
        <SearchActionBar
          searchProps={{
            value: searchValue,
            placeholder: searchPlaceholder,
            enterButton: false,
            onChange: (event) => onSearchValueChange(event.target.value),
            onSearch,
            onClear: onSearchClear,
          }}
          actions={actions}
        />
        {modal}
        {hasTableContract ? (
          <CustomTable
            {...tableProps}
            size="middle"
            rowKey={rowKey as any}
            columns={columns as any[]}
            loading={tableLoading}
            dataSource={dataSource as any[]}
            pagination={pagination}
            rowSelection={rowSelection}
            scroll={scroll}
          />
        ) : null}
        {children}
      </div>
    </div>
  );
};

export default OpsAnalysisSettingsListShell;
