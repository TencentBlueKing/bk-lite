'use client';

import React from 'react';
import { Spin, Tabs } from 'antd';
import type { TabsProps } from 'antd';
import Collapse, { usePersistedCollapseOpen } from '@/components/collapse';
import ManagementTableShell from '@/components/management-table-shell';

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
  chartCollapseStorageKey?: string;
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
  chartCollapseStorageKey = 'event.alert.chartExpanded',
  searchProps,
  columns,
  dataSource,
  rowKey,
  pagination,
  loading = false,
  scroll,
  containerClassName = 'min-w-0',
  chartWrapperClassName = 'mb-[10px] w-full overflow-hidden bg-[var(--color-bg-1)]',
  chartClassName = 'h-[100px] px-[10px]',
  filterPanelClassName = 'mb-[10px] bg-[var(--color-bg-1)] px-5 py-[10px]',
  tableContainerClassName = 'w-full bg-[var(--color-bg-1)] px-5 pb-5 pt-[10px]',
}) => {
  const [chartExpanded, onChartToggle] = usePersistedCollapseOpen(
    chartCollapseStorageKey
  );

  return (
    <div className={containerClassName}>
      <Tabs activeKey={activeTab} items={tabs} onChange={onTabChange} />

      <div className={filterPanelClassName}>
        {filterPanel}
      </div>

      <Spin spinning={chartLoading}>
        <div className={chartWrapperClassName}>
          <Collapse
            title={chartTitle}
            icon={chartHint ? <span>{chartHint}</span> : undefined}
            isOpen={chartExpanded}
            onToggle={onChartToggle}
          >
            <div className={chartClassName}>
              {chartContent}
            </div>
          </Collapse>
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
