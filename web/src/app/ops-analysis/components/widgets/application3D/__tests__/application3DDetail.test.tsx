import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Application3DDetail from '../application3DDetail';
import { DETAIL_STATUS_ACCENT } from '../application3DDetailChrome';
import type {
  Application3DDetailData,
  Application3DHealth,
  Application3DWallItem,
} from '@/app/ops-analysis/types/sceneWidget';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, defaultMessage?: string) => defaultMessage || key,
  }),
}));

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
  highestSeverity: { id: 'critical', label: '严重', rank: 400, color: 'critical' },
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
  severity: { id: 'critical', label: '严重', rank: 400, color: 'critical' } as const,
  alertType: 'alert' as const,
  isNoData: false,
  occurredAt: '2026-08-26T00:00:00Z',
  resource: { id: 'host-1', name: 'host-1' },
  metricName: 'CPU 使用率',
  durationSeconds: 60,
  policyName: 'CPU 策略',
};

const availableAlarms = {
  state: 'available' as const,
  activeAlarmCount: 1,
  severityCounts: { critical: 1, error: 0, warning: 0, info: 0 },
  noDataAlarmCount: 0,
  highestSeverity: { id: 'critical', label: '严重', rank: 400, color: 'critical' } as const,
  items: [alarmItem],
  page: { nextCursor: null, hasMore: false },
};

const detail: Application3DDetailData = {
  application: {
    id: 'app-1',
    name: '运营门户',
    health: criticalHealth,
    properties: [
      { key: 'app_id', label: '应用ID', displayValue: 'demo-app-002' },
      { key: 'operator', label: '主要维护人', displayValue: '张三' },
      { key: 'comment', label: '描述', displayValue: '演示应用' },
    ],
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

  it('uses frosted glass accent from wall health while detail is still loading', () => {
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
    expect(left?.getAttribute('data-status-tone')).toBe('critical');
    expect(style).toContain('255, 92, 84');
    expect(style).toContain(DETAIL_STATUS_ACCENT.critical.glow);
    expect(style).not.toMatch(/rgb\(\s*206,\s*220,\s*232/);
    expect(left?.textContent).toContain('运营门户');
    expect(style.toLowerCase()).not.toContain('linear-gradient(180deg, #862012');
  });

  it('shows critical/error/warning cells and omits info when count is zero', () => {
    const view = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
      />,
    );

    const left = view.container.querySelector('.app3d-biz-panel')?.textContent ?? '';
    expect(left).toContain('dashboard.application3DSeverity_critical');
    expect(left).toContain('dashboard.application3DSeverity_error');
    expect(left).toContain('dashboard.application3DSeverity_warning');
    expect(left).not.toContain('dashboard.application3DSeverity_info');
    expect(left).toContain('基本信息');
    expect(left).toContain('维护信息');
    expect(left).toContain('描述');
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
    expect(left?.textContent).toContain('dashboard.application3DSeverity_info');
    expect(left?.getAttribute('data-status-tone')).toBe('info');
    expect(left?.getAttribute('style') ?? '').toContain('96, 176, 250');
  });

  it('omits no-data tags from both panels while keeping severity badge on alarm rows', () => {
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
          alertType: 'no_data' as const,
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

    expect(view.container.textContent).not.toContain('application3DNoDataAlarm');
    expect(view.container.textContent).toContain('主机无数据');
    expect(view.container.querySelector('.app3d-severity-badge')).not.toBeNull();
  });

  it('keeps critical glass accent for no_data critical while detail is loading', () => {
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

    const left = view.container.querySelector('.app3d-biz-panel');
    expect(left?.getAttribute('data-status-tone')).toBe('critical');
    expect(left?.getAttribute('style') ?? '').toContain('255, 92, 84');
    expect(left?.getAttribute('style') ?? '').toContain(DETAIL_STATUS_ACCENT.critical.glow);
  });

  it('uses secondary glass close button below panels', () => {
    const view = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
      />,
    );
    const close = view.container.querySelector('.app3d-detail-shell > .app3d-close-cta');
    expect(close).not.toBeNull();
    expect(close?.textContent).toContain('common.close');
  });

  it('shows linked host, alert type, notification execution, and real metric name in alarm detail', () => {
    const alarmDetail = {
      applicationId: 'app-1',
      alarm: {
        id: 'alarm-1',
        content: 'CPU 过高',
        severity: { id: 'critical' as const, label: '严重', rank: 400 as const, color: 'critical' as const },
        alertType: 'alert' as const,
        isNoData: false,
        occurredAt: '2026-08-26T00:00:00Z',
        status: 'new' as const,
        durationSeconds: 60,
        resource: { id: 'host-1', name: '本地演示-host-01' },
        dimensions: [],
        metric: {
          id: '42',
          name: 'CPU 使用率',
          value: '96',
          unit: '%',
        },
        monitorContext: { objectName: 'Host', instanceName: 'host-01' },
        policy: { id: '1', name: 'application3d 本地演示策略' },
        notification: { configured: true, state: 'delivered' as const },
      },
      navigation: {
        previousAlarmId: null,
        nextAlarmId: null,
        order: 'start_event_time_desc_id_desc' as const,
      },
    };
    const metric = {
      applicationId: 'app-1',
      alarmId: 'alarm-1',
      state: 'available' as const,
      series: [{
        name: 'CPU 使用率',
        unit: '%',
        points: [
          { timestamp: '2026-08-25T17:00:00.000Z', value: 70 },
          { timestamp: '2026-08-25T17:30:00.000Z', value: 85 },
          { timestamp: '2026-08-25T18:00:00.000Z', value: 96 },
        ],
      }],
      thresholds: [{ level: 'critical' as const, value: 90, operator: '>', label: '严重' }],
      alarmMarker: { timestamp: '2026-08-25T17:45:00.000Z', label: 'CPU 过高' },
    };
    const view = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
        alarmDetail={alarmDetail}
        metric={metric}
      />,
    );
    const right = view.container.querySelector('.app3d-alarm-panel')?.textContent ?? '';
    expect(right).toContain('CPU 过高');
    expect(right).toContain('dashboard.application3DResource');
    expect(right).toContain('本地演示-host-01');
    expect(right).toContain('dashboard.application3DAlertType');
    expect(right).toContain('dashboard.application3DAlertType_alert');
    expect(right).toContain('dashboard.application3DOccurredAt');
    expect(right).toContain('dashboard.application3DDuration');
    expect(right).toContain('1m 0s');
    expect(right).toContain('dashboard.application3DPolicy');
    expect(right).toContain('application3d 本地演示策略');
    expect(right).toContain('dashboard.application3DMetric');
    expect(right).toContain('CPU 使用率');
    expect(right).not.toContain('CPU 持续超过 95%');
    expect(right).toContain('dashboard.application3DNotification');
    expect(right).toContain('dashboard.application3DNotificationConfigured');
    expect(right).toContain('dashboard.application3DNotification_delivered');
    expect(view.container.querySelector('[data-testid="app3d-metric-legend"]')?.textContent).toBe(
      'CPU 使用率 (%)',
    );
    expect(view.container.querySelector('[data-testid="app3d-threshold-label"]')?.textContent).toContain('严重 90');
    expect(view.container.querySelector('[data-testid="app3d-alarm-marker"]')).not.toBeNull();
    const markerX = Number(
      view.container.querySelector('[data-testid="app3d-alarm-marker"]')?.getAttribute('data-marker-x'),
    );
    expect(markerX).toBeGreaterThan(36);
    expect(markerX).not.toBe(150);
  });

  it('omits metric row when metric.name is null and still shows no_data alert type', () => {
    const alarmDetail = {
      applicationId: 'app-1',
      alarm: {
        id: 'alarm-2',
        content: '主机无数据',
        severity: { id: 'critical' as const, label: '严重', rank: 400 as const, color: 'critical' as const },
        alertType: 'no_data' as const,
        isNoData: true,
        occurredAt: '2026-08-26T00:00:00Z',
        status: 'new' as const,
        durationSeconds: 60,
        resource: { id: 'host-1', name: 'host-1' },
        dimensions: [],
        metric: { id: null, name: null, value: null, unit: null },
        monitorContext: { objectName: 'Host', instanceName: 'host-1' },
        policy: { id: '1', name: 'CPU 策略' },
        notification: { configured: false, state: 'not_configured' as const },
      },
      navigation: {
        previousAlarmId: null,
        nextAlarmId: null,
        order: 'start_event_time_desc_id_desc' as const,
      },
    };
    const metric = {
      applicationId: 'app-1',
      alarmId: 'alarm-2',
      state: 'available' as const,
      series: [{
        name: null,
        unit: '%',
        points: [
          { timestamp: '2026-08-25T17:00:00.000Z', value: 10 },
          { timestamp: '2026-08-25T18:00:00.000Z', value: 20 },
        ],
      }],
      thresholds: [],
      alarmMarker: null,
    };
    const view = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
        alarmDetail={alarmDetail}
        metric={metric}
      />,
    );
    const right = view.container.querySelector('.app3d-alarm-panel')?.textContent ?? '';
    expect(right).toContain('主机无数据');
    expect(right).toContain('dashboard.application3DAlertType_no_data');
    expect(right).not.toMatch(/dashboard\.application3DMetric(?!Trend|Failed|No)/);
    expect(right).toContain('dashboard.application3DNotificationNotConfigured');
    expect(view.container.querySelector('[data-testid="app3d-metric-legend"]')).toBeNull();
    expect(right).not.toContain('CPU 策略 (%)');
  });

  it('shows dimensions only when non-empty and positions marker by timestamp', () => {
    const alarmDetail = {
      applicationId: 'app-1',
      alarm: {
        id: 'alarm-3',
        content: '磁盘',
        severity: { id: 'warning' as const, label: '警告', rank: 200 as const, color: 'warning' as const },
        alertType: 'alert' as const,
        isNoData: false,
        occurredAt: null,
        status: 'new' as const,
        durationSeconds: 0,
        resource: { id: 'host-1', name: 'host-1' },
        dimensions: [
          { key: 'device', label: 'device', displayValue: 'sda1' },
          { key: 'mount', label: 'mount', displayValue: '/data' },
        ],
        metric: { id: '1', name: '磁盘使用率', value: '95', unit: '%' },
        monitorContext: { objectName: 'Host', instanceName: 'host-1' },
        policy: { id: '1', name: 'disk-policy' },
        notification: { configured: false, state: 'not_configured' as const },
      },
      navigation: {
        previousAlarmId: null,
        nextAlarmId: null,
        order: 'start_event_time_desc_id_desc' as const,
      },
    };
    const earlyMarker = {
      applicationId: 'app-1',
      alarmId: 'alarm-3',
      state: 'available' as const,
      series: [{
        name: '磁盘使用率',
        unit: '%',
        points: [
          { timestamp: '2026-08-25T17:00:00.000Z', value: 50 },
          { timestamp: '2026-08-25T18:00:00.000Z', value: 95 },
        ],
      }],
      thresholds: [{ level: 'warning' as const, value: 80, operator: '>', label: '警告' }],
      alarmMarker: { timestamp: '2026-08-25T17:00:00.000Z', label: '磁盘' },
    };
    const lateMarker = {
      ...earlyMarker,
      alarmMarker: { timestamp: '2026-08-25T18:00:00.000Z', label: '磁盘' },
    };
    const early = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
        alarmDetail={alarmDetail}
        metric={earlyMarker}
      />,
    );
    expect(early.container.querySelector('[data-testid="app3d-dimensions"]')?.textContent).toContain('sda1');
    expect(early.container.textContent).toContain('-');
    const earlyX = Number(
      early.container.querySelector('[data-testid="app3d-alarm-marker"]')?.getAttribute('data-marker-x'),
    );
    early.unmount();
    const late = render(
      <Application3DDetail
        selected={selected}
        detail={detail}
        loading={false}
        {...panelHandlers}
        alarmDetail={alarmDetail}
        metric={lateMarker}
      />,
    );
    const lateX = Number(
      late.container.querySelector('[data-testid="app3d-alarm-marker"]')?.getAttribute('data-marker-x'),
    );
    expect(lateX).toBeGreaterThan(earlyX);
  });
});
