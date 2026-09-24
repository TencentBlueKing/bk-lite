import { describe, expect, it } from 'vitest';
import { buildWidgetSubmitConfig } from '../submitConfig';
import { resolveApplication3DWallConfig } from '@/app/ops-analysis/utils/application3DWallConfig';

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
      application3DWall: resolveApplication3DWallConfig(undefined),
      appearance: { frame: 'bare' },
    });
    expect(result.config?.application3DWall).toEqual({
      pageSize: 24,
      alarmPagesEnabled: false,
      alarmPageSize: 24,
      autoPageEnabled: false,
      dwellSeconds: 10,
      pageEffect: 'slide',
    });
    expect(result.config).not.toHaveProperty('dataSource');
    expect(result.config).not.toHaveProperty('networkStatusTopology');
  });

  it('keeps a stored alarm page size when alarm pages are off, and turns auto page on', () => {
    const result = buildWidgetSubmitConfig({
      values: {
        name: '3D应用',
        chartType: 'application3D',
        sceneWidgetType: 'application3D',
        application3DWall: {
          pageSize: 36,
          alarmPagesEnabled: false,
          alarmPageSize: 12,
          autoPageEnabled: true,
          dwellSeconds: 8,
          pageEffect: 'fade',
        },
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

    expect(result.config?.application3DWall).toEqual({
      pageSize: 36,
      alarmPagesEnabled: false,
      alarmPageSize: 12,
      autoPageEnabled: true,
      dwellSeconds: 8,
      pageEffect: 'fade',
    });
  });

  it('clamps page size and dwell and falls back to slide for an unknown effect', () => {
    expect(resolveApplication3DWallConfig({
      pageSize: 99,
      dwellSeconds: 1,
      pageEffect: 'cube' as 'slide',
      autoPageEnabled: true,
    })).toEqual({
      pageSize: 36,
      alarmPagesEnabled: false,
      alarmPageSize: 24,
      autoPageEnabled: true,
      dwellSeconds: 5,
      pageEffect: 'slide',
    });
  });
});
