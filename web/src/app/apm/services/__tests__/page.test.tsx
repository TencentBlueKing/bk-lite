import React from 'react';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmServicesPage from '../page';

const api = {
  getApplications: vi.fn(),
  getEvents: vi.fn(),
  getHealth: vi.fn(),
  getServiceRed: vi.fn(),
  getServices: vi.fn(),
  getSlos: vi.fn(),
  setServiceArchived: vi.fn(),
  setServiceOrganizations: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
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
    matches: false,
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
      name: '未归类应用测试',
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
      action: 'created',
      status: 'firing',
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
      objective: '0.99',
      evaluation_window: 'rolling7d',
      is_enabled: true,
      service_namespace: 'bklite',
      service_name: 'bklite-server',
      current_rate: 0.995,
      budget_remaining: 0.8,
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
  it('即使尚未发现服务也显示内置未归类应用', async () => {
    api.getServices.mockResolvedValue([]);
    render(<ApmServicesPage />);

    const builtinCard = await screen.findByRole('button', { name: '查看应用 未归类应用 下的服务' });
    expect(within(builtinCard).getByText(/0 个服务/)).not.toBeNull();
  });

  it('将内置未归类应用稳定排在普通应用之后', async () => {
    api.getServices.mockResolvedValue([]);
    render(<ApmServicesPage />);

    const applicationCards = await screen.findAllByRole('button', { name: /查看应用 .* 下的服务/ });
    expect(applicationCards.map((card) => card.getAttribute('aria-label'))).toEqual([
      '查看应用 未归类应用测试 下的服务',
      '查看应用 未归类应用 下的服务',
    ]);
  });

  it('应用卡展示吞吐与告警徽标', async () => {
    render(<ApmServicesPage />);

    const card = await screen.findByRole('button', { name: '查看应用 未归类应用测试 下的服务' });
    await waitFor(() => expect(within(card).getByText('12.5')).not.toBeNull());
    expect(within(card).getByText('2.00%')).not.toBeNull();
    expect(within(card).getByTitle('应用内 1 个活跃告警')).not.toBeNull();
  });
});

describe('APM 服务目录服务视角与归档', () => {
  it('切换到服务视角后展示 RED 列与服务链接', async () => {
    const user = userEvent.setup();
    render(<ApmServicesPage />);

    await user.click(await screen.findByRole('button', { name: '查看应用 未归类应用测试 下的服务' }));

    expect((await screen.findAllByText('吞吐量(/s)')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('错误率').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'bklite-server' }).getAttribute('href')).toBe(
      '/apm/services/service-bklite?environment=production'
    );
    await waitFor(() => expect(screen.getAllByText('12.5').length).toBeGreaterThan(0));
    expect(screen.getAllByText('2.00%').length).toBeGreaterThan(0);
  });

  it('已归档入口打开抽屉并列出归档服务', async () => {
    const user = userEvent.setup();
    render(<ApmServicesPage />);

    await screen.findByRole('button', { name: '查看应用 未归类应用测试 下的服务' });
    await user.click(screen.getByRole('button', { name: /已归档/ }));

    expect(await screen.findByText('已归档服务')).not.toBeNull();
    expect(screen.getByText('legacy-server')).not.toBeNull();
    expect(screen.getByText('手动归档')).not.toBeNull();
  });
});
