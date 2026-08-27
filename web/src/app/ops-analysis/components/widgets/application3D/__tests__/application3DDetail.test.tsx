import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Application3DDetail from '../application3DDetail';
import { NEON_PANEL } from '../application3DVisual';
import type {
  Application3DDetailData,
  Application3DHealth,
  Application3DWallItem,
} from '@/app/ops-analysis/types/sceneWidget';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

const noop = () => undefined;

const criticalHealth: Application3DHealth = {
  state: 'alarming',
  reason: 'active_alarm',
  activeAlarmCount: 1,
  severityCounts: { critical: 1, error: 0, warning: 0, info: 0 },
  noDataAlarmCount: 0,
  highestSeverity: { id: 'critical', label: '致命', rank: 400, color: 'critical' },
  stale: false,
};

const selected: Application3DWallItem = {
  id: 'app-1',
  name: '运营门户',
  health: criticalHealth,
};

const detail: Application3DDetailData = {
  application: {
    id: 'app-1',
    name: '运营门户',
    health: criticalHealth,
    properties: [{ key: 'owner', label: '负责人', displayValue: '张三' }],
  },
  alarms: {
    state: 'available',
    activeAlarmCount: 1,
    severityCounts: { critical: 1, error: 0, warning: 0, info: 0 },
    noDataAlarmCount: 0,
    highestSeverity: { id: 'critical', label: '致命', rank: 400, color: 'critical' },
    items: [{
      id: 'alarm-1',
      content: 'CPU 过高',
      severity: { id: 'critical', label: '致命', rank: 400, color: 'critical' },
      isNoData: false,
      occurredAt: '2026-08-26T00:00:00Z',
      resource: { id: 'host-1', name: 'host-1' },
      metricName: 'cpu',
      durationSeconds: 60,
      policyName: 'CPU 策略',
    }],
    page: { nextCursor: null, hasMore: false },
  },
  refreshedAt: '2026-08-26T00:00:00Z',
};

const panelHandlers = {
  alarmDetail: null,
  metric: null,
  alarmLoading: false,
  metricLoading: false,
  moreAlarmsLoading: false,
  onClose: noop,
  onRetry: noop,
  onRetryAlarm: noop,
  onOpenAlarm: noop,
  onCloseAlarm: noop,
  onNavigateAlarm: noop,
  onRetryMetric: noop,
  onLoadMoreAlarms: noop,
};

describe('application3D detail panels', () => {
  it('keeps application info still while alarm detail is loading', () => {
    const view = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
        alarmLoading
      />,
    );

    const left = view.container.querySelector('.app3d-biz-panel');
    const right = view.container.querySelector('.app3d-alarm-panel');
    expect(left?.textContent).toContain('运营门户');
    expect(left?.textContent).toContain('张三');
    expect(left?.querySelector('.ant-spin')).toBeNull();
    expect(right?.querySelector('.ant-spin')).not.toBeNull();
  });

  it('uses wall card health for panel color while detail is still loading', () => {
    const view = render(
      <Application3DDetail
        selected={selected}
        detail={null}
        loading
        {...panelHandlers}
      />,
    );

    const left = view.container.querySelector('.app3d-biz-panel');
    const style = left?.getAttribute('style') ?? '';
    expect(style).toContain(NEON_PANEL.fatal.border);
    expect(style).not.toContain(NEON_PANEL.normal.border);
    expect(left?.textContent).toContain('运营门户');
  });
});

