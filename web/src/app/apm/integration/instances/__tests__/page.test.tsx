import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import { formatDateTime } from '@/app/apm/components/metric-format';
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

    expect(columnWidths).toEqual(['', '', '', '112px', '112px', '168px', '168px', '96px', '160px', '96px']);
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
    const lastSeenText = formatDateTime(activeInstance.last_seen_at, false);
    const lastSeen = screen.getByText(lastSeenText);
    expect(lastSeen.closest('td')?.textContent).toBe(lastSeenText);
    expect(lastSeen.getAttribute('title')).toBe(formatDateTime(activeInstance.last_seen_at));
    expect(screen.getByRole('columnheader', { name: '所属组织' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '调整组织' })).not.toBeNull();
  });

  it('实例状态只保留活跃和静默，不再暴露归档产品概念', async () => {
    renderPage();
    await screen.findByText('pod-a');

    expect(screen.queryByText('已归档')).toBeNull();
    expect(api.getInstancePage).not.toHaveBeenCalledWith(expect.objectContaining({ include_archived: expect.anything() }));
    expect(screen.queryByRole('button', { name: /归档|恢复/ })).toBeNull();
  });
});
