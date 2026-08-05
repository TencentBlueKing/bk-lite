import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmServicesPage from '../page';

const api = {
  getApplications: vi.fn(),
  getHealth: vi.fn(),
  getServiceRed: vi.fn(),
  getServices: vi.fn(),
  setServiceArchived: vi.fn(),
  setServiceOrganizations: vi.fn(),
  isLoading: false,
};

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

beforeEach(() => {
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
  api.getServices.mockResolvedValue([
    {
      id: 'service-bklite',
      application_id: 'bklite',
      application_name: 'bklite',
      namespace: 'bklite',
      name: 'bklite-server',
      first_seen_at: '2026-07-31T06:25:01Z',
      last_seen_at: '2026-07-31T06:25:01Z',
      archived_at: null,
      archive_reason: '',
      status: 'silent',
      environment_views: [],
      organization_ids: [1],
    },
  ]);
  api.getHealth.mockResolvedValue({ catalog_reconcile: { status: 'healthy' } });
  api.getServiceRed.mockResolvedValue({});
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 服务目录应用视角', () => {
  it('即使尚未发现服务也显示内置未归类应用', async () => {
    render(<ApmServicesPage />);

    const builtinCard = await screen.findByRole('button', { name: '查看应用 未归类应用 下的服务' });
    expect(within(builtinCard).getByText(/0 个服务/)).not.toBeNull();
  });

  it('将内置未归类应用稳定排在普通应用之后', async () => {
    render(<ApmServicesPage />);

    const applicationCards = await screen.findAllByRole('button', { name: /查看应用 .* 下的服务/ });
    expect(applicationCards.map((card) => card.getAttribute('aria-label'))).toEqual([
      '查看应用 未归类应用测试 下的服务',
      '查看应用 未归类应用 下的服务',
    ]);
  });
});
