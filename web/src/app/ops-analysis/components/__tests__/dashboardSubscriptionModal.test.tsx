import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { DashboardSubscription } from '@/app/ops-analysis/types/dashboardSubscription';
import DashboardSubscriptionModal from '../dashboardSubscriptionModal';

const api = {
  listSubscriptions: vi.fn(),
  createSubscription: vi.fn(),
  updateSubscription: vi.fn(),
  deleteSubscription: vi.fn(),
  executeSubscription: vi.fn(),
};

const makeSubscription = (
  overrides: Partial<DashboardSubscription> = {},
): DashboardSubscription => ({
  id: 1,
  dashboard: 8,
  creator: 'test',
  name: '日报',
  status: 'active' as const,
  recipient_email: 'ops@example.com',
  config: {},
  created_at: '2026-07-28T00:00:00Z',
  updated_at: '2026-07-28T00:00:00Z',
  ...overrides,
});

vi.mock('@/app/ops-analysis/api/dashboardSubscription', () => ({
  useDashboardSubscriptionApi: () => api,
}));

const translate = (key: string) =>
  ({
    'dashboard.subscriptionTitle': '报告订阅',
    'dashboard.subscriptionCreate': '创建订阅',
    'dashboard.subscriptionName': '订阅名称',
    'dashboard.subscriptionEmail': '接收邮箱',
    'dashboard.subscriptionSave': '保存',
    'dashboard.subscriptionCreateFailed': '创建订阅失败',
    'dashboard.subscriptionEmpty': '暂无报告订阅',
    'dashboard.subscriptionStatus': '订阅状态',
    'dashboard.subscriptionStatusActive': '启用',
    'dashboard.subscriptionStatusPaused': '暂停',
    'dashboard.subscriptionDeleteConfirm': '确认删除该报告订阅？',
    'dashboard.subscriptionExecute': '立即测试',
    'dashboard.subscriptionExecuteCreated': '测试执行已创建',
    'dashboard.subscriptionExecuteFailed': '测试执行创建失败',
    'common.edit': '编辑',
    'common.delete': '删除',
    'common.cancel': '取消',
  })[key] ?? key;

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: translate,
  }),
}));

beforeEach(() => {
  api.listSubscriptions.mockResolvedValue([]);
  api.createSubscription.mockResolvedValue(makeSubscription());
  api.executeSubscription.mockResolvedValue({
    id: 10,
    subscription: 1,
    dashboard: 8,
    creator: 'test',
    status: 'succeeded',
    trigger_type: 'manual',
    failure_stage: '',
    error_message: '',
    created_at: '2026-07-28T00:00:00Z',
    started_at: '2026-07-28T00:00:00Z',
    finished_at: '2026-07-28T00:00:01Z',
  });
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DashboardSubscriptionModal', () => {
  it('opens the create form and submits a subscription', async () => {
    const user = userEvent.setup();
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    await user.click(
      await screen.findByRole('button', { name: '创建订阅' }),
    );
    await user.type(screen.getByLabelText('订阅名称'), '日报');
    await user.type(screen.getByLabelText('接收邮箱'), 'ops@example.com');
    await user.click(
      screen.getByRole('button', { name: /保\s*存/ }),
    );

    await waitFor(() => {
      expect(api.createSubscription).toHaveBeenCalledWith({
        dashboard: 8,
        name: '日报',
        recipient_email: 'ops@example.com',
        status: 'active',
      });
    });
  });

  it('shows an error when creation fails', async () => {
    api.createSubscription.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    await user.click(
      await screen.findByRole('button', { name: '创建订阅' }),
    );
    await user.type(screen.getByLabelText('订阅名称'), '日报');
    await user.type(screen.getByLabelText('接收邮箱'), 'ops@example.com');
    await user.click(
      screen.getByRole('button', { name: /保\s*存/ }),
    );

    expect(await screen.findByText('创建订阅失败')).not.toBeNull();
  });

  it('lists status and edits an existing subscription', async () => {
    const subscription = makeSubscription();
    api.listSubscriptions.mockResolvedValue([subscription]);
    api.updateSubscription.mockResolvedValue({
      ...subscription,
      name: '周报',
    });
    const user = userEvent.setup();
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText('日报')).not.toBeNull();
    expect(screen.getByText('启用')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '编辑' }));
    const nameInput = screen.getByLabelText('订阅名称');
    await user.clear(nameInput);
    await user.type(nameInput, '周报');
    await user.click(
      screen.getByRole('button', { name: /保\s*存/ }),
    );

    await waitFor(() => {
      expect(api.updateSubscription).toHaveBeenCalledWith(1, {
        name: '周报',
        recipient_email: 'ops@example.com',
        status: 'active',
      });
    });
  });

  it('confirms deletion of an existing subscription', async () => {
    api.listSubscriptions.mockResolvedValue([makeSubscription()]);
    api.deleteSubscription.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText('日报');
    await user.click(screen.getByRole('button', { name: '删除' }));
    await user.click(
      await screen.findByRole('button', { name: 'OK' }),
    );

    await waitFor(() => {
      expect(api.deleteSubscription).toHaveBeenCalledWith(1);
    });
  });

  it('creates a manual test execution and shows success', async () => {
    api.listSubscriptions.mockResolvedValue([makeSubscription()]);
    const user = userEvent.setup();
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    await user.click(
      await screen.findByRole('button', { name: '立即测试' }),
    );

    await waitFor(() => {
      expect(api.executeSubscription).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText('测试执行已创建')).not.toBeNull();
  });

  it('shows an error when manual execution creation fails', async () => {
    api.listSubscriptions.mockResolvedValue([makeSubscription()]);
    api.executeSubscription.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    await user.click(
      await screen.findByRole('button', { name: '立即测试' }),
    );

    expect(await screen.findByText('测试执行创建失败')).not.toBeNull();
  });
});
