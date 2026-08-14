import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import dayjs from 'dayjs';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmIntegrationInstancesPage from '../page';

const api = {
  getApplications: vi.fn(),
  getHealth: vi.fn(),
  getInstancePage: vi.fn(),
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
  return renderWithApmIntl(<ApmIntegrationInstancesPage />);
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
    expect(screen.queryByText('默认显示活跃实例；切换状态或时间范围可查看静默、归档与历史实例。')).toBeNull();
    expect(screen.getByText('已接入 1 个实例').nextElementSibling).toBe(
      document.querySelector('[aria-label="接入上报时间范围"]')
    );
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

  it('按身份、归属、运行上下文、生命周期和治理操作组织表格列', async () => {
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
    renderPage();

    await screen.findByText('pod-a');
    const columnWidths = Array.from(document.querySelectorAll('.ant-table colgroup col'))
      .map((column) => (column as HTMLElement).style.width);

    expect(columnWidths).toEqual(['13%', '18%', '12%', '7%', '6%', '11%', '12%', '8%', '7%', '112px']);
    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      '实例 ID',
      '服务',
      '所属应用',
      '环境',
      '版本',
      '首次接入',
      '最近上报',
      '实例状态',
      '所属组织',
      '操作',
    ]);
    expect(getComputedStyle(screen.getByRole('columnheader', { name: '首次接入' })).textAlign).toBe('left');
    expect(getComputedStyle(screen.getByRole('columnheader', { name: '最近上报' })).textAlign).toBe('left');
    expect(getComputedStyle(screen.getByRole('columnheader', { name: '实例状态' })).textAlign).toBe('left');
    const actionHeader = screen.getByRole('columnheader', { name: '操作' });
    expect(getComputedStyle(actionHeader).textAlign).toBe('left');
    expect(actionHeader.classList.contains('ant-table-cell-fix-right')).toBe(true);
    const lastSeenText = dayjs(activeInstance.last_seen_at).format('YYYY-MM-DD HH:mm');
    const lastSeen = screen.getByText(lastSeenText);
    expect(lastSeen.closest('td')?.textContent).toBe(lastSeenText);
    expect(lastSeen.getAttribute('title')).toBe(dayjs(activeInstance.last_seen_at).format('YYYY-MM-DD HH:mm:ss'));
    expect(screen.getByRole('columnheader', { name: '所属组织' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '调整组织' })).not.toBeNull();
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
    expect(screen.queryByRole('button', { name: /归档|恢复/ })).toBeNull();
  });
});
