import { describe, expect, it } from 'vitest';
import type { DashboardLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import { serializeDashboardGridStackLayout } from '@/app/ops-analysis/utils/dashboardGridStack';
import { prepareDashboardPlaybackDocument } from '@/app/ops-analysis/(pages)/view/dashBoard/playbackDocument';

const widget = {
  i: 'overview',
  x: 0,
  y: 0,
  w: 6,
  h: 4,
  name: '总览',
  groupId: null,
  valueConfig: { chartType: 'line', dataSource: 3 },
} satisfies DashboardLayoutItem;

describe('prepareDashboardPlaybackDocument', () => {
  it('turns a cached dashboard body into layout before widget data is loaded', () => {
    const document = prepareDashboardPlaybackDocument({
      view_sets: serializeDashboardGridStackLayout([widget]),
      other: {},
      refresh_interval: 60_000,
      filters: [],
    }, {
      canvasId: 7,
      labelFilters: (filters) => filters,
      syncValues: (_definitions, values) => values,
      organizationId: null,
      homepageMode: false,
      renderMode: false,
    });

    expect(document.layout).toHaveLength(1);
    expect(document.layout[0]).toMatchObject({ i: 'overview', name: '总览' });
    expect(document.refreshInterval).toBe(60_000);
    expect(document.definitions).toEqual([]);
  });
});
