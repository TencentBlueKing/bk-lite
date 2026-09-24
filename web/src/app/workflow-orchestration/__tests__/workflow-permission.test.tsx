import { render } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkflowPermission } from '../components/workflow-permission';

const captures = vi.hoisted(() => ({ props: [] as Array<Record<string, unknown>> }));

vi.mock('@/components/permission', () => ({
  default: ({ children, ...props }: PropsWithChildren<Record<string, unknown>>) => {
    captures.props.push(props);
    return <>{children}</>;
  },
}));

describe('WorkflowPermission', () => {
  beforeEach(() => {
    captures.props.length = 0;
  });

  it('maps workflow operations to the selected menu permission path', () => {
    render(<WorkflowPermission operation="Publish" area="executions">Publish</WorkflowPermission>);

    expect(captures.props.at(-1)).toMatchObject({
      requiredPermissions: ['Publish'],
      permissionPath: '/workflow-orchestration/executions',
    });
  });

  it('allows a read-only workflow instance to pass the shared wrapper view gate', () => {
    render(<WorkflowPermission operation="View" instancePermissions={['View']}>View</WorkflowPermission>);

    expect(captures.props.at(-1)).toMatchObject({ instPermissions: ['Operate'] });
  });

  it('keeps write operations bound to instance Operate permission', () => {
    render(<WorkflowPermission operation="Edit" instancePermissions={['View']}>Edit</WorkflowPermission>);

    expect(captures.props.at(-1)).toMatchObject({ instPermissions: ['View'] });
  });
});
