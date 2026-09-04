import React from 'react';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ApmAlertsPage from '../page';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import { formatDateTime } from '@/app/apm/components/metric-format';

const { chartRender } = vi.hoisted(() => ({ chartRender: vi.fn() }));

const event = {
  id: 'e1',
  event_id: 'evt-1',
  action: 'triggered' as const,
  severity: 'error' as const,
  value: '0.2',
  occurred_at: '2026-08-14T02:00:00Z',
  title: '错误率触发',
  description: '错误率超过阈值',
};
const alert = {
  id: 'a1',
  external_id: 'alert-1',
  title: 'checkout 错误率升高',
  policy_id: 'p1',
  policy_name: '错误率',
  service_id: 's1',
  service_namespace: 'shop',
  service_name: 'checkout',
  environment: 'production',
  endpoint: 'POST /checkout',
  version: 'v2',
  metric_type: 'error_rate' as const,
  severity: 'error' as const,
  status: 'active' as const,
  notification_status: 'delivered' as const,
  current_value: '0.2',
  operator: 'sre.wang',
  started_at: event.occurred_at,
  ended_at: null,
  last_event_at: event.occurred_at,
  event_count: 1,
  events: [event],
};
const recoveredAlert = {
  ...alert,
  id: 'a2',
  external_id: 'alert-2',
  title: 'checkout P95 时延恢复',
  status: 'recovered' as const,
  notification_status: 'none' as const,
  operator: 'sre.li',
  ended_at: '2026-08-14T03:00:00Z',
};
const snapshot = {
  id: 'ss1',
  event_id: 'evt-1',
  schema_version: 1,
  action: 'triggered' as const,
  occurred_at: event.occurred_at,
  policy_snapshot: { name: '错误率', thresholds: [{ severity: 'error', comparator: 'gt', value: '0.1' }] },
  object_snapshot: { endpoint: 'POST /checkout', environment: 'production', version: 'v2' },
  evaluation_snapshot: {
    value: '0.2',
    unit: 'ratio',
    comparator: 'gt' as const,
    threshold: '0.1',
    severity: 'error' as const,
    data_state: 'available' as const,
  },
  trace_context: {
    service_namespace: 'shop',
    service_name: 'checkout',
    endpoint: 'POST /checkout',
    environment: 'production',
    started_at: '2026-08-14T01:55:00Z',
    ended_at: event.occurred_at,
  },
  payload_status: 'available' as const,
  payload_error_code: '',
  payload: {
    event_point: event.occurred_at,
    threshold: { severity: 'error' as const, comparator: 'gt' as const, value: '0.1' },
    series: [
      { timestamp: '2026-08-14T01:59:00Z', value: 0.08 },
      { timestamp: '2026-08-14T01:59:20Z', value: 0.1 },
      { timestamp: '2026-08-14T01:59:40Z', value: 0.12 },
      { timestamp: event.occurred_at, value: 0.2 },
    ],
  },
  retention_expires_at: '2026-11-12T02:00:00Z',
};
const metricSnapshot = {
  unit: 'ratio',
  aggregation: 'avg' as const,
  evaluation_interval: 1,
  metric_window: 5,
  snapshots: [
    {
      type: 'event' as const,
      snapshot_time: '2026-08-14T02:00:00Z',
      event_id: 'evt-1',
      event_time: '2026-08-14T02:00:00Z',
      value: '0.2',
      threshold: { severity: 'error' as const, comparator: 'gt' as const, value: '0.1' },
      data_state: 'available' as const,
    },
    {
      type: 'info' as const,
      snapshot_time: '2026-08-14T02:01:00Z',
      event_id: null,
      event_time: null,
      value: '0.18',
      threshold: { severity: 'error' as const, comparator: 'gt' as const, value: '0.1' },
      data_state: 'available' as const,
    },
  ],
};

const api = {
  closeAlert: vi.fn(),
  getAlertDistribution: vi.fn(),
  getAlerts: vi.fn(),
  getAlertSnapshots: vi.fn(),
  getEventEvidence: vi.fn(),
  getNotificationDeliveries: vi.fn(),
  retryNotificationDelivery: vi.fn(),
  isLoading: false,
};
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/heat-map', () => ({
  default: () => <div>事件分布热力图</div>,
}));
vi.mock('@/components/time-series-composed-chart', () => ({
  default: (props: { data: Array<Record<string, unknown>>; series: Array<{ name: string }> }) => {
    chartRender(props);
    return <div>{props.series.map((item) => item.name).join(' / ')}</div>;
  },
}));

beforeEach(() => {
  window.matchMedia = vi
    .fn()
    .mockReturnValue({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
  api.getAlerts.mockImplementation((query: { status_group?: string }) => Promise.resolve(
    query.status_group === 'active' ? [alert] : query.status_group === 'history' ? [recoveredAlert] : [],
  ));
  api.getAlertDistribution.mockImplementation((query: { status_group?: string }) => Promise.resolve(
    query.status_group === 'active'
      ? [{ time: event.occurred_at, critical: 0, error: 1, warning: 0 }]
      : query.status_group === 'history'
        ? [{ time: recoveredAlert.ended_at, critical: 0, error: 0, warning: 1 }]
        : [],
  ));
  api.getAlertSnapshots.mockResolvedValue(metricSnapshot);
  api.getEventEvidence.mockResolvedValue([snapshot]);
  api.getNotificationDeliveries.mockResolvedValue([]);
  api.retryNotificationDelivery.mockResolvedValue({
    id: 'd1',
    event_id: 'evt-1',
    channel_id: 1,
    channel_name: '值班群',
    channel_type: 'slack',
    delivery_mode: 'message',
    recipients: ['sre'],
    status: 'pending',
    attempts: 0,
    next_retry_at: null,
    last_error_code: '',
    last_error_message: '',
    delivered_at: null,
    failed_at: null,
  });
  api.closeAlert.mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 告警指标快照与事件原始数据', { timeout: 15000 }, () => {
  it('空列表只展示一处页面空态，不复用 APM 总述也不叠分布图空态', async () => {
    api.getAlerts.mockResolvedValue([]);
    api.getAlertDistribution.mockResolvedValue([]);
    renderWithApmIntl(<ApmAlertsPage />);

    expect(await screen.findByText('暂无活跃告警数据')).not.toBeNull();
    expect(screen.queryByText('当前范围暂无 APM 数据')).toBeNull();
    expect(screen.queryByText('暂无数据')).toBeNull();
    expect(screen.queryByRole('button', { name: '重新加载' })).toBeNull();
    expect(screen.queryByRole('img', { name: /活跃告警事件分布/ })).toBeNull();
  });

  it('只通过显式详情入口打开告警详情', async () => {
    renderWithApmIntl(<ApmAlertsPage />);
    const serviceCell = await screen.findByText('checkout');
    const alertRow = serviceCell.closest('tr');

    expect(alertRow).not.toBeNull();
    fireEvent.click(alertRow!);
    expect(screen.queryByRole('dialog', { name: /checkout 错误率升高/ })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    expect(await screen.findByRole('dialog', { name: /checkout 错误率升高/ })).not.toBeNull();
  });

  it('从列表人工关闭告警时不会意外打开告警详情', async () => {
    renderWithApmIntl(<ApmAlertsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '关闭' }));

    expect(screen.queryByRole('dialog', { name: /checkout 错误率升高/ })).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: /^确\s*定$/ }));
    await waitFor(() => expect(api.closeAlert).toHaveBeenCalledWith('a1'));

    expect(screen.queryByRole('dialog', { name: /checkout 错误率升高/ })).toBeNull();
  });

  it('使用 Alert 聚合接口展示活跃告警和分布', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmAlertsPage />);
    expect(await screen.findByText('checkout 错误率升高')).not.toBeNull();
    expect(screen.queryByText('搜索条件')).toBeNull();
    const alertWorkspace = screen.getByRole('region', { name: '告警工作区' });
    expect(alertWorkspace.contains(screen.getByLabelText('搜索告警'))).toBe(true);
    expect(alertWorkspace.contains(screen.getByLabelText('告警分布'))).toBe(true);
    expect(alertWorkspace.contains(screen.getByLabelText('告警列表'))).toBe(true);
    expect(screen.getByText('分布图')).not.toBeNull();
    expect(screen.queryByText('自动刷新')).toBeNull();
    expect(screen.queryByText('最近7天')).toBeNull();
    const severitySummary = screen.getByLabelText('三级告警数量');
    expect(severitySummary.textContent?.replace(/\s+/g, ' ').trim()).toMatch(/严重 0.*错误 1.*警告 0/);
    expect(severitySummary.querySelector('.ant-tag')).toBeNull();
    expect(screen.getByText('严重 / 错误 / 警告')).not.toBeNull();
    const distributionSeries = chartRender.mock.calls.find(
      ([props]) => props.series[0]?.name === '严重',
    )?.[0].series;
    const distributionLabel = chartRender.mock.calls.find(
      ([props]) => props.series[0]?.name === '严重',
    )?.[0].getXLabel({ time: '2026-08-17T16:41:03Z' });
    expect(distributionLabel).toBe(formatDateTime('2026-08-17T16:41:03Z', false));
    expect(screen.getByRole('img', { name: /活跃告警事件分布/ })).not.toBeNull();
    await user.click(screen.getByText('分布图'));
    expect(screen.queryByRole('img', { name: /活跃告警事件分布/ })).toBeNull();
    await user.click(screen.getByText('分布图'));
    expect(screen.getByRole('img', { name: /活跃告警事件分布/ })).not.toBeNull();
    expect(distributionSeries).toEqual([
      expect.objectContaining({ color: '#F43B2C', stack: 'severity', barGradient: false }),
      expect.objectContaining({ color: '#D97007', stack: 'severity', barGradient: false }),
      expect.objectContaining({ color: '#FFAD42', stack: 'severity', barGradient: false }),
    ]);
    const activeTab = screen.getByRole('tab', { name: '活跃告警' });
    const historyTab = screen.getByRole('tab', { name: '历史告警' });
    expect(activeTab.compareDocumentPosition(screen.getByLabelText('搜索告警')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent?.trim())).toEqual([
      '级别',
      '触发时间',
      '告警标题',
      '指标',
      '服务 / 端点',
      '通知',
      '处置人',
      '操作',
    ]);
    const columnWidths = Array.from(document.querySelectorAll('.ant-table colgroup col'))
      .map((column) => (column as HTMLElement).style.width);
    expect(columnWidths).toEqual(['96px', '168px', '', '120px', '', '120px', '160px', '160px']);
    expect(screen.getByText('已通知')).not.toBeNull();
    expect(screen.getByText('sre.wang')).not.toBeNull();
    expect(screen.queryByRole('columnheader', { name: '当前值' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '状态' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '事件' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '最近变化' })).toBeNull();
    const activeQuery = api.getAlerts.mock.calls.find(
      ([query]) => query.status_group === 'active'
    )?.[0] as Record<string, unknown>;
    const activeDistributionQuery = api.getAlertDistribution.mock.calls.find(
      ([query]) => query.status_group === 'active'
    )?.[0] as Record<string, unknown>;
    expect(activeQuery).not.toHaveProperty('started_at');
    expect(activeQuery).not.toHaveProperty('ended_at');
    expect(activeDistributionQuery).not.toHaveProperty('started_at');
    expect(activeDistributionQuery).not.toHaveProperty('ended_at');
    await user.click(historyTab);
    expect(await screen.findByText('checkout P95 时延恢复')).not.toBeNull();
    expect(screen.getByText('分布图')).not.toBeNull();
    expect(screen.getByText('最近7天')).not.toBeNull();
    expect(screen.queryByText('checkout 错误率升高')).toBeNull();
    expect(api.getAlerts).toHaveBeenLastCalledWith(expect.objectContaining({ status_group: 'history' }));
    expect(api.getAlertDistribution).toHaveBeenLastCalledWith(expect.objectContaining({ status_group: 'history' }));
    const historyQuery = api.getAlerts.mock.calls.at(-1)?.[0] as { started_at: string; ended_at: string };
    expect(new Date(historyQuery.ended_at).getTime() - new Date(historyQuery.started_at).getTime()).toBe(604_800_000);
    await user.click(screen.getByText('最近7天'));
    await user.click(await screen.findByText('最近1天'));
    await waitFor(() => {
      const oneDayQuery = api.getAlerts.mock.calls.at(-1)?.[0] as { started_at: string; ended_at: string };
      const oneDayDuration =
        new Date(oneDayQuery.ended_at).getTime() - new Date(oneDayQuery.started_at).getTime();
      expect(oneDayDuration).toBeGreaterThanOrEqual(86_400_000);
      expect(oneDayDuration).toBeLessThan(86_401_000);
      expect(api.getAlertDistribution).toHaveBeenLastCalledWith(expect.objectContaining({ status_group: 'history' }));
    });
    expect(chartRender.mock.calls.at(-1)?.[0].data).toEqual([
      expect.objectContaining({ warning: 1 }),
    ]);
  });

  it('事件 Tab 按原型展示分布热力图和扫描事件流', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmAlertsPage />);
    await user.click(await screen.findByRole('button', { name: 'checkout 错误率升高' }));
    await user.click(await screen.findByRole('tab', { name: '事件' }));
    expect(screen.getByText('事件分布 · 近 7 天 × 24h')).not.toBeNull();
    expect(await screen.findByText('事件流(按时间倒序 · 共 2 条)')).not.toBeNull();
    expect(screen.getByRole('img', { name: '事件分布，近 7 天按小时聚合' })).not.toBeNull();
    expect(
      screen.getByRole('list', { name: '事件流时间线' }).querySelectorAll('[role="listitem"]'),
    ).toHaveLength(2);
    expect(screen.getByText('20.0%')).not.toBeNull();
    expect(screen.getByText('18.0%')).not.toBeNull();
    expect(screen.getByText(/红底高亮 = 告警触发时段/)).not.toBeNull();
    expect(screen.queryByText('事件信息')).toBeNull();
    expect(screen.queryByText('原始证据')).toBeNull();
    expect(await screen.findByRole('link', { name: '查看当时调用链' })).not.toBeNull();
    expect(screen.getByRole('link', { name: '查看当时调用链' }).getAttribute('href')).toBe(
      '/apm/explore/traces?service_name=checkout&started_at=2026-08-14T01%3A55%3A00Z&ended_at=2026-08-14T02%3A00%3A00Z&service_namespace=shop&environment=production&span_name=POST+%2Fcheckout',
    );
    await waitFor(() => expect(api.getEventEvidence).toHaveBeenCalledWith('a1', 'evt-1'));
  });

  it('告警主图按策略扫描快照绘制成趋势图，生命周期事件只作为标记', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmAlertsPage />);

    await user.click(await screen.findByRole('button', { name: 'checkout 错误率升高' }));

    expect(await screen.findByText('告警信息')).not.toBeNull();
    expect(screen.getByText(/所属服务/)).not.toBeNull();
    expect(screen.getByRole('button', { name: '关闭告警' })).not.toBeNull();
    expect(await screen.findByText('评估值 / 当时阈值 / 生命周期事件')).not.toBeNull();
    expect(screen.getByText(/告警指标快照/)).not.toBeNull();
    expect(screen.getByText(/每点一次策略扫描/)).not.toBeNull();
    expect(screen.getByText(/检测频率 1 分钟/)).not.toBeNull();
    await waitFor(() => expect(api.getAlertSnapshots).toHaveBeenCalledWith('a1'));
    await waitFor(() => {
      const snapshotChart = [...chartRender.mock.calls].reverse().find(
        ([props]) => props.series[0]?.name === '评估值',
      )?.[0];
      expect(snapshotChart.data).toEqual([
        expect.objectContaining({
          elapsedMinutes: 0,
          value: 20,
          event: 20,
          threshold: 10,
        }),
        expect.objectContaining({
          elapsedMinutes: 1,
          value: 18,
          event: null,
          threshold: 10,
        }),
      ]);
      expect(snapshotChart.getXLabel(snapshotChart.data[0])).toBe('触发');
      expect(snapshotChart.getXLabel(snapshotChart.data[1])).toBe('+1 分钟');
    });
  });

  it('通知终止失败后可以人工重投', async () => {
    const user = userEvent.setup();
    api.getNotificationDeliveries.mockResolvedValue([
      {
        id: 'd-fail',
        event_id: 'evt-1',
        channel_id: 1,
        channel_name: '值班群',
        channel_type: 'slack',
        delivery_mode: 'message',
        recipients: ['sre'],
        status: 'failed',
        attempts: 3,
        next_retry_at: null,
        last_error_code: 'provider_unavailable',
        last_error_message: 'temporarily down',
        delivered_at: null,
        failed_at: event.occurred_at,
      },
    ]);
    renderWithApmIntl(<ApmAlertsPage />);
    await user.click(await screen.findByRole('button', { name: 'checkout 错误率升高' }));
    await user.click(await screen.findByRole('tab', { name: '事件' }));
    expect(await screen.findByText('值班群')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '重投' }));
    await waitFor(() => expect(api.retryNotificationDelivery).toHaveBeenCalledWith('d-fail'));
  });
});
