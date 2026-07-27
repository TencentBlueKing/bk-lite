import React from 'react';
import type { TreeSelectorPanelProps } from '@/components/tree-selector-panel';
import type { SearchProps } from 'antd/es/input/Search';
import ManagementTableShell from '@/components/management-table-shell';
import TreeWorkspaceShell from '@/components/tree-workspace-shell';

type ManagementTableShellProps = React.ComponentProps<typeof ManagementTableShell>;

export interface IntegrationInstanceManagementShellProps<TSortData = unknown> {
  treePanelProps: TreeSelectorPanelProps<TSortData>;
  sidebarMode?: 'fixed' | 'resizable';
  sidebarCollapseStorageKey?: string;
  sidebarHeader?: React.ReactNode;
  containerClassName?: string;
  sidebarClassName?: string;
  sidebarContentClassName?: string;
  treeContainerClassName?: string;
  contentClassName?: string;
  panelClassName?: string;
  searchClassName?: string;
  loading?: boolean;
  searchProps?: SearchProps;
  actions?: React.ReactNode;
  columns: ManagementTableShellProps['columns'];
  dataSource: ManagementTableShellProps['dataSource'];
  rowKey: ManagementTableShellProps['rowKey'];
  pagination?: ManagementTableShellProps['pagination'];
  scroll?: ManagementTableShellProps['scroll'];
  rowSelection?: ManagementTableShellProps['rowSelection'];
  tableProps?: ManagementTableShellProps['tableProps'];
  emptyText?: ManagementTableShellProps['emptyText'];
  modal?: React.ReactNode;
  tableContainerClassName?: string;
  toolbarContainerClassName?: string;
}

function IntegrationInstanceManagementShell<TSortData = unknown>({
  treePanelProps,
  sidebarMode = 'fixed',
  sidebarCollapseStorageKey,
  sidebarHeader,
  containerClassName,
  sidebarClassName,
  sidebarContentClassName,
  treeContainerClassName = '',
  contentClassName = 'flex-1 min-w-0',
  panelClassName = 'bg-transparent p-0',
  searchClassName = '!justify-between w-full items-center gap-3',
  loading = false,
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
  tableContainerClassName,
  toolbarContainerClassName,
}: IntegrationInstanceManagementShellProps<TSortData>) {
  return (
    <TreeWorkspaceShell
      treePanelProps={treePanelProps}
      sidebarMode={sidebarMode}
      collapseStorageKey={sidebarCollapseStorageKey}
      sidebarHeader={sidebarHeader}
      containerClassName={containerClassName}
      sidebarClassName={sidebarClassName}
      sidebarContentClassName={sidebarContentClassName}
      treeContainerClassName={treeContainerClassName}
      contentClassName={contentClassName}
    >
      <ManagementTableShell
        panelClassName={panelClassName}
        loading={loading}
        searchProps={searchProps}
        actions={actions}
        searchClassName={searchClassName}
        columns={columns}
        dataSource={dataSource}
        rowKey={rowKey}
        pagination={pagination}
        scroll={scroll}
        rowSelection={rowSelection}
        tableProps={tableProps}
        emptyText={emptyText}
        modal={modal}
        tableContainerClassName={tableContainerClassName}
        toolbarContainerClassName={toolbarContainerClassName}
      />
    </TreeWorkspaceShell>
  );
}

export default IntegrationInstanceManagementShell;
