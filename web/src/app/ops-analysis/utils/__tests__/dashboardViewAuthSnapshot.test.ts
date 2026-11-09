import { describe, expect, it } from 'vitest';

import type { DashboardWidgetLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import {
  createDashboardViewAuthFrozenSnapshot,
  createScenePermissionResultGate,
  isWidgetUnauthorizedFromFrozenSnapshot,
  mergeScenePermissionResults,
  stripScenePermissionsForWidgetIds,
} from '@/app/ops-analysis/utils/dashboardViewAuthSnapshot';

describe('dashboardViewAuthSnapshot', () => {
  it('drops late scene permission results after timeout gate closes', () => {
    const gate = createScenePermissionResultGate();
    gate.close();
    expect(
      gate.apply([{ widget_id: 'w-topo', code: 'permission_denied' }]),
    ).toBeNull();
  });

  it('mergeScenePermissionResults builds a widget map', () => {
    expect(
      mergeScenePermissionResults([
        { widget_id: 'a', code: 'permission_denied' },
        { widget_id: 'b', code: 'visible' },
      ]),
    ).toEqual({
      a: 'permission_denied',
      b: 'visible',
    });
  });

  it('timeout gate freeze keeps omission visible when late permission_denied arrives', () => {
    const widget: DashboardWidgetLayoutItem = {
      i: 'w-topo',
      x: 0,
      y: 0,
      w: 8,
      h: 4,
      itemType: 'widget',
      name: 'w-topo',
      chartType: 'relatedTopology',
      groupId: 'g1',
      valueConfig: {
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: {
          instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          modelId: 'host',
        },
      },
    };

    const gate = createScenePermissionResultGate();
    const frozen = createDashboardViewAuthFrozenSnapshot([], {}, ['cmdb']);
    gate.close();
    expect(
      gate.apply([{ widget_id: 'w-topo', code: 'permission_denied' }]),
    ).toBeNull();
    expect(isWidgetUnauthorizedFromFrozenSnapshot(widget, frozen)).toBe(false);
  });

  it('stripScenePermissionsForWidgetIds clears prior denied for a rerun cycle', () => {
    const widget: DashboardWidgetLayoutItem = {
      i: 'w-topo',
      x: 0,
      y: 0,
      w: 8,
      h: 4,
      itemType: 'widget',
      name: 'w-topo',
      chartType: 'relatedTopology',
      groupId: 'g1',
      valueConfig: {
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: {
          instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          modelId: 'host',
        },
      },
    };

    expect(
      stripScenePermissionsForWidgetIds(
        { 'w-topo': 'permission_denied', other: 'permission_denied' },
        ['w-topo'],
      ),
    ).toEqual({ other: 'permission_denied' });

    const frozenAfterTimeout = createDashboardViewAuthFrozenSnapshot([], {}, ['cmdb']);
    expect(isWidgetUnauthorizedFromFrozenSnapshot(widget, frozenAfterTimeout)).toBe(false);
  });

  it('frozen snapshot does not change when live maps receive late updates', () => {
    const widget: DashboardWidgetLayoutItem = {
      i: 'w-topo',
      x: 0,
      y: 0,
      w: 8,
      h: 4,
      itemType: 'widget',
      name: 'w-topo',
      chartType: 'relatedTopology',
      groupId: 'g1',
      valueConfig: {
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: {
          instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          modelId: 'host',
        },
      },
    };

    const frozen = createDashboardViewAuthFrozenSnapshot([], {}, ['cmdb']);
    expect(isWidgetUnauthorizedFromFrozenSnapshot(widget, frozen)).toBe(false);

    const late = createDashboardViewAuthFrozenSnapshot([], {
      'w-topo': 'permission_denied',
    }, ['cmdb']);
    expect(isWidgetUnauthorizedFromFrozenSnapshot(widget, frozen)).toBe(false);
    expect(isWidgetUnauthorizedFromFrozenSnapshot(widget, late)).toBe(false);

    const missingCmdb = createDashboardViewAuthFrozenSnapshot([], {
      'w-topo': 'visible',
    }, ['monitor']);
    expect(isWidgetUnauthorizedFromFrozenSnapshot(widget, missingCmdb)).toBe(true);
  });
});
