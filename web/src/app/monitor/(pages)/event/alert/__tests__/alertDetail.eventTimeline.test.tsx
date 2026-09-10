import React, { createRef } from 'react';
import { cleanup, render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ModalRef } from '@/app/monitor/types';
import zh from '@/app/monitor/locales/zh.json';
import AlertDetail from '../alertDetail';

vi.mock('@/components/operate-drawer', () => ({
  default: ({
    children,
    visible
  }: {
    children: React.ReactNode;
    visible?: boolean;
  }) => (visible ? <div>{children}</div> : null)
}));

vi.mock('../information', () => ({
  default: () => <div data-testid="information-panel" />
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({ convertToLocalizedTime: (value: string) => value })
}));

vi.mock('@/app/monitor/hooks/useUnitTransform', () => ({
  useUnitTransform: () => ({
    getEnumValueUnit: (_metric: unknown, value: unknown) => String(value ?? ''),
    findUnitNameById: (unitId?: string) => unitId || ''
  })
}));

vi.mock('@/app/monitor/hooks', () => ({
  useLevelList: () => [{ value: 'critical', label: '严重' }],
  useStateMap: () => ({ new: '活跃' }),
  useAlertTypeMap: () => ({ alert: '阈值' })
}));

vi.mock('@/app/monitor/api', () => ({
  default: () => ({
    getMonitorMetrics: vi.fn().mockResolvedValue({ items: [] })
  })
}));

const getMonitorEventDetail = vi.fn();
const getSnapshot = vi.fn().mockResolvedValue({ snapshots: [], chart_unit: '' });
const getEventRaw = vi.fn().mockResolvedValue({});

vi.mock('@/app/monitor/api/event', () => ({
  default: () => ({
    getMonitorEventDetail,
    getSnapshot,
    getEventRaw
  })
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const value = key
        .split('.')
        .reduce<unknown>((current, segment) => {
          if (!current || typeof current !== 'object') return undefined;
          return (current as Record<string, unknown>)[segment];
        }, zh);
      return typeof value === 'string' ? value : key;
    }
  })
}));

beforeEach(() => {
  getMonitorEventDetail.mockResolvedValue({
    results: [
      {
        id: 'ev-1',
        action: 'triggered',
        event_time: '2026-01-01 12:00:00',
        content: 'CPU 超阈值',
        value: 95,
        level: 'critical'
      },
      {
        id: 'ev-2',
        action: 'claimed',
        event_time: '2026-01-01 12:05:00',
        content: 'sre 认领，处理人变为 sre',
        value: 95,
        level: 'critical'
      },
      {
        id: 'ev-3',
        action: 'assigned',
        event_time: '2026-01-01 12:06:00',
        content: 'sre 分派给 bob',
        value: 95,
        level: 'critical'
      }
    ]
  });
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

describe('告警详情事件时间线', { timeout: 15000 }, () => {
  it('展示动作文案，且不再按 Event 计数渲染热力图', async () => {
    const ref = createRef<ModalRef>();
    render(
      <AlertDetail ref={ref} objects={[]} userList={[]} onSuccess={vi.fn()} />
    );

    await act(async () => {
      ref.current?.showModal({
        type: 'alert',
        title: '告警详情',
        form: {
          id: 1,
          status: 'new',
          level: 'critical',
          content: 'CPU 超阈值',
          alert_type: 'alert',
          updated_at: '2026-01-01 12:00:00',
          policy: {
            query_condition: { type: 'metric' }
          }
        }
      });
    });

    await screen.findByText('CPU 超阈值');

    await waitFor(() => {
      expect(getMonitorEventDetail).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ page: 1, page_size: -1 }),
      );
    });

    await userEvent.click(screen.getByText('事件'));
    expect(await screen.findByText('触发')).toBeTruthy();
    expect(await screen.findByText('认领')).toBeTruthy();
    expect(await screen.findByText('分派')).toBeTruthy();
    expect(screen.getAllByText('严重').length).toBeGreaterThanOrEqual(2);
    expect(document.querySelector('svg.heatmap, .event-heat-map')).toBeNull();
    expect(screen.queryByText('monitor.events.eventTriggered')).toBeNull();
  });
});
