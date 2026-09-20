import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback || _key }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/rum/sessions',
  useSearchParams: () => new URLSearchParams('traffic=visitors'),
}));

vi.mock('antd', () => ({
  Alert: ({
    message,
    action,
    role,
  }: {
    message: React.ReactNode;
    action?: React.ReactNode;
    role?: string;
  }) => (
    <div role={role || 'status'}>
      <span>{message}</span>
      {action}
    </div>
  ),
  Button: ({
    children,
    onClick,
    'aria-label': ariaLabel,
  }: {
    children?: React.ReactNode;
    onClick?: () => void;
    'aria-label'?: string;
  }) => (
    <button type="button" aria-label={ariaLabel} onClick={onClick}>
      {children ?? ariaLabel}
    </button>
  ),
  Dropdown: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Switch: () => <input type="checkbox" />,
  Skeleton: { Input: () => <div data-testid="skeleton-input" /> },
  Table: () => <div data-testid="table" />,
}));

vi.mock('@ant-design/icons', () => ({
  ReloadOutlined: () => null,
  CaretDownOutlined: () => null,
}));

vi.mock('@/components/permission', () => ({
  default: ({
    children,
    permissionPath,
    requiredPermissions,
  }: {
    children: React.ReactNode;
    permissionPath: string;
    requiredPermissions: string[];
  }) => (
    <div
      data-testid="permission"
      data-path={permissionPath}
      data-actions={requiredPermissions.join(',')}
    >
      {children}
    </div>
  ),
}));

import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumPageError from '@/app/rum/components/rum-page-error';
import RumPermission from '@/app/rum/components/rum-permission';
import { rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import { RumMetricCard, RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import {
  RumDualWorkbench,
  RumFilterBlock,
  RumSingleWorkbench,
} from '@/app/rum/components/rum-dual-workbench';
import TrafficScopeControl from '@/app/rum/components/traffic-scope';

describe('rum shared components', () => {
  it('PipelineDegradedBanner shows control vs analytics copy', () => {
    const { rerender } = render(<PipelineDegradedBanner reason="control" />);
    expect(screen.getByText(/控制面暂不可用/)).toBeTruthy();
    rerender(<PipelineDegradedBanner reason="analytics" />);
    expect(screen.getByText(/分析数据面暂不可用/)).toBeTruthy();
  });

  it('RumPageError renders message and optional retry', () => {
    const onRetry = vi.fn();
    const { unmount } = render(<RumPageError message="boom" />);
    expect(screen.getByRole('alert').textContent).toContain('boom');
    expect(screen.queryByText('重试')).toBeNull();
    unmount();

    render(<RumPageError message="boom" onRetry={onRetry} />);
    fireEvent.click(screen.getByText('重试'));
    expect(onRetry).toHaveBeenCalled();
  });

  it('RumPermission maps resource names onto /rum paths', () => {
    render(
      <RumPermission resource="applications">
        <span>child</span>
      </RumPermission>,
    );
    const node = screen.getByTestId('permission');
    expect(node.getAttribute('data-path')).toBe('/rum/applications');
    expect(node.getAttribute('data-actions')).toBe('Operate');
    expect(screen.getByText('child')).toBeTruthy();
  });

  it('rumSkeletonColumns drops function titles and boolean fixed flags', () => {
    expect(
      rumSkeletonColumns([
        { title: 'Name', width: 120, fixed: 'left' },
        { title: () => 'Dyn', width: 80, fixed: true },
      ]),
    ).toEqual([
      { title: 'Name', width: 120, fixed: 'left' },
      { title: undefined, width: 80, fixed: undefined },
    ]);
  });

  it('metric card/grid and workbench shells render children', () => {
    render(<RumMetricGrid cells={[{ label: 'Sessions', value: '12' }]} />);
    expect(screen.getByText('Sessions')).toBeTruthy();
    expect(screen.getByText('12')).toBeTruthy();

    render(
      <RumDualWorkbench
        asideTitle="Aside"
        aside={<div>left</div>}
        mainTitle="Main"
        main={<div>right</div>}
      />,
    );
    expect(screen.getByText('Aside')).toBeTruthy();
    expect(screen.getByText('left')).toBeTruthy();
    expect(screen.getByText('Main')).toBeTruthy();
    expect(screen.getByText('right')).toBeTruthy();

    render(
      <RumSingleWorkbench title="Only">
        <div>body</div>
      </RumSingleWorkbench>,
    );
    expect(screen.getByText('Only')).toBeTruthy();
    expect(screen.getByText('body')).toBeTruthy();

    render(
      <RumFilterBlock title="Filters">
        <div>chip</div>
      </RumFilterBlock>,
    );
    expect(screen.getByText('Filters')).toBeTruthy();
    expect(screen.getByText('chip')).toBeTruthy();

    render(<RumMetricCard label="LCP" value="1.2s" tone="success" />);
    expect(screen.getByText('LCP')).toBeTruthy();
  });

  it('TrafficScopeControl mounts with current traffic and RumIconAction clicks', () => {
    const onChange = vi.fn();
    const onClick = vi.fn();
    render(<TrafficScopeControl onChange={onChange} />);
    expect(screen.getByText('visitors')).toBeTruthy();

    render(<RumIconAction title="编辑" onClick={onClick} />);
    fireEvent.click(screen.getByLabelText('编辑'));
    expect(onClick).toHaveBeenCalled();
  });
});
