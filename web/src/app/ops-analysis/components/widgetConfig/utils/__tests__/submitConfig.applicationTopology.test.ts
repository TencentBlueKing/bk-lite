import { describe, expect, it } from 'vitest';
import { buildWidgetSubmitConfig, persistApplicationTopologyConfig } from '../submitConfig';
import {
  APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
  APPLICATION_TOPOLOGY_FILTER_ID,
} from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';

const base = {
  name: '应用拓扑',
  chartType: 'applicationTopology',
  sceneWidgetType: 'applicationTopology' as const,
};

describe('applicationTopology submit config', () => {
  it('persists depth and the canvas filter binding without an instance', () => {
    const saved = buildWidgetSubmitConfig({
      values: {
        ...base,
        applicationTopology: { depth: 4 },
      },
      chartType: 'applicationTopology',
      showChartThemeMode: false,
      showTableFilterFields: false,
      selectedFields: [],
      thresholdColors: [],
      filterBindings: {},
      displayColumns: [],
      filterFields: [],
      actions: [],
    });
    expect(saved.error).toBeUndefined();
    expect(saved.config?.applicationTopology).toEqual({
      modelId: 'system',
      depth: 4,
    });
    expect(saved.config?.filterBindings).toEqual({
      [APPLICATION_TOPOLOGY_FILTER_ID]: true,
      [APPLICATION_TOPOLOGY_DEPTH_FILTER_ID]: true,
    });
    expect(persistApplicationTopologyConfig({ depth: 9 }).depth).toBe(3);
  });
});
