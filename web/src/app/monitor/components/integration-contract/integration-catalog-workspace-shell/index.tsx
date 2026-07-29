import React from 'react';
import { Spin } from 'antd';
import type { TreeSelectorPanelProps } from '@/components/tree-selector-panel';
import TreeWorkspaceShell from '@/components/tree-workspace-shell';
import ToolbarSplitShell from '@/components/toolbar-split-shell';

type KeyGetter<T> = (item: T, index: number) => React.Key;
type ItemRenderer<T> = (item: T, index: number) => React.ReactNode;

export interface IntegrationCatalogWorkspaceShellProps<T> {
  items: T[];
  renderItem: ItemRenderer<T>;
  getItemKey: KeyGetter<T>;
  treePanelProps: TreeSelectorPanelProps;
  sidebarHeader?: React.ReactNode;
  sidebarMode?: 'fixed' | 'resizable';
  sidebarCollapseStorageKey?: string;
  search?: React.ReactNode;
  actions?: React.ReactNode;
  loading?: boolean;
  emptyState?: React.ReactNode;
  containerClassName?: string;
  sidebarClassName?: string;
  sidebarContentClassName?: string;
  treeContainerClassName?: string;
  contentClassName?: string;
  toolbarClassName?: string;
  gridClassName?: string;
  gridStyle?: React.CSSProperties;
}

const defaultGridStyle: React.CSSProperties = {
  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  alignContent: 'start',
};

function IntegrationCatalogWorkspaceShell<T>({
  items,
  renderItem,
  getItemKey,
  treePanelProps,
  sidebarHeader,
  sidebarMode = 'fixed',
  sidebarCollapseStorageKey,
  search,
  actions,
  loading = false,
  emptyState = null,
  containerClassName,
  sidebarClassName,
  sidebarContentClassName,
  treeContainerClassName = '',
  contentClassName,
  toolbarClassName = 'mb-[20px]',
  gridClassName = 'grid h-[calc(100vh-236px)] w-full gap-4 overflow-y-auto',
  gridStyle = defaultGridStyle,
}: IntegrationCatalogWorkspaceShellProps<T>) {
  return (
    <TreeWorkspaceShell
      treePanelProps={treePanelProps}
      sidebarHeader={sidebarHeader}
      sidebarMode={sidebarMode}
      collapseStorageKey={sidebarCollapseStorageKey}
      containerClassName={containerClassName}
      sidebarClassName={sidebarClassName}
      sidebarContentClassName={sidebarContentClassName}
      treeContainerClassName={treeContainerClassName}
      contentClassName={contentClassName}
    >
        {search || actions ? (
          <ToolbarSplitShell
            className={toolbarClassName}
            leadingClassName="flex-1 items-start"
            trailingClassName="shrink-0"
            leading={search}
            trailing={actions}
          />
        ) : null}

        <Spin spinning={loading}>
          {items.length ? (
            <div className={gridClassName} style={gridStyle}>
              {items.map((item, index) => (
                <div key={getItemKey(item, index)} className="p-2">
                  {renderItem(item, index)}
                </div>
              ))}
            </div>
          ) : (
            emptyState
          )}
        </Spin>
    </TreeWorkspaceShell>
  );
}

export default IntegrationCatalogWorkspaceShell;
