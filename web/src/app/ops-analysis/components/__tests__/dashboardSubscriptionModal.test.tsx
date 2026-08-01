import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type {
  DashboardExecutionSummary,
  DashboardSubscription,
} from '@/app/ops-analysis/types/dashboardSubscription';
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

const makeExecutionSummary = (
  overrides: Partial<DashboardExecutionSummary> = {},
): DashboardExecutionSummary => ({
  execution_id: 100,
  status: 'succeeded',
  trigger_type: 'scheduled',
  failure_stage: '',
  error_code: '',
  error_message: '',
  created_at: '2026-07-28T01:00:00Z',
  finished_at: '2026-07-28T01:05:00Z',
  scheduled_time_utc: '2026-07-28T01:00:00Z',
  ...overrides,
});

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
  schedule_type: null,
  schedule_hour: null,
  schedule_minute: null,
  schedule_weekday: null,
  schedule_day_of_month: null,
  timezone: null,
  next_run_at: null,
  version: 1,
  config: {},
  latest_scheduled_execution: null,
  latest_manual_test_execution: null,
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

const translate = (
  key: string,
  _defaultMessage?: string,
  values?: Record<string, string | number>,
) => {
  const messages: Record<string, string> = {
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
    'dashboard.subscriptionScheduleType': '发送周期',
    'dashboard.subscriptionScheduleNone': '暂不调度（仅手动测试）',
    'dashboard.subscriptionScheduleDaily': '每天',
    'dashboard.subscriptionScheduleWeekly': '每周',
    'dashboard.subscriptionScheduleMonthly': '每月',
    'dashboard.subscriptionScheduleSummaryDaily': '每天 {time}',
    'dashboard.subscriptionScheduleSummaryWeekly': '每{weekday} {time}',
    'dashboard.subscriptionScheduleSummaryMonthly': '每月 {day} 日 {time}',
    'dashboard.subscriptionTimezone': '订阅时区',
    'dashboard.subscriptionWeekdayMon': '周一',
    'dashboard.subscriptionWeekdayTue': '周二',
    'dashboard.subscriptionWeekdayWed': '周三',
    'dashboard.subscriptionWeekdayThu': '周四',
    'dashboard.subscriptionWeekdayFri': '周五',
    'dashboard.subscriptionWeekdaySat': '周六',
    'dashboard.subscriptionWeekdaySun': '周日',
    'dashboard.subscriptionNextRunAt': '下次计划',
    'dashboard.subscriptionLatestScheduled': '最近计划执行',
    'dashboard.subscriptionLatestManualTest': '最近测试执行',
    'dashboard.subscriptionExecutionEmpty': '暂无记录',
    'dashboard.subscriptionExecutionFinishedAt': '完成时间',
    'dashboard.subscriptionExecutionScheduledAt': '计划时间',
    'dashboard.subscriptionExecutionTestedAt': '测试时间',
    'dashboard.subscriptionExecutionFailureReason': '失败原因',
    'dashboard.subscriptionExecute': '立即测试',
    'dashboard.subscriptionExecuteCreated': '测试执行已创建',
    'dashboard.subscriptionExecuteFailed': '测试执行创建失败',
    'dashboard.subscriptionExecutionStatus': '状态',
    'dashboard.executionStatusPending': '等待执行',
    'dashboard.executionStatusRunning': '执行中',
    'dashboard.executionStatusSucceeded': '执行成功',
    'dashboard.executionStatusFailed': '执行失败',
    'dashboard.subscriptionExecutionRefresh': '刷新状态',
    'dashboard.subscriptionExecutionQueryFailed': '查询执行状态失败',
    'common.edit': '编辑',
    'common.delete': '删除',
    'common.cancel': '取消',
  };
  let message = messages[key] ?? key;
  if (values) {
    Object.entries(values).forEach(([name, value]) => {
      message = message.replaceAll(`{${name}}`, String(value));
    });
  }
  return message;
};

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
        schedule_type: null,
        schedule_hour: null,
        schedule_minute: null,
        schedule_weekday: null,
        schedule_day_of_month: null,
        timezone: null,
        applied_filter_values: {},
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
        schedule_type: null,
        schedule_hour: null,
        schedule_minute: null,
        schedule_weekday: null,
        schedule_day_of_month: null,
        timezone: null,
        applied_filter_values: {},
        version: 1,
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

  it('shows independent scheduled and manual_test statuses', async () => {
    api.listSubscriptions.mockResolvedValue([
      makeSubscription({
        latest_scheduled_execution: makeExecutionSummary({
          execution_id: 11,
          status: 'succeeded',
          trigger_type: 'scheduled',
        }),
        latest_manual_test_execution: makeExecutionSummary({
          execution_id: 12,
          status: 'failed',
          trigger_type: 'manual_test',
          error_message: 'SMTP 失败',
          scheduled_time_utc: null,
        }),
      }),
    ]);
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    const scheduled = await screen.findByTestId('latest-scheduled-1');
    const manual = screen.getByTestId('latest-manual-test-1');
    expect(within(scheduled).getByText('最近计划执行')).not.toBeNull();
    expect(within(scheduled).getByText('执行成功')).not.toBeNull();
    expect(within(manual).getByText('最近测试执行')).not.toBeNull();
    expect(within(manual).getByText('执行失败')).not.toBeNull();
    expect(within(manual).getByText(/SMTP 失败/)).not.toBeNull();
  });

  it('shows empty state for missing manual_test summary', async () => {
    api.listSubscriptions.mockResolvedValue([
      makeSubscription({
        latest_scheduled_execution: makeExecutionSummary(),
        latest_manual_test_execution: null,
      }),
    ]);
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    const manual = await screen.findByTestId('latest-manual-test-1');
    expect(within(manual).getByText('暂无记录')).not.toBeNull();
    expect(
      within(screen.getByTestId('latest-scheduled-1')).getByText('执行成功'),
    ).not.toBeNull();
  });

  it('shows empty state for missing scheduled summary', async () => {
    api.listSubscriptions.mockResolvedValue([
      makeSubscription({
        latest_scheduled_execution: null,
        latest_manual_test_execution: makeExecutionSummary({
          trigger_type: 'manual_test',
          status: 'pending',
          scheduled_time_utc: null,
        }),
      }),
    ]);
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    const scheduled = await screen.findByTestId('latest-scheduled-1');
    expect(within(scheduled).getByText('暂无记录')).not.toBeNull();
    expect(
      within(screen.getByTestId('latest-manual-test-1')).getByText('等待执行'),
    ).not.toBeNull();
  });

  it('keeps scheduled summary unchanged after manual_test refresh', async () => {
    const scheduled = makeExecutionSummary({
      execution_id: 11,
      status: 'succeeded',
      trigger_type: 'scheduled',
    });
    api.listSubscriptions
      .mockResolvedValueOnce([
        makeSubscription({
          latest_scheduled_execution: scheduled,
          latest_manual_test_execution: null,
        }),
      ])
      .mockResolvedValueOnce([
        makeSubscription({
          latest_scheduled_execution: scheduled,
          latest_manual_test_execution: makeExecutionSummary({
            execution_id: 22,
            status: 'pending',
            trigger_type: 'manual_test',
            scheduled_time_utc: null,
          }),
        }),
      ]);
    const user = userEvent.setup();
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    expect(
      within(await screen.findByTestId('latest-scheduled-1')).getByText(
        '执行成功',
      ),
    ).not.toBeNull();

    await user.click(
      await screen.findByRole('button', { name: '立即测试' }),
    );

    await waitFor(() => {
      expect(api.listSubscriptions).toHaveBeenCalledTimes(2);
    });
    expect(
      within(screen.getByTestId('latest-scheduled-1')).getByText('执行成功'),
    ).not.toBeNull();
    expect(
      within(screen.getByTestId('latest-manual-test-1')).getByText('等待执行'),
    ).not.toBeNull();
  });

  it('renders daily/weekly/monthly schedule summaries and timezone', async () => {
    api.listSubscriptions.mockResolvedValue([
      makeSubscription({
        id: 1,
        name: '日报',
        schedule_type: 'daily',
        schedule_hour: 9,
        schedule_minute: 0,
        timezone: 'Asia/Shanghai',
      }),
      makeSubscription({
        id: 2,
        name: '周报',
        schedule_type: 'weekly',
        schedule_hour: 9,
        schedule_minute: 0,
        schedule_weekday: 0,
        timezone: 'Asia/Shanghai',
      }),
      makeSubscription({
        id: 3,
        name: '月报',
        schedule_type: 'monthly',
        schedule_hour: 9,
        schedule_minute: 0,
        schedule_day_of_month: 31,
        timezone: 'Asia/Shanghai',
      }),
    ]);
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText('日报')).not.toBeNull();
    expect(screen.getByTestId('schedule-summary-1').textContent).toContain(
      '发送周期: 每天 09:00',
    );
    expect(screen.getByTestId('schedule-summary-2').textContent).toContain(
      '发送周期: 每周一 09:00',
    );
    expect(screen.getByTestId('schedule-summary-3').textContent).toContain(
      '发送周期: 每月 31 日 09:00',
    );
    expect(screen.getByTestId('schedule-timezone-1').textContent).toContain(
      '订阅时区: Asia/Shanghai',
    );
    expect(screen.getByTestId('schedule-timezone-2').textContent).toContain(
      '订阅时区: Asia/Shanghai',
    );
    expect(screen.getByTestId('schedule-timezone-3').textContent).toContain(
      '订阅时区: Asia/Shanghai',
    );
  });

  it('disables test button when scheduled execution is pending', async () => {
    api.listSubscriptions.mockResolvedValue([
      makeSubscription({
        latest_scheduled_execution: makeExecutionSummary({
          status: 'pending',
        }),
      }),
    ]);
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    expect(
      await screen.findByRole('button', { name: '立即测试' }),
    ).toHaveProperty('disabled', true);
  });

  it('disables test button when manual_test execution is running', async () => {
    api.listSubscriptions.mockResolvedValue([
      makeSubscription({
        latest_manual_test_execution: makeExecutionSummary({
          status: 'running',
          trigger_type: 'manual_test',
          scheduled_time_utc: null,
        }),
      }),
    ]);
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    expect(
      await screen.findByRole('button', { name: '立即测试' }),
    ).toHaveProperty('disabled', true);
  });

  it('keeps test button enabled for succeeded and failed summaries', async () => {
    api.listSubscriptions.mockResolvedValue([
      makeSubscription({
        latest_scheduled_execution: makeExecutionSummary({
          status: 'succeeded',
        }),
        latest_manual_test_execution: makeExecutionSummary({
          status: 'failed',
          trigger_type: 'manual_test',
          scheduled_time_utc: null,
        }),
      }),
    ]);
    render(
      <DashboardSubscriptionModal
        open
        dashboardId={8}
        onClose={vi.fn()}
      />,
    );

    expect(
      await screen.findByRole('button', { name: '立即测试' }),
    ).toHaveProperty('disabled', false);
  });
});
