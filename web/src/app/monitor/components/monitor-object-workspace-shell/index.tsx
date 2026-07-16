import React from 'react';
import type { TreeSelectorPanelProps } from '@/components/tree-selector-panel';
import TreeWorkspaceShell from '@/components/tree-workspace-shell';

export interface MonitorObjectWorkspaceShellProps<TSortData = unknown> {
  collapseStorageKey: string;
  treePanelProps: TreeSelectorPanelProps<TSortData>;
  sidebarHeader?: React.ReactNode;
  children: React.ReactNode;
  containerClassName?: string;
  sidebarContentClassName?: string;
  treeContainerClassName?: string;
  contentClassName?: string;
}

function MonitorObjectWorkspaceShell<TSortData = unknown>({
  collapseStorageKey,
  treePanelProps,
  sidebarHeader,
  children,
  containerClassName,
  sidebarContentClassName,
  treeContainerClassName,
  contentClassName,
}: MonitorObjectWorkspaceShellProps<TSortData>) {
  return (
    <TreeWorkspaceShell
      sidebarMode="resizable"
      collapseStorageKey={collapseStorageKey}
      sidebarHeader={sidebarHeader}
      treePanelProps={treePanelProps}
      containerClassName={containerClassName}
      sidebarContentClassName={sidebarContentClassName}
      treeContainerClassName={treeContainerClassName}
      contentClassName={contentClassName}
    >
      {children}
    </TreeWorkspaceShell>
  );
}

export default MonitorObjectWorkspaceShell;
