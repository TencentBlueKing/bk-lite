'use client';

import type { PropsWithChildren } from 'react';

import PermissionWrapper from '@/components/permission';

export type WorkflowOperation = 'View' | 'Add' | 'Edit' | 'Delete' | 'Execute' | 'Publish' | 'Approve' | 'Manage';
export type WorkflowPermissionArea = 'home' | 'workflows' | 'market' | 'executions';

const PERMISSION_PATH: Record<WorkflowPermissionArea, string> = {
  home: '/workflow/home',
  workflows: '/workflow/workflows',
  market: '/workflow/market',
  executions: '/workflow/executions',
};

interface WorkflowPermissionProps {
  operation: WorkflowOperation;
  area?: WorkflowPermissionArea;
  instancePermissions?: string[];
  className?: string;
}

export function WorkflowPermission({
  operation,
  area = 'workflows',
  instancePermissions,
  className,
  children,
}: PropsWithChildren<WorkflowPermissionProps>) {
  const effectiveInstancePermissions = operation === 'View' && instancePermissions
    ? (instancePermissions.includes('View') || instancePermissions.includes('Operate') ? ['Operate'] : [])
    : instancePermissions;
  return (
    <span
      className={className}
      data-instance-permissions={instancePermissions ? instancePermissions.join(',') : undefined}
    >
      <PermissionWrapper
        requiredPermissions={[operation]}
        permissionPath={PERMISSION_PATH[area]}
        instPermissions={effectiveInstancePermissions}
        className={className === 'contents' ? undefined : className}
      >
        {children}
      </PermissionWrapper>
    </span>
  );
}
