'use client';

import type { PropsWithChildren } from 'react';

import PermissionWrapper from '@/components/permission';

type WorkflowOperation = 'View' | 'Add' | 'Edit' | 'Delete' | 'Execute' | 'Publish' | 'Approve' | 'Manage';
type WorkflowPermissionArea = 'home' | 'workflows' | 'executions';

const PERMISSION_PATH: Record<WorkflowPermissionArea, string> = {
  home: '/workflow-orchestration/home',
  workflows: '/workflow-orchestration/workflows',
  executions: '/workflow-orchestration/executions',
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
