import { describe, expect, it } from 'vitest';
import { buildWidgetSubmitConfig } from '../submitConfig';

const ROOM_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const baseInput = {
  chartType: 'room3D',
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [] as string[],
  thresholdColors: [] as never[],
  filterBindings: {},
  displayColumns: [] as never[],
  filterFields: [] as never[],
  actions: [] as never[],
};

describe('room3D submit config', () => {
  it('persists scene metadata without a dataSource and keeps an empty default', () => {
    const result = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '3D机房',
        chartType: 'room3D',
        sceneWidgetType: 'room3D',
      },
    });

    expect(result.config).toEqual({
      name: '3D机房',
      description: undefined,
      chartType: 'room3D',
      sceneWidgetType: 'room3D',
      room3D: {},
      appearance: { frame: 'bare' },
    });
    expect(result.config).not.toHaveProperty('dataSource');
    expect(result.config).not.toHaveProperty('dataSourceParams');
  });

  it('persists a valid default room id', () => {
    const result = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '3D机房',
        chartType: 'room3D',
        sceneWidgetType: 'room3D',
        room3D: { serverRoomId: ROOM_A },
      },
    });

    expect(result.config?.room3D).toEqual({ serverRoomId: ROOM_A });
  });

  it('persists rack-top lines only when they leave the default', () => {
    const defaultLines = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '3D机房',
        chartType: 'room3D',
        sceneWidgetType: 'room3D',
        room3D: {
          rackTopLine1: 'location',
          rackTopLine2: 'type',
        },
      },
    });
    expect(defaultLines.config?.room3D).toEqual({});

    const customLines = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '3D机房',
        chartType: 'room3D',
        sceneWidgetType: 'room3D',
        room3D: {
          rackTopLine1: 'name',
          rackTopLine2: '',
        },
      },
    });
    expect(customLines.config?.room3D).toEqual({
      rackTopLine1: 'name',
      rackTopLine2: '',
    });
  });
});
