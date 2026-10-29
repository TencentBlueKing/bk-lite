// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { DashboardLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import {
  SCENE_PERMISSION_TIMEOUT_MS,
  useDashboardViewAuthSnapshot,
} from '@/app/ops-analysis/hooks/useDashboardViewAuthSnapshot';

const checkDashboardScenePermissions = vi.fn();

vi.mock('@/app/ops-analysis/api/dashboardScenePermissions', () => ({
  useDashboardScenePermissionsApi: () => ({
    checkDashboardScenePermissions,
  }),
}));

const CENTER_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const topologyLayout: DashboardLayoutItem[] = [
  {
    i: 'g1',
    x: 0,
    y: 0,
    w: 12,
    h: 1,
    itemType: 'group',
    name: 'Group',
  },
  {
    i: 'w-topo',
    x: 0,
    y: 1,
    w: 8,
    h: 4,
    itemType: 'widget',
    name: 'Topo',
    chartType: 'relatedTopology',
    groupId: 'g1',
    valueConfig: {
      chartType: 'relatedTopology',
      sceneWidgetType: 'relatedTopology',
      relatedTopology: {
        instUuid: CENTER_UUID,
        modelId: 'host',
      },
    },
  },
];

const baseProps = {
  layout: topologyLayout,
  dataSources: [],
  dataSourcesReady: true,
  isEditMode: false,
  canvasDataId: 'dashboard-a',
  authorizedAppNames: ['cmdb', 'monitor', 'alarm'],
  appAccessReady: true,
  enabled: true,
};

const dataSourceOnlyLayout: DashboardLayoutItem[] = [
  topologyLayout[0],
  {
    i: 'w-chart',
    x: 0,
    y: 1,
    w: 8,
    h: 4,
    itemType: 'widget',
    name: 'Chart',
    chartType: 'line',
    groupId: 'g1',
    valueConfig: {
      chartType: 'line',
      dataSource: 1,
    },
  },
];

const layoutWithInstUuid = (instUuid: string): DashboardLayoutItem[] => [
  topologyLayout[0],
  {
    ...topologyLayout[1],
    valueConfig: {
      chartType: 'relatedTopology',
      sceneWidgetType: 'relatedTopology',
      relatedTopology: {
        instUuid,
        modelId: 'host',
      },
    },
  },
];

describe('useDashboardViewAuthSnapshot', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    checkDashboardScenePermissions.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not hide widgets after rerun times out with stale permission_denied', async () => {
    checkDashboardScenePermissions
      .mockResolvedValueOnce([{ widget_id: 'w-topo', code: 'permission_denied' }])
      .mockImplementation(() => new Promise(() => {}));

    const { result, rerender } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: baseProps,
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-topo')).toBe(false);
    expect(result.current.isScenePermissionDenied('w-topo')).toBe(true);

    rerender({ ...baseProps, isEditMode: true });
    rerender({ ...baseProps, isEditMode: false });

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(SCENE_PERMISSION_TIMEOUT_MS);
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-topo')).toBe(false);
    expect(result.current.isScenePermissionDenied('w-topo')).toBe(false);
  });

  it('clears frozen snapshot when canvasDataId changes', async () => {
    checkDashboardScenePermissions
      .mockResolvedValueOnce([{ widget_id: 'w-topo', code: 'permission_denied' }])
      .mockResolvedValueOnce([{ widget_id: 'w-topo', code: 'visible' }]);

    const { result, rerender } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: baseProps,
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isWidgetUnauthorized('w-topo')).toBe(false);
    expect(result.current.isScenePermissionDenied('w-topo')).toBe(true);

    rerender({
      ...baseProps,
      canvasDataId: 'dashboard-b',
      layout: topologyLayout,
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-topo')).toBe(false);
    expect(result.current.isScenePermissionDenied('w-topo')).toBe(false);
  });

  it('does not reuse frozen denied when scene checks rerun without edit mode', async () => {
    const firstInst = CENTER_UUID;
    const secondInst = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

    checkDashboardScenePermissions
      .mockResolvedValueOnce([{ widget_id: 'w-topo', code: 'permission_denied' }])
      .mockImplementation(() => new Promise(() => {}));

    const { result, rerender } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: {
        ...baseProps,
        layout: layoutWithInstUuid(firstInst),
      },
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isWidgetUnauthorized('w-topo')).toBe(false);
    expect(result.current.isScenePermissionDenied('w-topo')).toBe(true);

    rerender({
      ...baseProps,
      layout: layoutWithInstUuid(secondInst),
    });

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(SCENE_PERMISSION_TIMEOUT_MS);
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-topo')).toBe(false);
    expect(result.current.isScenePermissionDenied('w-topo')).toBe(false);
  });

  it('does not freeze stale required_app when switching canvasDataId without scene checks', async () => {
    const deniedSource: DatasourceItem[] = [{ id: 1, name: 'ds', hasAuth: true, required_app: 'alarm' }];
    const allowedSource: DatasourceItem[] = [{ id: 1, name: 'ds', hasAuth: false, required_app: null }];

    const appsWithoutAlarm = ['cmdb', 'monitor'];
    const { result, rerender } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: {
        ...baseProps,
        authorizedAppNames: appsWithoutAlarm,
        layout: dataSourceOnlyLayout,
        dataSources: deniedSource,
        dataSourcesReady: true,
        canvasDataId: 'dashboard-a',
      },
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(true);

    rerender({
      ...baseProps,
      authorizedAppNames: appsWithoutAlarm,
      layout: dataSourceOnlyLayout,
      dataSources: deniedSource,
      dataSourcesReady: false,
      canvasDataId: 'dashboard-b',
    });

    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(false);

    rerender({
      ...baseProps,
      authorizedAppNames: appsWithoutAlarm,
      layout: dataSourceOnlyLayout,
      dataSources: allowedSource,
      dataSourcesReady: true,
      canvasDataId: 'dashboard-b',
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(false);
  });

  it('applies required_app and viewer apps that arrive after the first freeze', async () => {
    const appsWithoutAlarm = ['cmdb', 'monitor'];
    const stubWithoutLicense: DatasourceItem[] = [{ id: 1, hasAuth: false, required_app: null }];
    const shareStub: DatasourceItem[] = [{ id: 1, hasAuth: false, required_app: 'alarm' }];

    const { result, rerender } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: {
        ...baseProps,
        authorizedAppNames: ['cmdb', 'monitor', 'alarm'],
        layout: dataSourceOnlyLayout,
        dataSources: stubWithoutLicense,
        dataSourcesReady: true,
      },
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(false);

    rerender({
      ...baseProps,
      authorizedAppNames: appsWithoutAlarm,
      layout: dataSourceOnlyLayout,
      dataSources: shareStub,
      dataSourcesReady: true,
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(true);
  });

  it('freezes a local view once client apps are ready and keeps an authorized widget', async () => {
    const monitorSource: DatasourceItem[] = [{ id: 1, name: 'ds', hasAuth: true, required_app: 'monitor' }];
    const { result, rerender } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: {
        ...baseProps,
        authorizedAppNames: [] as string[],
        appAccessReady: false,
        layout: dataSourceOnlyLayout,
        dataSources: monitorSource,
        dataSourcesReady: true,
      },
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(false);
    expect(result.current.resourcesReady).toBe(false);

    rerender({
      ...baseProps,
      authorizedAppNames: ['cmdb', 'monitor', 'alarm'],
      appAccessReady: true,
      layout: dataSourceOnlyLayout,
      dataSources: monitorSource,
      dataSourcesReady: true,
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.resourcesReady).toBe(true);
    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(false);
  });

  it('freezes after a decided lookup error without treating missing sources as module-invisible', async () => {
    const { result, rerender } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: {
        ...baseProps,
        layout: dataSourceOnlyLayout,
        dataSources: [],
        dataSourcesReady: false,
      },
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.resourcesReady).toBe(false);
    expect(result.current.frozen).toBe(false);

    rerender({
      ...baseProps,
      layout: dataSourceOnlyLayout,
      dataSources: [],
      dataSourcesReady: true,
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.resourcesReady).toBe(true);
    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(false);
  });

  it('matches a share stub whose id is numeric text', async () => {
    const shareStub = [{ id: '1', hasAuth: true, required_app: 'alarm' }] as unknown as DatasourceItem[];
    const { result } = renderHook((props) => useDashboardViewAuthSnapshot(props), {
      initialProps: {
        ...baseProps,
        authorizedAppNames: ['cmdb', 'monitor'],
        layout: dataSourceOnlyLayout,
        dataSources: shareStub,
        dataSourcesReady: true,
      },
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.frozen).toBe(true);
    expect(result.current.isWidgetUnauthorized('w-chart')).toBe(true);
  });
});
