import { describe, expect, it } from 'vitest';

import type { DashboardWidgetLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { omitFullyUnauthorizedDashboardGroups } from '@/app/ops-analysis/utils/dashboardGroupViewVisibility';
import { isDashboardWidgetUnauthorized } from '@/app/ops-analysis/utils/dashboardWidgetAuth';
import { hasAppAccess } from '@/context/appCapabilities/access';

const allow = (...names: string[]) => (appName: string) =>
  hasAppAccess(names.map((name) => ({ name })), appName);

const baseWidget = (
  overrides: Partial<DashboardWidgetLayoutItem> = {},
): DashboardWidgetLayoutItem => ({
  i: 'w1',
  x: 0,
  y: 0,
  w: 8,
  h: 4,
  itemType: 'widget',
  name: 'w1',
  chartType: 'line',
  groupId: null,
  valueConfig: { chartType: 'line', dataSource: 9 },
  ...overrides,
});

const source = (overrides: Partial<DatasourceItem> = {}): DatasourceItem => ({
  id: 9,
  hasAuth: false,
  required_app: null,
  name: 'hidden',
  rest_api: 'x/y',
  source_type: 'nats',
  chart_type: ['line'],
  groups: [2],
  ...overrides,
} as DatasourceItem);

describe('isDashboardWidgetUnauthorized', () => {
  it('treats missing datasource as not unauthorized', () => {
    expect(
      isDashboardWidgetUnauthorized(baseWidget(), {
        dataSources: [],
        hasAppAccess: allow(),
      }),
    ).toBe(false);
  });

  it('treats unbound datasource as not unauthorized', () => {
    expect(
      isDashboardWidgetUnauthorized(
        baseWidget({ valueConfig: { chartType: 'line' } }),
        { dataSources: [source({ required_app: 'alarm' })], hasAppAccess: allow() },
      ),
    ).toBe(false);
  });

  it('does not treat hasAuth false as unauthorized when required_app is empty', () => {
    expect(
      isDashboardWidgetUnauthorized(baseWidget(), {
        dataSources: [source({ hasAuth: false, required_app: null })],
        hasAppAccess: allow(),
      }),
    ).toBe(false);
  });

  it('hides a chart when the share stub id is numeric text', () => {
    expect(
      isDashboardWidgetUnauthorized(baseWidget({ valueConfig: { chartType: 'line', dataSource: 9 } }), {
        dataSources: [source({ id: '9' as unknown as number, hasAuth: false, required_app: 'alarm', rest_api: undefined })],
        hasAppAccess: allow('cmdb'),
      }),
    ).toBe(true);
  });

  it('hides a chart when required_app is set and the identity lacks that app', () => {
    expect(
      isDashboardWidgetUnauthorized(baseWidget(), {
        dataSources: [source({ hasAuth: true, required_app: 'alarm' })],
        hasAppAccess: allow('monitor', 'cmdb'),
      }),
    ).toBe(true);
  });

  it('keeps a chart when the identity has the source required_app', () => {
    expect(
      isDashboardWidgetUnauthorized(baseWidget(), {
        dataSources: [source({ required_app: 'alarm' })],
        hasAppAccess: allow('alarm'),
      }),
    ).toBe(false);
  });

  it('does not hide a monitor source only because cmdb is missing', () => {
    expect(
      isDashboardWidgetUnauthorized(baseWidget(), {
        dataSources: [source({
          required_app: 'monitor',
          rest_api: 'monitor/get_cmdb_relation_alert_aggregation',
        })],
        hasAppAccess: allow('monitor'),
      }),
    ).toBe(false);
  });

  it('does not hide an external source that has no required_app', () => {
    expect(
      isDashboardWidgetUnauthorized(baseWidget(), {
        dataSources: [source({
          source_type: 'elasticsearch',
          required_app: null,
          hasAuth: false,
        })],
        hasAppAccess: allow(),
      }),
    ).toBe(false);
  });

  it('hides topology scenes without cmdb even when instance ACL is not denied', () => {
    for (const sceneType of ['relatedTopology', 'applicationTopology', 'networkStatusTopology'] as const) {
      expect(
        isDashboardWidgetUnauthorized(
          baseWidget({
            chartType: sceneType,
            valueConfig: { chartType: sceneType, sceneWidgetType: sceneType },
          }),
          { dataSources: [], hasAppAccess: allow('monitor') },
        ),
      ).toBe(true);
    }
  });

  it('keeps topology scenes when cmdb is licensed, including permission_denied', () => {
    expect(
      isDashboardWidgetUnauthorized(
        baseWidget({
          chartType: 'relatedTopology',
          valueConfig: {
            chartType: 'relatedTopology',
            sceneWidgetType: 'relatedTopology',
            relatedTopology: { modelId: 'host' },
          },
        }),
        { dataSources: [], hasAppAccess: allow('cmdb') },
      ),
    ).toBe(false);
  });

  it('does not omit a whole group only because hasAuth is false', () => {
    const layout = [
      {
        i: 'g1',
        x: 0,
        y: 0,
        w: 24,
        h: 1,
        itemType: 'group' as const,
        name: 'g1',
      },
      baseWidget({ groupId: 'g1' }),
    ];
    const omitted = omitFullyUnauthorizedDashboardGroups(layout, (widgetId) =>
      isDashboardWidgetUnauthorized(
        layout.find((item) => item.i === widgetId) as DashboardWidgetLayoutItem,
        {
          dataSources: [source({ hasAuth: false, required_app: null })],
          hasAppAccess: allow(),
        },
      ));
    expect(omitted.map((item) => item.i)).toEqual(['g1', 'w1']);
  });

  it('omits a group when every chart lacks the source module license', () => {
    const widget = baseWidget({ groupId: 'g1' });
    const layout = [
      {
        i: 'g1',
        x: 0,
        y: 0,
        w: 24,
        h: 1,
        itemType: 'group' as const,
        name: 'g1',
      },
      widget,
    ];
    const omitted = omitFullyUnauthorizedDashboardGroups(layout, () =>
      isDashboardWidgetUnauthorized(widget, {
        dataSources: [source({ required_app: 'alarm' })],
        hasAppAccess: allow('cmdb'),
      }));
    expect(omitted).toEqual([]);
  });
});
