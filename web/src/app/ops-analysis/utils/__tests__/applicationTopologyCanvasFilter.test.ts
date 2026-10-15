import { describe, expect, it } from 'vitest';
import type { ScreenItem } from '@/app/ops-analysis/types/screen';
import {
  APPLICATION_TOPOLOGY_FILTER_ID,
  APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG,
  APPLICATION_TOPOLOGY_FILTER_NAME,
  ensureApplicationTopologyCanvasFilter,
  resolveApplicationTopologyCanvasSelection,
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
  it('adds an application system filter when the canvas has the widget', () => {
    const filters = ensureApplicationTopologyCanvasFilter([], [widget]);
    expect(filters).toEqual([
      expect.objectContaining({
        id: APPLICATION_TOPOLOGY_FILTER_ID,
        name: APPLICATION_TOPOLOGY_FILTER_NAME,
        defaultValue: SYSTEM,
        inputConfig: APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG,
      }),
    ]);
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
