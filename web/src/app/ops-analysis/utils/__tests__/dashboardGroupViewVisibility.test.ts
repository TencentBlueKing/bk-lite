import { describe, expect, it } from 'vitest';

import type {
  DashboardGroupLayoutItem,
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
} from '@/app/ops-analysis/types/dashBoard';
import {
  deriveDashboardGridDisplayLayout,
  isModuleLicenseCanvasEmpty,
  omitFullyUnauthorizedDashboardGroups,
  selectDashboardTopLevelRenderBlocks,
  selectDashboardViewRenderWidgetIds,
  shouldHoldDashboardRenderSignal,
} from '@/app/ops-analysis/utils/dashboardGroupViewVisibility';

const group = (
  id: string,
  y: number,
  h = 1,
): DashboardGroupLayoutItem => ({
  i: id,
  x: 0,
  y,
  w: 24,
  h,
  itemType: 'group',
  name: id,
});

const widget = (
  id: string,
  y: number,
  options: { groupId?: string; h?: number } = {},
): DashboardWidgetLayoutItem => ({
  i: id,
  x: 0,
  y,
  w: 8,
  h: options.h ?? 4,
  itemType: 'widget',
  name: id,
  chartType: 'line',
  groupId: options.groupId ?? null,
  valueConfig: { chartType: 'line' },
});

const topologyWidget = (
  id: string,
  y: number,
  options: { groupId?: string; h?: number } = {},
): DashboardWidgetLayoutItem => ({
  i: id,
  x: 0,
  y,
  w: 8,
  h: options.h ?? 4,
  itemType: 'widget',
  name: id,
  chartType: 'relatedTopology',
  groupId: options.groupId ?? null,
  valueConfig: {
    chartType: 'relatedTopology',
    sceneWidgetType: 'relatedTopology',
    relatedTopology: {
      instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      modelId: 'host',
    },
  },
});

describe('dashboard group view visibility', () => {
  const unauthorized = new Set(['w-denied']);

  const isWidgetUnauthorized = (widgetId: string) => unauthorized.has(widgetId);

  it('hides a group when every widget is unauthorized and compacts blocks below', () => {
    const layout: DashboardLayoutItem[] = [
      group('g-hidden', 0),
      widget('w-denied', 1, { groupId: 'g-hidden' }),
      group('g-visible', 10),
      widget('w-ok', 11, { groupId: 'g-visible' }),
    ];

    const blocks = selectDashboardTopLevelRenderBlocks({
      items: layout,
      mode: 'view',
      isWidgetUnauthorized,
    });

    expect(blocks.map((block) => block.key)).toEqual(['g-visible']);

    const display = deriveDashboardGridDisplayLayout({
      items: layout,
      mode: 'view',
      isWidgetUnauthorized,
    });
    const visibleGroup = display.find((item) => item.i === 'g-visible');
    expect(visibleGroup?.y).toBe(0);
  });

  it('keeps a group when any widget is still visible', () => {
    const layout: DashboardLayoutItem[] = [
      group('g-mixed', 0),
      widget('w-denied', 1, { groupId: 'g-mixed' }),
      widget('w-ok', 1, { groupId: 'g-mixed', h: 4 }),
    ];

    const blocks = selectDashboardTopLevelRenderBlocks({
      items: layout,
      mode: 'view',
      isWidgetUnauthorized,
    });

    expect(blocks.map((block) => block.key)).toEqual(['g-mixed']);
  });

  it('keeps empty groups and ungrouped unauthorized widgets', () => {
    const layout: DashboardLayoutItem[] = [
      group('g-empty', 0),
      widget('w-denied', 8),
    ];

    const omitted = omitFullyUnauthorizedDashboardGroups(layout, isWidgetUnauthorized);
    expect(omitted.map((item) => item.i)).toEqual(['g-empty', 'w-denied']);
  });

  it('recomputes omission when switching from edit to view', () => {
    const layout: DashboardLayoutItem[] = [
      group('g-hidden', 0),
      widget('w-denied', 1, { groupId: 'g-hidden' }),
    ];

    const editBlocks = selectDashboardTopLevelRenderBlocks({
      items: layout,
      mode: 'edit',
      isWidgetUnauthorized,
    });
    expect(editBlocks.map((block) => block.key)).toEqual(['g-hidden']);

    const viewBlocks = selectDashboardTopLevelRenderBlocks({
      items: layout,
      mode: 'view',
      isWidgetUnauthorized,
    });
    expect(viewBlocks.map((block) => block.key)).toEqual([]);
  });

  it('does not omit groups in edit mode', () => {
    const layout: DashboardLayoutItem[] = [
      group('g-hidden', 0),
      widget('w-denied', 1, { groupId: 'g-hidden' }),
    ];

    const blocks = selectDashboardTopLevelRenderBlocks({
      items: layout,
      mode: 'edit',
      isWidgetUnauthorized,
    });

    expect(blocks.map((block) => block.key)).toEqual(['g-hidden']);
  });

  it('treats missing unauthorized conclusions as visible for omission', () => {
    const layout: DashboardLayoutItem[] = [
      group('g-hidden', 0),
      widget('w-other', 1, { groupId: 'g-hidden' }),
    ];

    const blocks = selectDashboardTopLevelRenderBlocks({
      items: layout,
      mode: 'view',
      isWidgetUnauthorized,
    });

    expect(blocks.map((block) => block.key)).toEqual(['g-hidden']);
  });
});

describe('module license canvas empty', () => {
  const unauthorized = new Set(['w-denied', 'w-denied-2']);
  const isWidgetUnauthorized = (widgetId: string) => unauthorized.has(widgetId);
  const omittedLayout: DashboardLayoutItem[] = [
    group('g-hidden', 0),
    widget('w-denied', 1, { groupId: 'g-hidden' }),
    group('g-hidden-2', 10),
    widget('w-denied-2', 11, { groupId: 'g-hidden-2' }),
  ];

  it('is empty when every grouped widget is module-invisible', () => {
    expect(isModuleLicenseCanvasEmpty({
      items: omittedLayout,
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(true);
  });

  it('is empty when every ungrouped widget is module-invisible', () => {
    const items: DashboardLayoutItem[] = [
      widget('w-denied', 0),
      widget('w-denied-2', 4),
    ];
    expect(isModuleLicenseCanvasEmpty({
      items,
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(true);
    expect(deriveDashboardGridDisplayLayout({
      items,
      mode: 'view',
      isWidgetUnauthorized,
    }).map((item) => item.i)).toEqual(['w-denied', 'w-denied-2']);
    expect(selectDashboardViewRenderWidgetIds({
      items,
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toEqual([]);
  });

  it('stays closed while resources are not ready', () => {
    expect(isModuleLicenseCanvasEmpty({
      items: omittedLayout,
      mode: 'view',
      resourcesReady: false,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(false);
  });

  it('stays closed before the auth snapshot is frozen', () => {
    expect(isModuleLicenseCanvasEmpty({
      items: omittedLayout,
      mode: 'view',
      resourcesReady: true,
      frozen: false,
      isWidgetUnauthorized,
    })).toBe(false);
  });

  it('does not fire in edit mode', () => {
    expect(isModuleLicenseCanvasEmpty({
      items: omittedLayout,
      mode: 'edit',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(false);
  });

  it('does not treat a saved-empty canvas as missing module licenses', () => {
    expect(isModuleLicenseCanvasEmpty({
      items: [group('g-empty', 0)],
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(false);
  });

  it('does not fire when groups are fully omitted but one ungrouped widget stays visible', () => {
    expect(isModuleLicenseCanvasEmpty({
      items: [
        ...omittedLayout,
        widget('w-open', 20),
      ],
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(false);
  });

  it('keeps mixed ungrouped widgets in the layout when one stays module-visible', () => {
    const items: DashboardLayoutItem[] = [
      widget('w-denied', 0),
      widget('w-open', 4),
    ];
    expect(isModuleLicenseCanvasEmpty({
      items,
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(false);
    expect(deriveDashboardGridDisplayLayout({
      items,
      mode: 'view',
      isWidgetUnauthorized,
    }).map((item) => item.i)).toEqual(['w-denied', 'w-open']);
    expect(selectDashboardViewRenderWidgetIds({
      items,
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toEqual(['w-denied', 'w-open']);
  });

  it('does not fire when a grouped widget remains visible', () => {
    expect(isModuleLicenseCanvasEmpty({
      items: [
        group('g-hidden', 0),
        widget('w-denied', 1, { groupId: 'g-hidden' }),
        group('g-visible', 10),
        widget('w-ok', 11, { groupId: 'g-visible' }),
      ],
      mode: 'view',
      resourcesReady: true,
      frozen: true,
      isWidgetUnauthorized,
    })).toBe(false);
  });

  it('does not treat a decided lookup error as whole-board module empty', () => {
    const isTopoUnauthorized = (widgetId: string) => widgetId === 'w-topo';
    const items: DashboardLayoutItem[] = [
      group('g-topo', 0),
      topologyWidget('w-topo', 1, { groupId: 'g-topo' }),
      group('g-chart', 10),
      widget('w-chart', 11, { groupId: 'g-chart' }),
    ];
    const input = {
      items,
      mode: 'view' as const,
      resourcesReady: true,
      frozen: true,
      dataSourceLookupStatus: 'error' as const,
      isWidgetUnauthorized: isTopoUnauthorized,
    };
    expect(isModuleLicenseCanvasEmpty(input)).toBe(false);
    expect(selectDashboardViewRenderWidgetIds(input)).toEqual(['w-chart']);
  });
});

describe('shouldHoldDashboardRenderSignal', () => {
  it('holds while the dashboard is still loading, even if lookup already decided', () => {
    expect(shouldHoldDashboardRenderSignal({
      loading: true,
      layoutReadyDashboardId: null,
      dashboardId: 67,
    })).toBe(true);
  });

  it('holds on the first paint before this canvas layout is stored', () => {
    expect(shouldHoldDashboardRenderSignal({
      loading: false,
      layoutReadyDashboardId: null,
      dashboardId: 67,
    })).toBe(true);
  });

  it('holds when a different canvas layout is the one marked ready', () => {
    expect(shouldHoldDashboardRenderSignal({
      loading: false,
      layoutReadyDashboardId: 66,
      dashboardId: 67,
    })).toBe(true);
  });

  it('releases after this canvas layout has loaded', () => {
    expect(shouldHoldDashboardRenderSignal({
      loading: false,
      layoutReadyDashboardId: '67',
      dashboardId: '67',
    })).toBe(false);
  });
});
