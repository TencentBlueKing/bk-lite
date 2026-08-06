import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmEventsPage from '../page';

const api = {
  getEvents: vi.fn(),
  retryNotificationDelivery: vi.fn(),
  isLoading: false,
};

vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

const firingEvent = {
  id: '1',
  event_id: 'evt-1',
  external_id: 'ext-1',
  title: 'checkout 错误率升高',
  description: '近 5 分钟错误率超过阈值',
  severity: 'critical' as const,
  action: 'created' as const,
  status: 'firing' as const,
  service: 'checkout',
  item: 'error_rate' as const,
  value: 0.2,
  resource_id: 'r1',
  resource_name: 'checkout',
  start_time: '2026-08-06T02:00:00Z',
  end_time: null,
  received_at: '2026-08-06T02:00:00Z',
  policy_id: 'p1',
  environment: 'prod',
  notification_deliveries: [{
    id: 'd1',
    event_id: 'evt-1',
    channel_id: 1,
    channel_name: '运维群',
    channel_type: 'email',
    delivery_mode: 'message' as const,
    recipients: ['ops@example.com'],
    status: 'failed' as const,
    attempts: 2,
    last_error_code: 'timeout',
    last_error_message: 'smtp timeout',
  }],
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
  api.getEvents.mockResolvedValue([firingEvent]);
  api.retryNotificationDelivery.mockResolvedValue({
    ...firingEvent.notification_deliveries[0],
    status: 'pending',
    attempts: 3,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 告警详情抽屉', () => {
  it('点击详情打开告警抽屉并展示投递信息', async () => {
    const user = userEvent.setup();
    render(<ApmEventsPage />);

    expect(await screen.findByText('checkout 错误率升高')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '详情' }));

    expect(await screen.findByText('近 5 分钟错误率超过阈值')).not.toBeNull();
    expect(screen.getByText('运维群')).not.toBeNull();
    expect(screen.getByText('终止失败')).not.toBeNull();
  });

  it('可在详情抽屉中人工重投失败通知', async () => {
    const user = userEvent.setup();
    render(<ApmEventsPage />);
    await screen.findByText('checkout 错误率升高');
    await user.click(screen.getByRole('button', { name: '详情' }));
    await screen.findByText('运维群');

    await user.click(screen.getByRole('button', { name: '人工重投' }));

    await waitFor(() => expect(api.retryNotificationDelivery).toHaveBeenCalledWith('d1'));
  });
});
