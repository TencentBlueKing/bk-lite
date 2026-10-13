import { describe, expect, it } from 'vitest';
import { ROOM3D_FILTER_ID } from '@/app/ops-analysis/utils/room3DScreenFilter';
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
      filterBindings: { [ROOM3D_FILTER_ID]: true },
      appearance: { frame: 'bare' },
    });
    expect(result.config).not.toHaveProperty('dataSource');
    expect(result.config).not.toHaveProperty('dataSourceParams');
  });

  it('does not persist a widget-level default room', () => {
    const result = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '3D机房',
        chartType: 'room3D',
        sceneWidgetType: 'room3D',
        room3D: { serverRoomId: ROOM_A },
      },
    });

    expect(result.config?.room3D).toEqual({});
    expect(result.config?.filterBindings).toEqual({ [ROOM3D_FILTER_ID]: true });
  });

  it('writes the room filter binding on even when stored binding is false', () => {
    const result = buildWidgetSubmitConfig({
      ...baseInput,
      filterBindings: { [ROOM3D_FILTER_ID]: false },
      values: {
        name: '3D机房',
        chartType: 'room3D',
        sceneWidgetType: 'room3D',
      },
    });

    expect(result.config?.filterBindings).toEqual({ [ROOM3D_FILTER_ID]: true });
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
