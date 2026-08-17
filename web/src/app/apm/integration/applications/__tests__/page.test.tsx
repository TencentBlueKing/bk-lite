import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmApplicationsPage from '../page';

const api = {
  getApplications: vi.fn(),
  createApplication: vi.fn(),
  updateApplication: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-data-table', () => ({
  APM_TABLE_COLUMN_WIDTHS: {
    actionGroup: 168,
    organization: 160,
    status: 96,
    timestamp: 168,
  },
  default: ({ columns, dataSource }: {
    columns: Array<{ key?: string; fixed?: string; render?: (_: unknown, item: { id: string; name: string; application_id: string }) => React.ReactNode }>;
    dataSource: Array<{ id: string; name: string; application_id: string }>;
  }) => (
    <div data-testid="application-table">
      {dataSource.map((item) => (
        <div key={item.id}>
          <span>{item.name}</span>
          <div data-fixed={columns.find((column) => column.key === 'action')?.fixed}>
            {columns.find((column) => column.key === 'action')?.render?.(undefined, item)}
          </div>
        </div>
      ))}
    </div>
  ),
}));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/group-tree-select', () => ({
  default: () => <div data-testid="group-tree-select" />,
}));
vi.mock('@/components/permission', () => ({
  default: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <span className={className}>{children}</span>
  ),
}));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ flatGroups: [{ id: 10, name: 'Default' }] }),
}));

const application = {
  id: 'application-a',
  application_id: 'shop',
  name: '演示应用',
  description: '演示说明',
  is_builtin: false,
  service_count: 3,
  organization_ids: [10],
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-13T00:00:00Z',
  created_by: 'admin',
  updated_by: 'admin',
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
  api.getApplications.mockResolvedValue([application]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 应用管理', () => {
  it('移除重复总数并将创建应用作为右侧主操作', async () => {
    renderWithApmIntl(<ApmApplicationsPage />);

    await screen.findByText('演示应用');
    expect(screen.queryByText('共 1 个应用')).toBeNull();

    const createButton = screen.getByRole('button', { name: '创建应用' });
    expect(createButton.parentElement?.classList.contains('ml-auto')).toBe(true);
  });

  it('直接展示高频行操作并固定在表格右侧', async () => {
    renderWithApmIntl(<ApmApplicationsPage />);

    await screen.findByText('演示应用');
    expect(screen.getByRole('button', { name: '添加接入' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '查看详情' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '编辑' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: /更多操作/ })).toBeNull();
    expect(document.querySelector('[data-fixed="right"]')).not.toBeNull();
  });

  it('使用抽屉承载创建应用表单', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmApplicationsPage />);
    await screen.findByText('演示应用');

    await user.click(screen.getByRole('button', { name: '创建应用' }));

    await waitFor(() => expect(document.querySelector('.ant-drawer')).not.toBeNull());
    expect(document.querySelector('.ant-modal')).toBeNull();
    expect(document.querySelector('.ant-drawer-title')?.textContent).toBe('创建应用');
    expect(document.querySelector('form#apm-application-form')).not.toBeNull();
    expect(screen.getByRole('button', { name: /^创\s*建$/ }).getAttribute('form')).toBe('apm-application-form');
  });
});
