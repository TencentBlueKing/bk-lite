import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmIntegrationInstancesPage from '../page';

const api = {
  getApplications: vi.fn(),
  getHealth: vi.fn(),
  getInstancePage: vi.fn(),
  setInstanceArchived: vi.fn(),
  setInstanceOrganizations: vi.fn(),
  isLoading: false,
};

vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/permission', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ flatGroups: [] }) }));

const activeInstance = {
  id: 'instance-a',
  service_namespace: 'shop',
  service_name: 'checkout',
  instance_id: 'pod-a',
  environment: 'prod',
  version: '1.0.0',
  application_id: 'shop',
  application_name: '电商应用',
  permission_mode: 'inherited' as const,
  first_seen_at: '2026-08-05T00:00:00Z',
  last_seen_at: '2026-08-05T01:00:00Z',
  archived_at: null,
  archive_reason: '',
  status: 'active' as const,
  organization_ids: [10],
};

function renderPage() {
  return render(
    // @ts-expect-error react-intl type incompatibility with React 19
    <IntlProvider
      locale="zh"
      messages={{
        'apm.instances.defaultActiveHelp': '默认显示活跃实例；切换状态或时间范围可查看静默、归档与历史实例。',
      }}
    >
      <ApmIntegrationInstancesPage />
    </IntlProvider>
  );
}

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
    { id: 'app-a', application_id: 'shop', name: '电商应用', is_builtin: false, organization_ids: [10] },
  ]);
  api.getHealth.mockResolvedValue({ catalog_reconcile: { status: 'ok' } });
  api.getInstancePage.mockResolvedValue({ count: 1, items: [activeInstance] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 接入实例目录', () => {
  it('默认通过有界服务端分页只加载活跃实例', async () => {
    renderPage();

    await screen.findByText('pod-a');
    expect(screen.getByText('默认显示活跃实例；切换状态或时间范围可查看静默、归档与历史实例。')).not.toBeNull();
    await waitFor(() => expect(api.getInstancePage).toHaveBeenCalledWith(expect.objectContaining({
      page: 1,
      page_size: 20,
      status: 'active',
      include_archived: false,
      started_at: expect.any(String),
      ended_at: expect.any(String),
    })));
    expect(screen.getByRole('combobox', { name: '按实例状态筛选' }).getAttribute('aria-expanded')).toBe('false');
  });

  it('可显式切换到归档实例并交由服务端过滤', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('pod-a');

    await user.click(screen.getByRole('combobox', { name: '按实例状态筛选' }));
    await user.click(await screen.findByText('已归档'));

    await waitFor(() => expect(api.getInstancePage).toHaveBeenLastCalledWith(expect.objectContaining({
      page: 1,
      status: 'archived',
      include_archived: true,
    })));
  });
});
