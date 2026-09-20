import React from 'react';
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import AlertDetailDrawer from '../alert-detail-drawer';
import ApmAlertsPage from '../page';
import type { ApmAlert, ApmEventSnapshot, ApmNotificationDelivery } from '@/app/apm/types';

const api = {
  closeAlert: vi.fn(),
  claimAlert: vi.fn(),
  assignAlert: vi.fn(),
  getAlertDistribution: vi.fn(),
  getAlerts: vi.fn(),
  getAlertSnapshots: vi.fn(),
  getEventEvidence: vi.fn(),
  getNotificationDeliveries: vi.fn(),
  getNotificationRecipients: vi.fn(),
  retryNotificationDelivery: vi.fn(),
  isLoading: false,
};
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

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
  event_count: 4,
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
    },
    {
      id: 'e4',
      event_id: 'evt-reassigned',
      action: 'reassigned',
      severity: 'error',
      value: '0.2',
      occurred_at: '2026-08-14T02:08:00Z',
      title: '转派',
      description: 'sre 转派给 alice'
    }
  ]
};

describe('APM 告警详情事件列表', { timeout: 15000 }, () => {
  it('事件流展示认领、分派与转派，不把它们画进指标快照图', async () => {
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
    expect(screen.getByText('转派')).toBeTruthy();
    expect(screen.getByText('sre 认领，处理人变为 sre')).toBeTruthy();
    expect(screen.getByText('sre 分派给 bob')).toBeTruthy();
    expect(screen.getByText('sre 转派给 alice')).toBeTruthy();
  });

  it('传入 eventEvidenceLoading 时应渲染证据加载态', async () => {
    renderWithApmIntl(
      <AlertDetailDrawer
        open
        alert={alert}
        metricSnapshot={{
          unit: 'ratio',
          aggregation: 'avg',
          evaluation_interval: 1,
          metric_window: 5,
          snapshots: [],
        }}
        metricSnapshotLoading={false}
        metricSnapshotError={null}
        selectedEvent={alert.events[0]}
        eventEvidence={null}
        eventEvidenceLoading
        eventEvidenceError={null}
        deliveries={[]}
        deliveriesLoading={false}
        deliveriesError={null}
        retryingDeliveryId={null}
        onClose={vi.fn()}
        onHandlerActionSuccess={vi.fn()}
        onRetrySnapshot={vi.fn()}
        onSelectEvent={vi.fn()}
        onRetryDelivery={vi.fn()}
        onRetryEventEvidence={vi.fn()}
        onRetryDeliveries={vi.fn()}
      />
    );

    await userEvent.click(screen.getByRole('tab', { name: '事件' }));
    expect(screen.getByLabelText('加载 APM 数据')).toBeTruthy();
  });

  it('证据与通知失败时应分区展示错误和重试', async () => {
    const retryEvidence = vi.fn();
    const retryDeliveries = vi.fn();
    renderWithApmIntl(
      <AlertDetailDrawer
        open
        alert={alert}
        metricSnapshot={{
          unit: 'ratio',
          aggregation: 'avg',
          evaluation_interval: 1,
          metric_window: 5,
          snapshots: [],
        }}
        metricSnapshotLoading={false}
        metricSnapshotError={null}
        selectedEvent={alert.events[0]}
        eventEvidence={null}
        eventEvidenceLoading={false}
        eventEvidenceError="error"
        deliveries={[]}
        deliveriesLoading={false}
        deliveriesError="error"
        retryingDeliveryId={null}
        onClose={vi.fn()}
        onHandlerActionSuccess={vi.fn()}
        onRetrySnapshot={vi.fn()}
        onSelectEvent={vi.fn()}
        onRetryDelivery={vi.fn()}
        onRetryEventEvidence={retryEvidence}
        onRetryDeliveries={retryDeliveries}
      />
    );

    await userEvent.click(screen.getByRole('tab', { name: '事件' }));
    const retryButtons = screen.getAllByRole('button', { name: '重试' });
    expect(retryButtons).toHaveLength(2);
    await userEvent.click(retryButtons[0]);
    await userEvent.click(retryButtons[1]);
    expect(retryEvidence).toHaveBeenCalledTimes(1);
    expect(retryDeliveries).toHaveBeenCalledTimes(1);
  });
});

const listEvent = {
  id: 'e1',
  event_id: 'evt-1',
  action: 'triggered' as const,
  severity: 'error' as const,
  value: '0.2',
  occurred_at: '2026-08-14T02:00:00Z',
  title: '错误率触发',
  description: '错误率超过阈值',
};
const listEventEscalated = {
  ...listEvent,
  id: 'e2',
  event_id: 'evt-2',
  action: 'escalated' as const,
  occurred_at: '2026-08-14T02:10:00Z',
  title: '错误率升级',
  description: '错误率继续升高',
};
const listAlert: ApmAlert = {
  ...alert,
  events: [listEvent],
  event_count: 1,
  last_event_at: listEvent.occurred_at,
};
const evidenceSnapshot: ApmEventSnapshot = {
  id: 'ss1',
  event_id: 'evt-1',
  schema_version: 1,
  action: 'triggered',
  occurred_at: listEvent.occurred_at,
  policy_snapshot: { name: '错误率', thresholds: [{ severity: 'error', comparator: 'gt', value: '0.1' }] },
  object_snapshot: { endpoint: 'POST /checkout', environment: 'production', version: 'v2' },
  evaluation_snapshot: {
    value: '0.2',
    unit: 'ratio',
    comparator: 'gt',
    threshold: '0.1',
    severity: 'error',
    data_state: 'available',
  },
  trace_context: {
    service_namespace: 'shop',
    service_name: 'checkout',
    endpoint: 'POST /checkout',
    environment: 'production',
    started_at: '2026-08-14T01:55:00Z',
    ended_at: listEvent.occurred_at,
  },
  payload_status: 'available',
  payload_error_code: '',
  payload: null,
  retention_expires_at: '2026-11-12T02:00:00Z',
};
const deliveryItem: ApmNotificationDelivery = {
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
  failed_at: listEvent.occurred_at,
};
const listMetricSnapshot = {
  unit: 'ratio',
  aggregation: 'avg' as const,
  evaluation_interval: 1,
  metric_window: 5,
  snapshots: [
    {
      type: 'event' as const,
      snapshot_time: listEvent.occurred_at,
      event_id: 'evt-1',
      event_time: listEvent.occurred_at,
      value: '0.2',
      threshold: { severity: 'error' as const, comparator: 'gt' as const, value: '0.1' },
      data_state: 'available' as const,
    },
  ],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function openEventTab() {
  const user = userEvent.setup();
  renderWithApmIntl(<ApmAlertsPage />);
  await user.click(await screen.findByRole('button', { name: 'checkout 错误率升高' }));
  await user.click(await screen.findByRole('tab', { name: '事件' }));
  return user;
}

describe('APM 告警事件证据与通知独立失败', { timeout: 15000 }, () => {
  beforeEach(() => {
    api.getAlerts.mockImplementation((query: { status_group?: string }) => (
      Promise.resolve(query.status_group === 'active' ? [listAlert] : [])
    ));
    api.getAlertDistribution.mockResolvedValue([]);
    api.getAlertSnapshots.mockResolvedValue(listMetricSnapshot);
    api.getEventEvidence.mockResolvedValue([evidenceSnapshot]);
    api.getNotificationDeliveries.mockResolvedValue([]);
    api.retryNotificationDelivery.mockResolvedValue(deliveryItem);
    api.closeAlert.mockResolvedValue(undefined);
    api.claimAlert.mockResolvedValue(undefined);
    api.assignAlert.mockResolvedValue(undefined);
    api.getNotificationRecipients.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('证据成功通知失败时仍展示证据，并给出通知重试', async () => {
    api.getNotificationDeliveries.mockRejectedValue(new Error('notify failed'));
    await openEventTab();

    expect(await screen.findByRole('link', { name: '查看当时调用链' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '重试' })).not.toBeNull();
    expect(screen.getByText('通知投递')).not.toBeNull();
    expect(screen.queryByText('值班群')).toBeNull();
  });

  it('通知成功证据失败时仍展示通知，并给出证据重试', async () => {
    api.getEventEvidence.mockRejectedValue(new Error('evidence failed'));
    api.getNotificationDeliveries.mockResolvedValue([deliveryItem]);
    await openEventTab();

    expect(await screen.findByText('值班群')).not.toBeNull();
    expect(screen.getByRole('button', { name: '重试' })).not.toBeNull();
    expect(screen.queryByRole('link', { name: '查看当时调用链' })).toBeNull();
  });

  it('两侧都失败时各自有错误和重试，重试只刷新对应请求', async () => {
    api.getEventEvidence.mockRejectedValue(new Error('evidence failed'));
    api.getNotificationDeliveries.mockRejectedValue(new Error('notify failed'));
    const user = await openEventTab();

    const retryButtons = await screen.findAllByRole('button', { name: '重试' });
    expect(retryButtons).toHaveLength(2);
    expect(screen.getAllByRole('alert')).toHaveLength(2);

    api.getEventEvidence.mockResolvedValue([evidenceSnapshot]);
    await user.click(retryButtons[0]);
    expect(await screen.findByRole('link', { name: '查看当时调用链' })).not.toBeNull();
    expect(api.getEventEvidence).toHaveBeenCalledTimes(2);
    expect(api.getNotificationDeliveries).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole('button', { name: '重试' })).toHaveLength(1);
  });

  it('旧失败晚到不得覆盖新成功', async () => {
    const firstEvidence = deferred<ApmEventSnapshot[]>();
    const secondEvidence = deferred<ApmEventSnapshot[]>();
    let evidenceCalls = 0;
    api.getAlerts.mockImplementation((query: { status_group?: string }) => (
      Promise.resolve(query.status_group === 'active' ? [{
        ...listAlert,
        events: [listEvent, listEventEscalated],
        event_count: 2,
        last_event_at: listEventEscalated.occurred_at,
      }] : [])
    ));
    api.getAlertSnapshots.mockResolvedValue({
      ...listMetricSnapshot,
      snapshots: [
        ...listMetricSnapshot.snapshots,
        {
          type: 'event' as const,
          snapshot_time: listEventEscalated.occurred_at,
          event_id: 'evt-2',
          event_time: listEventEscalated.occurred_at,
          value: '0.3',
          threshold: { severity: 'error' as const, comparator: 'gt' as const, value: '0.1' },
          data_state: 'available' as const,
        },
      ],
    });
    api.getEventEvidence.mockImplementation(() => {
      evidenceCalls += 1;
      return evidenceCalls === 1 ? firstEvidence.promise : secondEvidence.promise;
    });
    const user = await openEventTab();
    const streamItems = within(screen.getByRole('list', { name: '事件流时间线' })).getAllByRole('listitem');
    await user.click(streamItems[streamItems.length - 1]);
    secondEvidence.resolve([evidenceSnapshot]);
    expect(await screen.findByRole('link', { name: '查看当时调用链' })).not.toBeNull();

    firstEvidence.reject(new Error('stale evidence'));
    await waitFor(() => {
      expect(screen.getByRole('link', { name: '查看当时调用链' })).not.toBeNull();
      expect(screen.queryByRole('button', { name: '重试' })).toBeNull();
    });
  });
});
