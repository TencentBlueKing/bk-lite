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

const alarmItem = {
  id: 'alarm-1',
  content: 'CPU 过高',
  severity: { id: 'critical', label: '致命', rank: 400, color: 'critical' } as const,
  isNoData: false,
  occurredAt: '2026-08-26T00:00:00Z',
  resource: { id: 'host-1', name: 'host-1' },
  metricName: 'cpu',
  durationSeconds: 60,
  policyName: 'CPU 策略',
};

const availableAlarms = {
  state: 'available' as const,
  activeAlarmCount: 1,
  severityCounts: { critical: 1, error: 0, warning: 0, info: 0 },
  noDataAlarmCount: 0,
  highestSeverity: { id: 'critical', label: '致命', rank: 400, color: 'critical' } as const,
  items: [alarmItem],
  page: { nextCursor: null, hasMore: false },
};

const detail: Application3DDetailData = {
  application: {
    id: 'app-1',
    name: '运营门户',
    health: criticalHealth,
    properties: [{ key: 'owner', label: '负责人', displayValue: '张三' }],
  },
  alarms: availableAlarms,
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
    expect(style).not.toContain(NEON_PANEL.remain.border);
    expect(left?.textContent).toContain('运营门户');
  });

  it('shows product severity cells and hides info when count is zero', () => {
    const view = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
      />,
    );

    const left = view.container.querySelector('.app3d-biz-panel')?.textContent ?? '';
    expect(left).toContain('application3DSeverity_critical');
    expect(left).toContain('application3DSeverity_error');
    expect(left).toContain('application3DSeverity_warning');
    expect(left).not.toContain('application3DSeverity_info');
  });

  it('shows a defensive info row only when severityCounts.info > 0', () => {
    const infoHealth: Application3DHealth = {
      ...criticalHealth,
      activeAlarmCount: 1,
      severityCounts: { critical: 0, error: 0, warning: 0, info: 1 },
      highestSeverity: { id: 'info', label: '提示', rank: 100, color: 'info' },
    };
    const infoDetail: Application3DDetailData = {
      ...detail,
      application: { ...detail.application, health: infoHealth },
      alarms: {
        ...availableAlarms,
        activeAlarmCount: 1,
        severityCounts: { critical: 0, error: 0, warning: 0, info: 1 },
        highestSeverity: infoHealth.highestSeverity,
        items: [{
          ...alarmItem,
          severity: infoHealth.highestSeverity,
        }],
      },
    };
    const view = render(
      <Application3DDetail
        selected={{ ...selected, health: infoHealth }}
        detail={infoDetail}
        loading={false}
        {...panelHandlers}
      />,
    );

    const left = view.container.querySelector('.app3d-biz-panel');
    expect(left?.textContent).toContain('application3DSeverity_info');
    expect(left?.getAttribute('style') ?? '').toContain(NEON_PANEL.info.border);
    expect(left?.getAttribute('style') ?? '').not.toContain(NEON_PANEL.remain.border);
  });

  it('keeps no-data tag on alarm list but omits alert-type stats from left panel', () => {
    const noDataHealth: Application3DHealth = {
      ...criticalHealth,
      noDataAlarmCount: 1,
    };
    const noDataDetail: Application3DDetailData = {
      ...detail,
      application: { ...detail.application, health: noDataHealth },
      alarms: {
        ...availableAlarms,
        noDataAlarmCount: 1,
        items: [{
          ...alarmItem,
          content: '主机无数据',
          isNoData: true,
        }],
      },
    };
    const view = render(
      <Application3DDetail
        selected={{ ...selected, health: noDataHealth }}
        detail={noDataDetail}
        loading={false}
        {...panelHandlers}
      />,
    );

    const left = view.container.querySelector('.app3d-biz-panel')?.textContent ?? '';
    expect(left).not.toContain('application3DNoDataAlarm');
    expect(left).toContain('application3DSeverity_critical');
    expect(left).not.toContain('application3DSeverity_info');
    expect(view.container.textContent).toContain('主机无数据');
    expect(view.container.textContent).toContain('application3DSeverity_critical');
    expect(view.container.querySelector('.app3d-alarm-panel')?.textContent).toContain(
      'application3DNoDataAlarm',
    );
  });

  it('keeps critical panel color for no_data critical while detail is loading', () => {
    const noDataSelected: Application3DWallItem = {
      ...selected,
      health: { ...criticalHealth, noDataAlarmCount: 1 },
    };
    const view = render(
      <Application3DDetail
        selected={noDataSelected}
        detail={null}
        loading
        {...panelHandlers}
      />,
    );

    const style = view.container.querySelector('.app3d-biz-panel')?.getAttribute('style') ?? '';
    expect(style).toContain(NEON_PANEL.fatal.border);
    expect(style).not.toContain(NEON_PANEL.remain.border);
  });
});

