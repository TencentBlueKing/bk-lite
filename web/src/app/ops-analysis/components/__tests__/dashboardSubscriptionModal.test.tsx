import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { DashboardSubscription } from '@/app/ops-analysis/types/dashboardSubscription';
import DashboardSubscriptionModal from '../dashboardSubscriptionModal';

const api = {
  listSubscriptions: vi.fn(),
  createSubscription: vi.fn(),
  updateSubscription: vi.fn(),
  deleteSubscription: vi.fn(),
  executeSubscription: vi.fn(),
  getExecution: vi.fn(),
};

const channelApi = {
  getChannelData: vi.fn(),
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
  email_channel: 11,
  config: {},
  created_at: '2026-07-28T00:00:00Z',
  updated_at: '2026-07-28T00:00:00Z',
  ...overrides,
});

vi.mock('@/app/ops-analysis/api/dashboardSubscription', () => ({
  useDashboardSubscriptionApi: () => api,
}));

vi.mock('@/app/system-manager/api/channel', () => ({
  useChannelApi: () => channelApi,
}));

const translate = (key: string) =>
  ({
    'dashboard.subscriptionTitle': '报告订阅',
    'dashboard.subscriptionCreate': '创建订阅',
    'dashboard.subscriptionName': '订阅名称',
    'dashboard.subscriptionEmail': '接收邮箱',
    'dashboard.subscriptionChannel': '邮件渠道',
    'dashboard.subscriptionChannelPlaceholder': '请选择邮件渠道',
    'dashboard.subscriptionChannelRequired': '请选择邮件渠道',
    'dashboard.subscriptionChannelLoadFailed': '加载邮件渠道失败',
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
    'dashboard.subscriptionExecutionStatus': '状态',
    'dashboard.executionStatusPending': '等待执行',
    'dashboard.executionStatusFailed': '执行失败',
    'dashboard.subscriptionExecutionRefresh': '刷新状态',
    'dashboard.subscriptionExecutionQueryFailed': '查询执行状态失败',
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
    execution_id: 10,
    status: 'pending',
    request_id: 'req-test',
    created: true,
  });
  api.getExecution.mockResolvedValue({
    id: 10,
    subscription: 1,
    dashboard: 8,
    creator: 'test',
    status: 'pending',
    trigger_type: 'manual_test',
    failure_stage: '',
    error_message: '',
    created_at: '2026-07-28T00:00:00Z',
    started_at: null,
    finished_at: null,
    snapshot: {
      dashboard_id: 8,
      creator_id: 'test',
      subscription_id: 1,
      filter_values: {},
      created_at: '2026-07-28T00:00:00Z',
    },
  });
  channelApi.getChannelData.mockResolvedValue([
    { id: 11, name: '运营邮件通道', channel_type: 'email' },
    { id: 12, name: '备用邮件通道', channel_type: 'email' },
    { id: 99, name: '企微通道', channel_type: 'enterprise_wechat' },
  ]);
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

async function selectEmailChannel(user: ReturnType<typeof userEvent.setup>, label = '运营邮件通道') {
  await user.click(screen.getByLabelText('邮件渠道'));
  const option = await screen.findByText(label);
  await user.click(option);
}

describe('DashboardSubscriptionModal', () => {
  it('requires email channel before creating a subscription', async () => {
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

    expect(await screen.findByText('请选择邮件渠道')).not.toBeNull();
    expect(api.createSubscription).not.toHaveBeenCalled();
  });

  it('opens the create form and submits email_channel', async () => {
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
    await selectEmailChannel(user);
    await user.click(
      screen.getByRole('button', { name: /保\s*存/ }),
    );

    await waitFor(() => {
      expect(api.createSubscription).toHaveBeenCalledWith({
        dashboard: 8,
        name: '日报',
        recipient_email: 'ops@example.com',
        email_channel: 11,
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
    await selectEmailChannel(user);
    await user.click(
      screen.getByRole('button', { name: /保\s*存/ }),
    );

    expect(await screen.findByText('创建订阅失败')).not.toBeNull();
  });

  it('shows channel load errors from the existing channel API', async () => {
    channelApi.getChannelData.mockRejectedValueOnce(new Error('boom'));
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText('加载邮件渠道失败')).not.toBeNull();
  });

  it('lists status and edits an existing subscription with current channel', async () => {
    const subscription = makeSubscription();
    api.listSubscriptions.mockResolvedValue([subscription]);
    api.updateSubscription.mockResolvedValue({
      ...subscription,
      name: '周报',
      email_channel: 12,
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
    expect(screen.getByText('邮件渠道：运营邮件通道')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '编辑' }));

    const channelSelect = screen.getByLabelText('邮件渠道');
    expect(within(channelSelect.closest('.ant-select')!).getByText('运营邮件通道')).not.toBeNull();

    const nameInput = screen.getByLabelText('订阅名称');
    await user.clear(nameInput);
    await user.type(nameInput, '周报');
    await selectEmailChannel(user, '备用邮件通道');
    await user.click(
      screen.getByRole('button', { name: /保\s*存/ }),
    );

    await waitFor(() => {
      expect(api.updateSubscription).toHaveBeenCalledWith(1, {
        name: '周报',
        recipient_email: 'ops@example.com',
        email_channel: 12,
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

  it('creates a pending manual test execution and displays its status', async () => {
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
      expect(api.executeSubscription).toHaveBeenCalledWith(
        1,
        expect.any(String),
      );
    });
    expect(
      await screen.findByText('测试执行已创建 · 状态：等待执行'),
    ).not.toBeNull();
  });

  it('shows an error when querying execution status fails', async () => {
    api.listSubscriptions.mockResolvedValue([makeSubscription()]);
    api.getExecution.mockRejectedValueOnce(new Error('boom'));
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
    await user.click(
      await screen.findByRole('button', { name: '刷新状态' }),
    );

    await waitFor(() => {
      expect(api.getExecution).toHaveBeenCalledWith(10);
    });
    expect(await screen.findByText('查询执行状态失败')).not.toBeNull();
  });

  it('shows a failed execution with error semantics', async () => {
    api.listSubscriptions.mockResolvedValue([makeSubscription()]);
    api.getExecution.mockResolvedValueOnce({
      id: 10,
      status: 'failed',
    });
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
    await user.click(
      await screen.findByRole('button', { name: '刷新状态' }),
    );

    const executionAlert = await screen.findByText(
      '测试执行已创建 · 状态：执行失败',
    );
    expect(executionAlert.closest('[role="alert"]')?.className).toContain(
      'ant-alert-error',
    );
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
