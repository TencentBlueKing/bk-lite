import React from 'react';
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from 'antd';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import { formatDateTime } from '@/app/apm/components/metric-format';
import ApmServicesPage from '../page';

const api = {
  getApplications: vi.fn(),
  getEvents: vi.fn(),
  getHealth: vi.fn(),
  getServiceRed: vi.fn(),
  getServices: vi.fn(),
  getSlos: vi.fn(),
  getTopology: vi.fn(),
  setServiceArchived: vi.fn(),
  setServiceOrganizations: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/apm/services',
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ flatGroups: [{ id: 1, name: 'Default' }] }),
}));
vi.mock('@/components/permission', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/app/apm/components/organization-assignment-modal', () => ({ default: () => null }));
const serviceWithEnv = {
  id: 'service-bklite',
  application_id: 'bklite',
  application_name: 'bklite',
  namespace: 'bklite',
  name: 'bklite-server',
  language: 'java',
  first_seen_at: '2026-07-31T06:25:01Z',
  last_seen_at: '2026-07-31T06:25:01Z',
  archived_at: null,
  archive_reason: '',
  status: 'active' as const,
  environment_views: [{ environment: 'production', last_seen_at: '2026-07-31T06:25:01Z', status: 'active' as const }],
  organization_ids: [1],
};

const archivedService = {
  ...serviceWithEnv,
  id: 'service-archived',
  name: 'legacy-server',
  archived_at: '2026-07-01T00:00:00Z',
  archive_reason: 'manual',
  status: 'archived' as const,
  environment_views: [{ environment: 'production', last_seen_at: '2026-06-01T00:00:00Z', status: 'archived' as const }],
};

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getApplications.mockResolvedValue([
    {
      id: 'builtin',
      application_id: '',
      name: '未归类应用',
      description: '未设置 service.namespace 的服务',
      is_builtin: true,
      service_count: 0,
      organization_ids: [1],
      created_at: '2026-08-05T00:00:00Z',
      updated_at: '2026-08-05T00:00:00Z',
      created_by: 'migration',
      updated_by: 'migration',
    },
    {
      id: 'bklite',
      application_id: 'bklite',
      name: '电商应用',
      description: '',
      is_builtin: false,
      service_count: 1,
      organization_ids: [1],
      created_at: '2026-08-05T00:00:00Z',
      updated_at: '2026-08-05T00:00:00Z',
      created_by: 'admin',
      updated_by: 'admin',
    },
  ]);
  api.getServices.mockResolvedValue([serviceWithEnv, archivedService]);
  api.getHealth.mockResolvedValue({ catalog_reconcile: { status: 'healthy' } });
  api.getServiceRed.mockResolvedValue({
    service_id: 'service-bklite',
    environment: 'production',
    started_at: '2026-07-31T05:25:01Z',
    ended_at: '2026-07-31T06:25:01Z',
    request_rate: 12.5,
    error_rate: 0.02,
    p95_ms: 80,
    p99_ms: 120,
    timeseries: [
      { timestamp: '2026-07-31T05:30:00Z', request_rate: 10, error_rate: 0.01, p95_ms: 70, p99_ms: 100 },
      { timestamp: '2026-07-31T06:00:00Z', request_rate: 15, error_rate: 0.03, p95_ms: 90, p99_ms: 140 },
    ],
    top_endpoints: [],
  });
  api.getEvents.mockResolvedValue([
    {
      id: 'evt-1',
      event_id: 'evt-1',
      external_id: 'ext-1',
      title: '错误率升高',
      description: '',
      severity: 'critical',
      action: 'triggered',
      status: 'active',
      service: 'bklite-server',
      item: 'error_rate',
      value: 0.2,
      resource_id: 'r1',
      resource_name: 'bklite-server',
      start_time: '2026-07-31T06:00:00Z',
      end_time: null,
      received_at: '2026-07-31T06:00:00Z',
      policy_id: 'p1',
      environment: 'production',
      notification_deliveries: [],
    },
  ]);
  api.getSlos.mockResolvedValue([
    {
      id: 'slo-1',
      name: '可用性',
      service_id: 'service-bklite',
      environment: 'production',
      endpoint: '',
      sli_type: 'availability',
      objective: '99',
      evaluation_window: 'rolling7d',
      is_enabled: true,
      service_namespace: 'bklite',
      service_name: 'bklite-server',
      current_rate: 78.785,
      budget_remaining: 0,
      data_state: 'available',
      started_at: null,
      ended_at: '2026-07-31T06:25:01Z',
      created_at: '2026-07-01T00:00:00Z',
      updated_at: '2026-07-31T06:25:01Z',
      created_by: 'admin',
      updated_by: 'admin',
    },
  ]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 服务目录应用视角', () => {
  it('不展示已移除的内置未归类应用', async () => {
    api.getServices.mockResolvedValue([]);
    renderWithApmIntl(<ApmServicesPage />);

    await waitFor(() => expect(api.getApplications).toHaveBeenCalled());
    expect(screen.queryByText('未归类应用')).toBeNull();
  });

  it('应用卡展示吞吐、最高活跃告警、应用详情与服务下钻入口', async () => {
    renderWithApmIntl(<ApmServicesPage />);

    const card = await screen.findByRole('link', { name: '查看应用 电商应用 详情' });
    expect(card.getAttribute('href')).toBe('/apm/services/applications/bklite');
    const cardArticle = card.closest('article');
    expect(cardArticle).not.toBeNull();
    await waitFor(() => expect(within(cardArticle!).getByText('12.5')).not.toBeNull());
    expect(within(cardArticle!).getByText('2.00%')).not.toBeNull();
    const statusTag = within(cardArticle!).getByLabelText('最高活跃告警：严重');
    expect(statusTag.classList.contains('ant-tag')).toBe(true);
    const servicesLink = within(cardArticle!).getByRole('link', { name: '应用内 1 个服务，查看服务' });
    expect(card.contains(servicesLink)).toBe(false);
    expect(servicesLink.getAttribute('href')).toBe(
      '/apm/services?perspective=service&namespace=bklite'
    );
    expect(within(cardArticle!).queryByText(/个服务/)).toBeNull();
    expect(within(cardArticle!).getByText(/应用 · 1h/)).not.toBeNull();
    expect(screen.getByRole('radiogroup', { name: '服务指标时间窗口' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: /已归档/ })).toBeNull();
    expect(within(cardArticle!).getByTitle('吞吐量趋势')).not.toBeNull();
    expect(within(cardArticle!).getByTitle('错误率趋势')).not.toBeNull();
    const alertLink = within(cardArticle!).getByRole('link', { name: /应用内 1 个活跃告警/ });
    expect(card.contains(alertLink)).toBe(false);
    expect(alertLink.getAttribute('href')).toBe('/apm/events/alerts?service=bklite-server');
  });

  it('选择 7d 窗口仍查询 RED 而不是让全部 KPI 失败', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServicesPage />);
    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalled());
    api.getServiceRed.mockClear();

    await user.click(screen.getByRole('radio', { name: '7d' }).closest('label')!);

    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalled());
    const startedAt = api.getServiceRed.mock.calls[0][2] as string;
    const endedAt = api.getServiceRed.mock.calls[0][3] as string;
    expect(new Date(endedAt).getTime() - new Date(startedAt).getTime()).toBeGreaterThan(6 * 24 * 60 * 60 * 1000);
    expect(screen.queryByText('RED 指标查询失败')).toBeNull();
    expect(api.getTopology).not.toHaveBeenCalled();
  });
});

describe('APM 服务目录服务视角与归档', () => {
  it('切换到服务视角后展示 RED、SLO、语言与最高活跃告警', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServicesPage />);

    const servicePerspective = await screen.findByRole('radio', { name: '服务' });
    await user.click(servicePerspective.closest('label')!);

    expect((await screen.findAllByText('吞吐量（请求/秒）')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('错误率').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('OpenTelemetry SDK 语言：Java')).not.toBeNull();
    expect(screen.getByLabelText('最高活跃告警：严重')).not.toBeNull();
    expect(screen.getByRole('link', { name: 'bklite-server' }).getAttribute('href')).toBe(
      '/apm/services/service-bklite?environment=production&window=1h'
    );
    expect(
      screen.getByRole('link', { name: /bklite-server 有 1 个活跃告警/ }).getAttribute('href')
    ).toBe('/apm/events/alerts?service=bklite-server&environment=production');
    await waitFor(() => expect(screen.getAllByText('12.5').length).toBeGreaterThan(0));
    expect(screen.getAllByText('2.00%').length).toBeGreaterThan(0);
    expect(screen.getByText('未达标 78.8%')).not.toBeNull();
    const searchInput = screen.getByRole('textbox', { name: '按应用或服务名称搜索' });
    const serviceHeader = screen.getByRole('columnheader', { name: '服务' });
    const actionHeader = screen.getByRole('columnheader', { name: '操作' });
    expect(searchInput.closest('section')).toBe(serviceHeader.closest('section'));
    expect(getComputedStyle(actionHeader).textAlign).toBe('left');
    expect(actionHeader.classList.contains('ant-table-cell-fix-right')).toBe(true);
    expect(screen.getByRole('button', { name: '调整组织' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '归档' })).not.toBeNull();
    expect(screen.getByRole('button', { name: /已归档/ })).not.toBeNull();
    expect(screen.getByRole('radiogroup', { name: '服务指标时间窗口' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: /更多操作/ })).toBeNull();
    expect(screen.queryByText('全部服务')).toBeNull();
    expect(screen.queryByText(/个环境视图/)).toBeNull();
    const lastSeenText = formatDateTime(serviceWithEnv.environment_views[0].last_seen_at, false);
    const lastSeen = screen.getByText(lastSeenText);
    expect(lastSeen.closest('td')?.textContent).toBe(lastSeenText);
    expect(lastSeen.getAttribute('title')).toBe(
      formatDateTime(serviceWithEnv.environment_views[0].last_seen_at)
    );
  });

  it('在手机宽度把服务治理操作收进更多菜单', async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServicesPage />);

    const servicePerspective = await screen.findByRole('radio', { name: '服务' });
    await user.click(servicePerspective.closest('label')!);

    const moreActions = await screen.findByRole('button', { name: '更多操作' });
    expect(screen.queryByRole('button', { name: '调整组织' })).toBeNull();
    expect(screen.queryByRole('button', { name: '归档' })).toBeNull();

    await user.click(moreActions);
    expect(await screen.findByText('调整组织')).not.toBeNull();
    expect(screen.getByText('归档')).not.toBeNull();
  });

  it('已归档入口打开抽屉并列出归档服务', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServicesPage />);

    const servicePerspective = await screen.findByRole('radio', { name: '服务' });
    await user.click(servicePerspective.closest('label')!);
    await user.click(await screen.findByRole('button', { name: /已归档/ }));

    expect(await screen.findByText('已归档服务')).not.toBeNull();
    expect(screen.getByText('legacy-server')).not.toBeNull();
    expect(screen.getByText('手动归档')).not.toBeNull();
  });

  it('勾选多个服务后可批量归档', async () => {
    const checkout = {
      ...serviceWithEnv,
      id: 'service-checkout',
      name: 'checkout-service',
      language: 'go',
    };
    api.getServices.mockResolvedValue([serviceWithEnv, checkout, archivedService]);
    api.setServiceArchived.mockResolvedValue({});
    const confirmSpy = vi.spyOn(Modal, 'confirm').mockImplementation((config) => {
      void Promise.resolve(config.onOk?.());
      return { destroy: vi.fn(), update: vi.fn() } as ReturnType<typeof Modal.confirm>;
    });
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServicesPage />);

    const servicePerspective = await screen.findByRole('radio', { name: '服务' });
    await user.click(servicePerspective.closest('label')!);
    await screen.findByText('bklite-server');
    await screen.findByText('checkout-service');
    expect((screen.getByRole('button', { name: '批量操作' }) as HTMLButtonElement).disabled).toBe(true);

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    const batchButton = screen.getByRole('button', { name: '批量操作' }) as HTMLButtonElement;
    expect(batchButton.disabled).toBe(false);
    await user.click(batchButton);
    await user.click(await screen.findByRole('menuitem', { name: '归档' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(String(confirmSpy.mock.calls[0][0].title)).toContain('2');
    await waitFor(() => {
      expect(api.setServiceArchived).toHaveBeenCalledTimes(2);
    });
    expect(api.setServiceArchived).toHaveBeenCalledWith('service-bklite', true);
    expect(api.setServiceArchived).toHaveBeenCalledWith('service-checkout', true);
    confirmSpy.mockRestore();
  }, 15_000);
});
