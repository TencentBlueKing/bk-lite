import { describe, expect, it } from 'vitest';
import type { ScreenItem } from '@/app/ops-analysis/types/screen';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
  APPLICATION_TOPOLOGY_DEPTH_FILTER_INPUT_CONFIG,
  APPLICATION_TOPOLOGY_DEPTH_FILTER_NAME,
  APPLICATION_TOPOLOGY_FILTER_ID,
  APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG,
  APPLICATION_TOPOLOGY_FILTER_NAME,
  ensureApplicationTopologyCanvasFilter,
  relabelApplicationTopologyFilters,
  resolveApplicationTopologyCanvasSelection,
  resolveApplicationTopologyDepth,
} from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';

const SYSTEM = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const widget = {
  type: 'widget',
  chartType: 'applicationTopology',
  valueConfig: {
    chartType: 'applicationTopology',
    sceneWidgetType: 'applicationTopology',
    applicationTopology: { instUuid: SYSTEM, depth: 3 },
  },
} as ScreenItem;

describe('application topology canvas filter', () => {
  it('adds the system and depth filters when the canvas has the widget', () => {
    const filters = ensureApplicationTopologyCanvasFilter([], [widget]);
    expect(filters).toEqual([
      expect.objectContaining({
        id: APPLICATION_TOPOLOGY_FILTER_ID,
        name: APPLICATION_TOPOLOGY_FILTER_NAME,
        defaultValue: SYSTEM,
        inputConfig: APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG,
      }),
      expect.objectContaining({
        id: APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
        name: APPLICATION_TOPOLOGY_DEPTH_FILTER_NAME,
        defaultValue: '3',
        inputConfig: APPLICATION_TOPOLOGY_DEPTH_FILTER_INPUT_CONFIG,
      }),
    ]);
  });

  it('adds the depth filter even when the system filter is already stored', () => {
    const systemFilter = {
      id: APPLICATION_TOPOLOGY_FILTER_ID,
      key: 'application_system_id',
      name: '应用系统',
      type: 'string',
      defaultValue: SYSTEM,
      order: 0,
      enabled: true,
    } as UnifiedFilterDefinition;
    const filters = ensureApplicationTopologyCanvasFilter([systemFilter], [{
      ...widget,
      valueConfig: {
        ...widget.valueConfig,
        applicationTopology: { instUuid: SYSTEM, depth: 4 },
      },
    }]);
    expect(filters.map((item) => item.id)).toEqual([
      APPLICATION_TOPOLOGY_FILTER_ID,
      APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
    ]);
    expect(filters[1]?.defaultValue).toBe('4');
  });

  it('replaces shipped default names with the current language and keeps a custom name', () => {
    const filters = ensureApplicationTopologyCanvasFilter([], [widget]);
    const labeled = relabelApplicationTopologyFilters({
      filters: [
        { ...filters[0], name: 'Application System' },
        { ...filters[1], name: '展开层级' },
        {
          id: 'other__string',
          key: 'other',
          name: '业务系统',
          type: 'string',
          enabled: true,
          order: 2,
        },
      ],
    }, {
      system: '应用系统',
      depth: '展开层级',
    });
    expect(labeled.filters?.map((item) => item.name)).toEqual([
      '应用系统',
      '展开层级',
      '业务系统',
    ]);
    expect(relabelApplicationTopologyFilters({
      filters: [{ ...filters[0], name: '我的系统' }],
    }, { system: '应用系统' }).filters?.[0].name).toBe('我的系统');
  });

  it('reads the applied depth ahead of the filter default and the widget fallback', () => {
    const filters = ensureApplicationTopologyCanvasFilter([], [widget]);
    expect(resolveApplicationTopologyDepth({
      filterDefinitions: filters,
      unifiedFilterValues: { [APPLICATION_TOPOLOGY_DEPTH_FILTER_ID]: '5' },
      fallbackDepth: 3,
    })).toBe(5);
    expect(resolveApplicationTopologyDepth({
      filterDefinitions: filters,
      unifiedFilterValues: {},
      fallbackDepth: 2,
    })).toBe(3);
    expect(resolveApplicationTopologyDepth({
      filterDefinitions: [],
      unifiedFilterValues: {},
      fallbackDepth: 2,
    })).toBe(2);
  });

  it('reads the header selection ahead of the saved default', () => {
    const filters = ensureApplicationTopologyCanvasFilter([], [widget]);
    expect(resolveApplicationTopologyCanvasSelection({
      filterDefinitions: filters,
      unifiedFilterValues: { [APPLICATION_TOPOLOGY_FILTER_ID]: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' },
      fallbackInstUuid: SYSTEM,
    })).toBe('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
    expect(resolveApplicationTopologyCanvasSelection({
      filterDefinitions: filters,
      unifiedFilterValues: {},
      fallbackInstUuid: '',
    })).toBe(SYSTEM);
  });
});
