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
  sidebarContentClassName = 'flex h-full min-h-0 w-full flex-col overflow-y-auto overflow-x-hidden bg-[var(--color-bg-1)] px-2.5 py-5',
  treeContainerClassName = '',
  contentClassName = 'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--color-bg-1)] p-5',
  containerClassName = 'flex h-full min-h-0 w-full min-w-0 gap-2.5 overflow-hidden',
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
