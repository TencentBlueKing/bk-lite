import React from 'react';
import { Spin, Tabs } from 'antd';
import type { TabsProps } from 'antd';
import ManagementTableShell from '@/components/management-table-shell';
import PageHeaderShell from '@/components/page-header-shell';

type ManagementTableShellProps = React.ComponentProps<typeof ManagementTableShell>;

export interface EventAlertWorkspaceShellProps {
  activeTab: string;
  tabs: TabsProps['items'];
  onTabChange: (key: string) => void;
  filterPanel: React.ReactNode;
  chartTitle: React.ReactNode;
  chartHint?: React.ReactNode;
  chartLoading?: boolean;
  chartContent: React.ReactNode;
  searchProps: ManagementTableShellProps['searchProps'];
  columns: ManagementTableShellProps['columns'];
  dataSource: ManagementTableShellProps['dataSource'];
  rowKey: ManagementTableShellProps['rowKey'];
  pagination?: ManagementTableShellProps['pagination'];
  loading?: boolean;
  scroll?: ManagementTableShellProps['scroll'];
  containerClassName?: string;
  chartWrapperClassName?: string;
  chartClassName?: string;
  filterPanelClassName?: string;
  tableContainerClassName?: string;
}

const EventAlertWorkspaceShell: React.FC<EventAlertWorkspaceShellProps> = ({
  activeTab,
  tabs,
  onTabChange,
  filterPanel,
  chartTitle,
  chartHint,
  chartLoading = false,
  chartContent,
  searchProps,
  columns,
  dataSource,
  rowKey,
  pagination,
  loading = false,
  scroll,
  containerClassName = 'min-w-0',
  chartWrapperClassName = 'mb-[10px] w-full bg-[var(--color-bg-1)] px-5 pb-0 pl-[10px] pt-5',
  chartClassName = 'h-[100px]',
  filterPanelClassName = 'mb-[10px] bg-[var(--color-bg-1)] px-5 py-[10px]',
  tableContainerClassName = 'w-full bg-[var(--color-bg-1)] px-5 pb-5 pt-[10px]',
}) => {
  return (
    <div className={containerClassName}>
      <Tabs activeKey={activeTab} items={tabs} onChange={onTabChange} />

      <div className={filterPanelClassName}>
        {filterPanel}
      </div>

      <Spin spinning={chartLoading}>
        <div className={chartWrapperClassName}>
          <PageHeaderShell
            className="mb-[2px] ml-[10px]"
            title={chartTitle}
            as="h3"
            headerRowClassName="flex items-center justify-between gap-3"
            titleRowClassName="flex items-center"
            titleClassName="m-0 text-[14px] font-normal text-[var(--color-text-1)]"
            actionsClassName="relative shrink-0"
            actions={chartHint}
          />
          <div className={chartClassName}>
            {chartContent}
          </div>
        </div>
      </Spin>

      <ManagementTableShell
        containerClassName={tableContainerClassName}
        panelClassName="bg-transparent p-0"
        toolbarContainerClassName="mb-[10px]"
        searchProps={searchProps}
        columns={columns}
        dataSource={dataSource}
        rowKey={rowKey}
        pagination={pagination}
        loading={loading}
        scroll={scroll}
      />
    </div>
  );
};

export default EventAlertWorkspaceShell;
