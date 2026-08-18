import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ApmAlertsPage from '../page';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';

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
  trace_context: { service_name: 'checkout' },
  payload_status: 'available' as const,
  payload_error_code: '',
  payload: {
    event_point: event.occurred_at,
    threshold: { severity: 'error' as const, comparator: 'gt' as const, value: '0.1' },
    series: [
      { timestamp: '2026-08-14T01:59:00Z', value: 0.08 },
      { timestamp: event.occurred_at, value: 0.2 },
    ],
  },
  retention_expires_at: '2026-11-12T02:00:00Z',
};

const api = {
  closeAlert: vi.fn(),
  getAlertDistribution: vi.fn(),
  getAlerts: vi.fn(),
  getAlertSnapshots: vi.fn(),
  getNotificationDeliveries: vi.fn(),
  isLoading: false,
};
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/time-series-composed-chart', () => ({
  default: (props: { series: Array<{ name: string }> }) => {
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
  api.getAlerts.mockResolvedValue([alert, recoveredAlert]);
  api.getAlertDistribution.mockResolvedValue([{ time: event.occurred_at, critical: 0, error: 1, warning: 0 }]);
  api.getAlertSnapshots.mockResolvedValue([snapshot]);
  api.getNotificationDeliveries.mockResolvedValue([]);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM Alert 与 Event Snapshot', () => {
  it('使用 Alert 聚合接口展示活跃告警和分布', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmAlertsPage />);
    expect(await screen.findByText('checkout 错误率升高')).not.toBeNull();
    expect(screen.getByRole('heading', { name: '告警' })).not.toBeNull();
    expect(screen.getByText('告警分布(近 24h)')).not.toBeNull();
    expect(screen.getByText('严重 / 错误 / 警告')).not.toBeNull();
    const distributionSeries = chartRender.mock.calls.find(
      ([props]) => props.series[0]?.name === '严重',
    )?.[0].series;
    expect(distributionSeries).toEqual([
      expect.objectContaining({ color: '#F43B2C', stack: 'severity', barGradient: false }),
      expect.objectContaining({ color: '#D97007', stack: 'severity', barGradient: false }),
      expect.objectContaining({ color: '#FFAD42', stack: 'severity', barGradient: false }),
    ]);
    expect(screen.getByRole('tab', { name: /活跃告警.*1/ })).not.toBeNull();
    expect(screen.getByRole('tab', { name: /历史告警.*1/ })).not.toBeNull();
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
    expect(screen.getByText('已通知')).not.toBeNull();
    expect(screen.getByText('sre.wang')).not.toBeNull();
    expect(screen.queryByRole('columnheader', { name: '当前值' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '状态' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '事件' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '最近变化' })).toBeNull();
    expect(api.getAlerts).toHaveBeenCalledWith(expect.not.objectContaining({ status: 'active' }));
    await user.click(screen.getByRole('tab', { name: /历史告警.*1/ }));
    expect(await screen.findByText('checkout P95 时延恢复')).not.toBeNull();
    expect(api.getAlerts).toHaveBeenCalledTimes(1);
  });

  it('详情趋势绑定所选 event_id 的持久化快照，而不是重查当前 RED', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmAlertsPage />);
    await user.click(await screen.findByRole('button', { name: 'checkout 错误率升高' }));
    await user.click(await screen.findByRole('tab', { name: '事件快照' }));
    expect(await screen.findByText('评估值 / 当时阈值 / 事件发生点')).not.toBeNull();
    expect(screen.getByText('正在展示所选事件发生时的持久化快照，不会重新查询当前策略。')).not.toBeNull();
    await waitFor(() => expect(api.getAlertSnapshots).toHaveBeenCalledWith('a1', 'evt-1'));
  });
});
