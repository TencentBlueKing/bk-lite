import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import AlertDetailDrawer from '../alert-detail-drawer';
import type { ApmAlert } from '@/app/apm/types';

vi.mock('@/components/time-series-composed-chart', () => ({
  default: () => <div data-testid="metric-chart" />
}));

vi.mock('@/app/apm/events/alerts/alert-handler-actions', () => ({
  default: () => null
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  });
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const alert: ApmAlert = {
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
  metric_type: 'error_rate',
  severity: 'error',
  status: 'active',
  notification_status: 'delivered',
  current_value: '0.2',
  operator: '',
  handlers: [7],
  handlers_display: ['sre'],
  organizations: [10],
  started_at: '2026-08-14T02:00:00Z',
  ended_at: null,
  last_event_at: '2026-08-14T02:10:00Z',
  event_count: 3,
  events: [
    {
      id: 'e1',
      event_id: 'evt-triggered',
      action: 'triggered',
      severity: 'error',
      value: '0.2',
      occurred_at: '2026-08-14T02:00:00Z',
      title: '触发',
      description: '错误率超过阈值'
    },
    {
      id: 'e2',
      event_id: 'evt-claimed',
      action: 'claimed',
      severity: 'error',
      value: '0.2',
      occurred_at: '2026-08-14T02:05:00Z',
      title: '认领',
      description: 'sre 认领，处理人变为 sre'
    },
    {
      id: 'e3',
      event_id: 'evt-assigned',
      action: 'assigned',
      severity: 'error',
      value: '0.2',
      occurred_at: '2026-08-14T02:06:00Z',
      title: '分派',
      description: 'sre 分派给 bob'
    }
  ]
};

describe('APM 告警详情事件列表', { timeout: 15000 }, () => {
  it('事件流展示认领与分派，不把它们画进指标快照图', async () => {
    const metricSnapshot = {
      unit: 'ratio',
      aggregation: 'avg' as const,
      evaluation_interval: 1,
      metric_window: 5,
      snapshots: [
        {
          snapshot_time: '2026-08-14T02:00:00Z',
          type: 'event' as const,
          event_id: 'evt-triggered',
          event_time: '2026-08-14T02:00:00Z',
          value: '0.2',
          threshold: { severity: 'error' as const, comparator: 'gt' as const, value: '0.1' },
          data_state: 'available' as const,
        }
      ]
    };

    renderWithApmIntl(
      <AlertDetailDrawer
        open
        alert={alert}
        metricSnapshot={metricSnapshot}
        metricSnapshotLoading={false}
        metricSnapshotError={null}
        selectedEvent={null}
        eventEvidence={null}
        eventEvidenceLoading={false}
        deliveries={[]}
        retryingDeliveryId={null}
        onClose={vi.fn()}
        onHandlerActionSuccess={vi.fn()}
        onRetrySnapshot={vi.fn()}
        onSelectEvent={vi.fn()}
        onRetryDelivery={vi.fn()}
      />
    );

    expect(screen.getByTestId('metric-chart')).toBeTruthy();
    await userEvent.click(screen.getByRole('tab', { name: '事件' }));
    expect(await screen.findByText('认领')).toBeTruthy();
    expect(screen.getByText('分派')).toBeTruthy();
    expect(screen.getByText('sre 认领，处理人变为 sre')).toBeTruthy();
    expect(screen.getByText('sre 分派给 bob')).toBeTruthy();
  });
});
