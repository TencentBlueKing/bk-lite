import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ApmPolicyEditor from '../policy-editor';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';

const input = {
  name: '错误率策略',
  service_id: 'svc-1',
  environment: 'production',
  alert_name: '${service}',
  endpoints: ['POST /checkout'],
  version_mode: 'all' as const,
  versions: [],
  metric_type: 'error_rate' as const,
  evaluation_interval: 1,
  metric_window: 5,
  aggregation: 'avg' as const,
  thresholds: [{ severity: 'warning' as const, comparator: 'gt' as const, value: '0.05' }],
  trigger_after: 3,
  recover_after: 3,
  no_data_after: null,
  no_data_severity: '' as const,
  notification_targets: [],
};
const policy = {
  ...input,
  id: 'p1',
  comparator: 'gt' as const,
  threshold: '0.05',
  duration_window: 5,
  recovery_window: 3,
  severity: 'warning' as const,
  is_enabled: true,
  service_namespace: 'shop',
  service_name: 'checkout',
  state: null,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
};
const api = {
  createPolicy: vi.fn(),
  getInstances: vi.fn(),
  getNotificationChannels: vi.fn(),
  getPolicy: vi.fn(),
  getServiceRed: vi.fn(),
  getServices: vi.fn(),
  isLoading: false,
  previewPolicy: vi.fn(),
  updatePolicy: vi.fn(),
};
vi.mock('next/link', () => ({ default: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/time-series-composed-chart', () => ({ default: () => <div>真实趋势图</div> }));

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
  api.getServices.mockResolvedValue([{ id: 'svc-1', namespace: 'shop', name: 'checkout' }]);
  api.getNotificationChannels.mockResolvedValue([]);
  api.getPolicy.mockResolvedValue(policy);
  api.getServiceRed.mockResolvedValue({ top_endpoints: [{ endpoint: 'POST /checkout' }], timeseries: [] });
  api.getInstances.mockResolvedValue([]);
  api.previewPolicy.mockResolvedValue({
    value: '0.2',
    breached: true,
    evaluated_at: '2026-08-14T02:00:00Z',
    data_state: 'available',
    threshold: input.thresholds[0],
    series: [{ timestamp: '2026-08-14T02:00:00Z', request_rate: 10, error_rate: 0.2, p95_ms: 100, p99_ms: 150 }],
  });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 四步策略编辑器', () => {
  it('展示四步流程和真实变量来源，且不暴露 Monitor/Log 表达式', async () => {
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    expect(await screen.findByText('1. 基本信息')).not.toBeNull();
    expect(screen.getByText('2. 指标定义')).not.toBeNull();
    expect(screen.getByText('3. 告警条件')).not.toBeNull();
    expect(screen.getByText('4. 通知配置')).not.toBeNull();
    expect(screen.getByText('${endpoint}')).not.toBeNull();
    expect(screen.queryByText(/LogSQL|MonitorObject|采集插件/)).toBeNull();
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('指标预览把当前表单提交给真实预览接口', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);
    await user.click(await screen.findByRole('button', { name: '预览真实指标' }));
    await waitFor(() =>
      expect(api.previewPolicy).toHaveBeenCalledWith(
        expect.objectContaining({ service_id: 'svc-1', environment: 'production', metric_type: 'error_rate' }),
      ),
    );
    expect(await screen.findByText('真实趋势图')).not.toBeNull();
  });

  it('编辑策略时保留归档服务和不可用渠道的名称', async () => {
    const user = userEvent.setup();
    api.getServices.mockResolvedValue([
      { id: 'svc-active', namespace: 'shop', name: 'catalog', archived_at: null },
    ]);
    api.getNotificationChannels.mockResolvedValue([
      {
        id: 23,
        name: '告警中心',
        channel_type: 'nats',
        description: '事件副本',
        delivery_mode: 'alert_event_copy',
        recipient_mode: 'none',
        availability: 'unavailable',
      },
    ]);
    api.getPolicy.mockResolvedValue({
      ...policy,
      notification_targets: [
        {
          channel_id: 23,
          channel_name: '告警中心',
          channel_type: 'nats',
          delivery_mode: 'alert_event_copy',
          recipient_mode: 'none',
          recipients: [],
        },
      ],
    });

    renderWithApmIntl(<ApmPolicyEditor policyId="p1" />);

    expect(await screen.findByText('shop / checkout（已归档）')).not.toBeNull();
    expect(screen.getByText('告警中心（当前不可用）')).not.toBeNull();
    expect(screen.queryByText('svc-1')).toBeNull();
    expect(screen.queryByText('23')).toBeNull();
    expect(api.getServices).toHaveBeenCalledWith({ include_archived: true });

    await user.click(screen.getByRole('button', { name: '保存策略' }));
    expect(await screen.findByText('已失效，保存前请移除')).not.toBeNull();
    expect(api.updatePolicy).not.toHaveBeenCalled();
  });
});
