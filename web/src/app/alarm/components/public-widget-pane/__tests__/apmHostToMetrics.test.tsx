/**
 * 锁定用户症状：告警行（真实 API 形状）→ 复盘窗 → PublicWidgetPane →
 * ServiceOverviewWidget → getServiceRed 的 started_at/ended_at。
 * 若这里是 02:19–03:19 而浏览器仍是 now−1h，则问题在宿主运行时数据或浏览器旧 chunk。
 */
import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getService: vi.fn(),
  getServiceRed: vi.fn(),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, defaultVal?: string) => defaultVal || key,
  }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (time: string) => time,
  }),
}));

vi.mock('@/app/apm/api', () => ({ default: () => api }));

vi.mock('@/context/appCapabilities', async () => {
  const actual = await vi.importActual<typeof import('@/context/appCapabilities')>(
    '@/context/appCapabilities',
  );
  return {
    ...actual,
    useLazyAppWidget: ({
      loadWidget,
      active,
    }: {
      loadWidget: (() => Promise<{ default: unknown }>) | null;
      active: boolean;
    }) => {
      const [Widget, setWidget] = React.useState<React.ComponentType<
        Record<string, unknown>
      > | null>(null);
      React.useEffect(() => {
        if (!active || !loadWidget) return;
        let cancelled = false;
        loadWidget().then((mod) => {
          if (!cancelled) {
            setWidget(() => mod.default as React.ComponentType<Record<string, unknown>>);
          }
        });
        return () => {
          cancelled = true;
        };
      }, [active, loadWidget]);
      return { Widget, loadFailed: false };
    },
  };
});

import { PublicWidgetPane } from '../index';
import { buildAlarmApmReplayWindow } from '@/app/alarm/utils/alarmApmReplayWindow';
import ServiceOverviewWidget from '@/app/apm/components/public/ServiceOverviewWidget';

/** Asia/Shanghai 用户下 AlertModelSerializer 对 ALERT-PHASE2-HT-APM-SVC 的实际出参（DB 为 02:49:34Z） */
const PHASE2_ALERT_ROW = {
  id: 52,
  alert_id: 'ALERT-PHASE2-HT-APM-SVC',
  first_event_time: '2026-09-17 10:49:34',
  last_event_time: '2026-09-17 10:50:34',
  created_at: '2026-09-15 18:32:52',
  resource_type: 'apm_service',
  resource_id: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001',
};

describe('alarm host → ServiceOverview metrics window', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
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

  beforeEach(() => {
    api.getService.mockResolvedValue({
      id: PHASE2_ALERT_ROW.resource_id,
      name: 'phase2-ht-demo-service',
      namespace: 'default',
      language: 'go',
      status: 'active',
      environment_views: [{ environment: 'default' }],
    });
    api.getServiceRed.mockResolvedValue({
      request_rate: 1,
      error_rate: 0,
      p95_ms: 10,
      p99_ms: 20,
      top_endpoints: [],
    });
  });

  it('uses first_event_time ±30m (user TZ → UTC), not now−1h', async () => {
    const now = new Date('2026-09-17T06:04:38.486Z');
    const window = buildAlarmApmReplayWindow(
      PHASE2_ALERT_ROW,
      now,
      'Asia/Shanghai',
    );
    expect(window).toEqual({
      startedAt: '2026-09-17T02:19:34.000Z',
      endedAt: '2026-09-17T03:19:34.000Z',
    });

    render(
      <PublicWidgetPane
        active
        loadWidget={async () => ({ default: ServiceOverviewWidget })}
        identifier={PHASE2_ALERT_ROW.resource_id}
        identifierProp="serviceId"
        startedAt={window?.startedAt}
        endedAt={window?.endedAt}
      />,
    );

    await waitFor(() => {
      expect(api.getServiceRed).toHaveBeenCalled();
    });

    expect(api.getServiceRed).toHaveBeenCalledWith(
      PHASE2_ALERT_ROW.resource_id,
      'default',
      '2026-09-17T02:19:34.000Z',
      '2026-09-17T03:19:34.000Z',
    );

    const [, , startedAt, endedAt] = api.getServiceRed.mock.calls[0];
    expect(startedAt).not.toBe('2026-09-17T05:04:38.486Z');
    expect(endedAt).not.toBe('2026-09-17T06:04:38.486Z');
  });

  it('falls back to now−1h only when host omits the window (matches user URL shape)', async () => {
    render(
      <PublicWidgetPane
        active
        loadWidget={async () => ({ default: ServiceOverviewWidget })}
        identifier={PHASE2_ALERT_ROW.resource_id}
        identifierProp="serviceId"
      />,
    );

    await waitFor(() => {
      expect(api.getServiceRed).toHaveBeenCalled();
    });

    const [, , startedAt, endedAt] = api.getServiceRed.mock.calls[0] as [
      string,
      string,
      string,
      string,
    ];
    const spanMs = Date.parse(endedAt) - Date.parse(startedAt);
    expect(spanMs).toBe(60 * 60 * 1000);
    expect(startedAt).not.toBe('2026-09-17T02:19:34.000Z');
    expect(endedAt).not.toBe('2026-09-17T03:19:34.000Z');
  });

  it('remounts and refetches when host window arrives after first paint', async () => {
    const { rerender } = render(
      <PublicWidgetPane
        active
        loadWidget={async () => ({ default: ServiceOverviewWidget })}
        identifier={PHASE2_ALERT_ROW.resource_id}
        identifierProp="serviceId"
      />,
    );

    await waitFor(() => {
      expect(api.getServiceRed).toHaveBeenCalledTimes(1);
    });

    const window = buildAlarmApmReplayWindow(
      PHASE2_ALERT_ROW,
      new Date('2026-09-17T06:04:38.486Z'),
      'Asia/Shanghai',
    );

    rerender(
      <PublicWidgetPane
        active
        loadWidget={async () => ({ default: ServiceOverviewWidget })}
        identifier={PHASE2_ALERT_ROW.resource_id}
        identifierProp="serviceId"
        startedAt={window?.startedAt}
        endedAt={window?.endedAt}
      />,
    );

    await waitFor(() => {
      expect(api.getServiceRed).toHaveBeenCalledTimes(2);
    });

    expect(api.getServiceRed).toHaveBeenLastCalledWith(
      PHASE2_ALERT_ROW.resource_id,
      'default',
      '2026-09-17T02:19:34.000Z',
      '2026-09-17T03:19:34.000Z',
    );
  });
});
