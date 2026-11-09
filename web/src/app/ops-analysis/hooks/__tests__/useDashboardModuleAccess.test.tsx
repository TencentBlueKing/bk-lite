// @vitest-environment jsdom

import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useDashboardModuleAccess } from '@/app/ops-analysis/hooks/useDashboardModuleAccess';
import type { DashboardLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { hasAppAccess } from '@/context/appCapabilities/access';
import {
  isModuleLicenseCanvasEmpty,
  omitFullyUnauthorizedDashboardGroups,
} from '@/app/ops-analysis/utils/dashboardGroupViewVisibility';
import { isDashboardWidgetUnauthorized } from '@/app/ops-analysis/utils/dashboardWidgetAuth';

vi.mock('@/context/client', () => ({
  useOptionalClientData: () => ({
    clientData: [{ name: 'cmdb' }, { name: 'monitor' }, { name: 'alarm' }],
    loading: false,
  }),
}));

const source = (id: number, requiredApp: string): DatasourceItem => ({
  id,
  name: requiredApp,
  hasAuth: true,
  required_app: requiredApp,
} as DatasourceItem);

const widget = (
  id: string,
  dataSourceId: number,
  groupId: string | null,
): DashboardLayoutItem => ({
  i: id,
  x: 0,
  y: 0,
  w: 8,
  h: 4,
  itemType: 'widget',
  name: id,
  chartType: 'single',
  groupId,
  valueConfig: { chartType: 'single', dataSource: dataSourceId },
});

const group = (id: string): DashboardLayoutItem => ({
  i: id,
  x: 0,
  y: 0,
  w: 24,
  h: 1,
  itemType: 'group',
  name: id,
});

const decide = (appNames: readonly string[], items: DashboardLayoutItem[], dataSources: DatasourceItem[]) => {
  const allowed = appNames.map((name) => ({ name }));
  const isWidgetUnauthorized = (widgetId: string) => {
    const item = items.find((entry) => entry.i === widgetId);
    if (!item || item.itemType === 'group') return false;
    return isDashboardWidgetUnauthorized(item, {
      dataSources,
      hasAppAccess: (appName) => hasAppAccess(allowed, appName),
    });
  };
  return {
    kept: omitFullyUnauthorizedDashboardGroups(items, isWidgetUnauthorized).map((item) => item.i),
    empty: isModuleLicenseCanvasEmpty({
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      items,
      isWidgetUnauthorized,
    }),
  };
};

describe('useDashboardModuleAccess identity', () => {
  it('uses the opener client list on a normal local view', () => {
    const { result } = renderHook(() => useDashboardModuleAccess(false, null));

    expect(result.current.appAccessReady).toBe(true);
    expect(result.current.authorizedAppNames).toEqual(['cmdb', 'monitor', 'alarm']);
  });

  it('share and subscription follow identity A when the browser session has more apps', () => {
    const identityApps = ['cmdb'] as const;
    const share = renderHook(() => useDashboardModuleAccess(true, identityApps));
    const subscription = renderHook(() => useDashboardModuleAccess(true, identityApps));

    expect(share.result.current.authorizedAppNames).toEqual(['cmdb']);
    expect(subscription.result.current.authorizedAppNames).toEqual(['cmdb']);

    const items = [
      group('overview'),
      widget('w-cmdb', 1, 'overview'),
      group('monitor'),
      widget('w-monitor', 2, 'monitor'),
      group('alarm'),
      widget('w-alarm', 3, 'alarm'),
    ];
    const dataSources = [source(1, 'cmdb'), source(2, 'monitor'), source(3, 'alarm')];
    const identity = decide(share.result.current.authorizedAppNames, items, dataSources);
    const opener = decide(['cmdb', 'monitor', 'alarm'], items, dataSources);

    expect(identity.kept).toEqual(['overview', 'w-cmdb']);
    expect(identity.empty).toBe(false);
    expect(opener.kept).toEqual(items.map((item) => item.i));
  });

  it('does not treat a missing share or subscription app list as the opener list', () => {
    const { result } = renderHook(() => useDashboardModuleAccess(true, null));

    expect(result.current.appAccessReady).toBe(false);
    expect(result.current.authorizedAppNames).toEqual([]);
  });

  it('hides the whole canvas when every stored widget needs an app the identity lacks', () => {
    const { result } = renderHook(() => useDashboardModuleAccess(true, ['cmdb']));
    const items = [widget('w-monitor', 2, null), widget('w-alarm', 3, null)];

    expect(decide(
      result.current.authorizedAppNames,
      items,
      [source(2, 'monitor'), source(3, 'alarm')],
    ).empty).toBe(true);
  });
});
