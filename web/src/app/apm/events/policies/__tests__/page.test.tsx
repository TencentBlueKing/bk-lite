import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmPoliciesPage from '../page';

const tableMessages = {
  'common.total': '共',
  'common.items': '条',
  'common.checked': '已选',
  'common.confirm': '确认',
  'common.cancel': '取消',
  'common.searchPlaceHolder': '搜索字段',
  'common.selectAll': '全选',
  'common.selected': '已选',
  'common.clear': '清空',
  'common.pin': '固定',
  'common.unpin': '取消固定',
  'cutomTable.fieldSetting': '字段设置',
  'cutomTable.pinHint': '固定字段会显示在表格左侧',
};

const api = {
  createPolicy: vi.fn(),
  deletePolicy: vi.fn(),
  getNotificationChannels: vi.fn(),
  getNotificationRecipients: vi.fn(),
  getPolicies: vi.fn(),
  getServices: vi.fn(),
  isLoading: false,
  setPolicyEnabled: vi.fn(),
  updatePolicy: vi.fn(),
};

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children, className, padding }: { children: React.ReactNode; className?: string; padding?: string }) => (
    <section className={className} data-padding={padding}>{children}</section>
  ),
}));

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
  api.getNotificationChannels.mockResolvedValue([]);
  api.getNotificationRecipients.mockResolvedValue([]);
  api.getServices.mockResolvedValue([{
    id: 'svc-1',
    application_id: 'shop',
    application_name: 'shop',
    namespace: 'shop',
    name: 'checkout',
    first_seen_at: '2026-08-05T00:00:00Z',
    last_seen_at: '2026-08-06T02:00:00Z',
    archived_at: null,
    archive_reason: '',
    status: 'active',
    environment_views: [{ environment: 'prod', last_seen_at: '2026-08-06T02:00:00Z', status: 'active' }],
    organization_ids: [1],
  }]);
  api.getPolicies.mockResolvedValue([{
    id: 'policy-1',
    name: '结账接口 P95 过慢',
    service_id: 'svc-1',
    service_namespace: 'shop',
    service_name: 'checkout',
    environment: 'prod',
    metric_type: 'p95',
    comparator: 'gt',
    threshold: '500',
    duration_window: 3,
    recovery_window: 3,
    severity: 'warning',
    notification_targets: [],
    is_enabled: true,
    state: {
      status: 'firing',
      consecutive_hits: 2,
      consecutive_recoveries: 0,
      last_succeeded_at: '2026-08-13T07:53:00Z',
      last_failed_at: null,
    },
    created_at: '2026-08-11T12:03:00Z',
    updated_at: '2026-08-13T07:53:00Z',
    created_by: 'admin',
    updated_by: 'admin',
  }]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 告警策略列表', () => {
  it('用紧凑工具栏和语义对齐的自适应列取代拼凑式表头', async () => {
    render(
      <IntlProvider locale="zh" messages={tableMessages}>
        <ApmPoliciesPage />
      </IntlProvider>,
    );

    expect(await screen.findByText('结账接口 P95 过慢')).not.toBeNull();
    const listTitle = screen.getByText('策略列表');
    expect(screen.queryByText('1 条告警中')).toBeNull();
    expect(screen.queryByText(/每分钟评估/)).toBeNull();
    expect(listTitle.closest('div')?.className).toContain('py-2');
    expect(listTitle.closest('section')?.getAttribute('data-padding')).toBe('none');

    const columnWidths = Array.from(document.querySelectorAll('.ant-table colgroup col'))
      .map((column) => (column as HTMLElement).style.width);
    expect(columnWidths).toEqual(['38%', '12%', '16%', '16%', '8%', '10%']);
    expect(getComputedStyle(screen.getByRole('columnheader', { name: '启用状态' })).textAlign).toBe('center');
    expect(getComputedStyle(screen.getByRole('columnheader', { name: '操作' })).textAlign).toBe('right');
  });

  it('通过弹窗新建策略而不是跳转独立页面', async () => {
    const user = userEvent.setup();
    render(
      <IntlProvider locale="zh" messages={tableMessages}>
        <ApmPoliciesPage />
      </IntlProvider>,
    );
    await screen.findByText('结账接口 P95 过慢');

    const createButton = screen.getByRole('button', { name: '新建策略' });
    expect(createButton.closest('a')).toBeNull();
    await user.click(createButton);

    expect(await screen.findByRole('dialog', { name: '新建 APM 策略' })).not.toBeNull();
    expect(screen.getByLabelText('策略名称')).not.toBeNull();
  });
});
