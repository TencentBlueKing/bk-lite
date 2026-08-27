import { describe, expect, it } from 'vitest';
import { buildWidgetSubmitConfig } from '../submitConfig';

describe('application3D submit config', () => {
  it('persists only minimal scene metadata with a bare frame', () => {
    const result = buildWidgetSubmitConfig({
      values: {
        name: '3D应用',
        chartType: 'application3D',
        sceneWidgetType: 'application3D',
      },
      chartType: 'application3D',
      showChartThemeMode: false,
      showTableFilterFields: false,
      selectedFields: [],
      thresholdColors: [],
      filterBindings: {},
      displayColumns: [],
      filterFields: [],
      actions: [],
    });

    expect(result.config).toEqual({
      name: '3D应用',
      description: undefined,
      chartType: 'application3D',
      sceneWidgetType: 'application3D',
      appearance: { frame: 'bare' },
    });
    expect(result.config).not.toHaveProperty('dataSource');
    expect(result.config).not.toHaveProperty('networkStatusTopology');
  });
});
