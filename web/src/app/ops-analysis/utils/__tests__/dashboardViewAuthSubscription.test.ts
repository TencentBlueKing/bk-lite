import { describe, expect, it } from 'vitest';

import { hasAppAccess } from '@/context/appCapabilities/access';
import type { DashboardWidgetLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { isDashboardWidgetUnauthorized } from '@/app/ops-analysis/utils/dashboardWidgetAuth';

describe('subscription view auth uses required_app', () => {
  const widget: DashboardWidgetLayoutItem = {
    i: 'w-chart',
    x: 0,
    y: 0,
    w: 8,
    h: 4,
    itemType: 'widget',
    name: 'chart',
    chartType: 'line',
    groupId: 'g1',
    valueConfig: { chartType: 'line', dataSource: 42 },
  };

  it('does not omit when the payload only says hasAuth false', () => {
    const dataSources = [{ id: 42, hasAuth: false, required_app: null }] as DatasourceItem[];
    expect(
      isDashboardWidgetUnauthorized(widget, {
        dataSources,
        hasAppAccess: () => false,
      }),
    ).toBe(false);
  });

  it('omits from the execution identity app list and required_app without rest_api', () => {
    const dataSources = [{
      id: 42,
      hasAuth: false,
      required_app: 'alarm',
    }] as DatasourceItem[];
    const apps = [{ name: 'monitor' }];
    expect(dataSources[0]?.rest_api).toBeUndefined();
    expect(
      isDashboardWidgetUnauthorized(widget, {
        dataSources,
        hasAppAccess: (appName) => hasAppAccess(apps, appName),
      }),
    ).toBe(true);
    expect(
      isDashboardWidgetUnauthorized(widget, {
        dataSources,
        hasAppAccess: (appName) => hasAppAccess([{ name: 'alarm' }], appName),
      }),
    ).toBe(false);
  });
});
