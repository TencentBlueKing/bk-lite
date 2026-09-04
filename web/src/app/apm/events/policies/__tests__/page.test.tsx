import React from 'react';
import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ApmPoliciesPage from '../page';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import { formatDateTime } from '@/app/apm/components/metric-format';

const policy = {
  id: 'policy-1',
  name: '结账接口 P95 过慢',
  service_id: 'svc-1',
  service_namespace: 'shop',
  service_name: 'checkout',
  environment: 'production',
  alert_name: '',
  endpoints: ['POST /checkout'],
  version_mode: 'specific' as const,
  versions: ['v2'],
  metric_type: 'p95' as const,
  evaluation_interval: 1,
  metric_window: 5,
  aggregation: 'max' as const,
  thresholds: [{ severity: 'warning' as const, comparator: 'gt' as const, value: '500' }],
  trigger_after: 3,
  recover_after: 3,
  no_data_after: null,
  no_data_severity: '' as const,
  notification_targets: [],
  is_enabled: true,
  state: {
    status: 'active' as const,
    consecutive_hits: 0,
    consecutive_recoveries: 0,
    last_succeeded_at: '2026-08-14T02:00:00Z',
    last_failed_at: null,
  },
  created_at: '2026-08-11T12:03:00Z',
  updated_at: '2026-08-14T02:00:00Z',
  created_by: 'admin',
  updated_by: 'admin',
};
const api = { deletePolicy: vi.fn(), getPolicies: vi.fn(), isLoading: false, setPolicyEnabled: vi.fn() };

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

beforeEach(() => {
  window.matchMedia = vi
    .fn()
    .mockReturnValue({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
  api.getPolicies.mockResolvedValue([policy]);
  api.setPolicyEnabled.mockResolvedValue({ ...policy, is_enabled: false });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 策略列表', () => {
  it('空列表只展示策略空态，不复用 APM 总述', async () => {
    api.getPolicies.mockResolvedValue([]);
    renderWithApmIntl(<ApmPoliciesPage />);

    expect(await screen.findByText('暂无告警策略')).not.toBeNull();
    expect(screen.queryByText('当前范围暂无 APM 数据')).toBeNull();
    expect(screen.queryByText('暂无数据')).toBeNull();
    expect(screen.queryByRole('button', { name: '重新加载' })).toBeNull();
  });

  it('按原型展示策略名称、服务、审计时间和启停操作列', async () => {
    renderWithApmIntl(<ApmPoliciesPage />);
    await screen.findByText('结账接口 P95 过慢');

    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      '策略名称',
      '服务',
      '创建人',
      '创建时间',
      '执行时间',
      '启停',
      '操作',
    ]);
    expect(screen.getByText('checkout')).not.toBeNull();
    expect(screen.getByText('POST /checkout')).not.toBeNull();
    expect(screen.getByText('admin')).not.toBeNull();
    expect(screen.getByText(formatDateTime(policy.created_at, false))).not.toBeNull();
    expect(screen.getByText(formatDateTime(policy.state.last_succeeded_at, false))).not.toBeNull();
    expect(screen.queryByRole('columnheader', { name: '环境' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '端点 / 版本' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '告警条件' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '状态' })).toBeNull();
  });

  it('最近评估失败时不把失败显示成普通执行时间', async () => {
    api.getPolicies.mockResolvedValue([
      {
        ...policy,
        state: {
          ...policy.state,
          last_succeeded_at: '2026-08-14T01:00:00Z',
          last_failed_at: '2026-08-14T02:10:00Z',
        },
      },
    ]);
    renderWithApmIntl(<ApmPoliciesPage />);
    expect(await screen.findByText(/评估失败/)).not.toBeNull();
  });

  it('新建和编辑使用独立路由，启停只保留在列表', async () => {
    renderWithApmIntl(<ApmPoliciesPage />);
    expect(await screen.findByText('结账接口 P95 过慢')).not.toBeNull();
    expect(screen.getByRole('link', { name: /新建策略/ }).getAttribute('href')).toBe('/apm/events/policies/new');
    expect(screen.getByRole('button', { name: '结账接口 P95 过慢：编辑策略' }).closest('a')?.getAttribute('href')).toBe(
      '/apm/events/policies/policy-1',
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('列表启停调用专用操作接口', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPoliciesPage />);
    await screen.findByText('结账接口 P95 过慢');
    await user.click(screen.getByRole('switch'));
    expect(api.setPolicyEnabled).toHaveBeenCalledWith('policy-1', false);
  });
});
