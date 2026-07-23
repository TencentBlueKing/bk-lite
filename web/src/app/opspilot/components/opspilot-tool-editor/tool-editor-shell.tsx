'use client';

import React from 'react';
import SectionHeader from '@/components/section-header';
import ToolConnectionStatusTag, {
  type ToolConnectionStatus,
  type ToolConnectionStatusTagProps,
} from './tool-connection-status-tag';
import ToolEditorEmptyState from './tool-editor-empty-state';
import ToolInstanceSidebar, { type ToolInstanceSidebarProps } from './tool-instance-sidebar';

export interface ToolEditorShellProps {
  sidebarProps: ToolInstanceSidebarProps;
  detailTitle?: React.ReactNode;
  detailStatusScope?: ToolConnectionStatusTagProps['scope'];
  detailStatus?: ToolConnectionStatus;
  detailHeaderExtra?: React.ReactNode;
  detailFooter?: React.ReactNode;
  detailFooterClassName?: string;
  emptyDescription: React.ReactNode;
  className?: string;
  panelClassName?: string;
  bodyClassName?: string;
  children?: React.ReactNode;
}

const joinClassNames = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const ToolEditorShell: React.FC<ToolEditorShellProps> = ({
  sidebarProps,
  detailTitle,
  detailStatusScope,
  detailStatus,
  detailHeaderExtra,
  detailFooter,
  detailFooterClassName,
  emptyDescription,
  className,
  panelClassName,
  bodyClassName,
  children,
}) => {
  const resolvedHeaderExtra = detailHeaderExtra ?? (
    detailStatusScope && detailStatus ? (
      <ToolConnectionStatusTag scope={detailStatusScope} status={detailStatus} />
    ) : null
  );

  return (
    <div className={joinClassNames('flex min-h-[480px] gap-4', className)}>
      <ToolInstanceSidebar {...sidebarProps} />

      <div
        className={joinClassNames(
          'flex-1 rounded border border-[var(--color-border)] p-4',
          panelClassName,
        )}
      >
        {detailTitle ? (
          <div className={joinClassNames('space-y-4', bodyClassName)}>
            <SectionHeader
              title={detailTitle}
              titleClassName="m-0 text-lg font-medium text-[var(--color-text-1)]"
              actions={resolvedHeaderExtra}
            />
            {children}
            {detailFooter ? (
              <div className={joinClassNames('flex justify-end', detailFooterClassName)}>
                {detailFooter}
              </div>
            ) : null}
          </div>
        ) : (
          <ToolEditorEmptyState description={emptyDescription} fullHeight />
        )}
      </div>
    </div>
  );
};

export default ToolEditorShell;
