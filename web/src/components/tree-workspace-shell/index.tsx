import React from 'react';
import ResizableSidebar from '@/components/resizable-sidebar';
import TreeSelectorPanel, {
  type TreeSelectorPanelProps,
} from '@/components/tree-selector-panel';

export interface TreeWorkspaceShellProps<TSortData = unknown> {
  treePanelProps: TreeSelectorPanelProps<TSortData>;
  children: React.ReactNode;
  sidebarHeader?: React.ReactNode;
  sidebarMode?: 'fixed' | 'resizable';
  collapseStorageKey?: string;
  sidebarClassName?: string;
  sidebarContentClassName?: string;
  treeContainerClassName?: string;
  contentClassName?: string;
  containerClassName?: string;
}

function TreeWorkspaceShell<TSortData = unknown>({
  treePanelProps,
  children,
  sidebarHeader,
  sidebarMode = 'fixed',
  collapseStorageKey,
  sidebarClassName = '',
  sidebarContentClassName = 'h-[calc(100vh-146px)] w-full overflow-y-auto overflow-x-hidden bg-[var(--color-bg-1)] px-[10px] py-5',
  treeContainerClassName = '',
  contentClassName = 'flex-1 min-w-0 bg-[var(--color-bg-1)] p-5',
  containerClassName = 'flex w-full overflow-hidden',
}: TreeWorkspaceShellProps<TSortData>) {
  const sidebarContent = (
    <div className={sidebarContentClassName}>
      {sidebarHeader}
      <div className={treeContainerClassName}>
        <TreeSelectorPanel {...treePanelProps} />
      </div>
    </div>
  );
  const resolvedSidebarClassName = sidebarMode === 'fixed'
    ? ['shrink-0', sidebarClassName].filter(Boolean).join(' ')
    : sidebarClassName;

  return (
    <div className={containerClassName}>
      {sidebarMode === 'resizable' ? (
        <ResizableSidebar collapseStorageKey={collapseStorageKey}>
          {sidebarContent}
        </ResizableSidebar>
      ) : (
        <div className={resolvedSidebarClassName}>{sidebarContent}</div>
      )}
      <div className={contentClassName}>{children}</div>
    </div>
  );
}

export default TreeWorkspaceShell;
