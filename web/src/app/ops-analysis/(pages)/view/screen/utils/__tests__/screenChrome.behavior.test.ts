import { describe, expect, it } from 'vitest';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import {
  getDefaultScreenWidgetAppearance,
  resolveScreenWidgetAppearance,
  buildFiltersFromScreenItems,
} from '../layoutUtils';
import { buildScreenElementList } from '../screenElementList';
import {
  createScreenClockItem,
  createScreenDecorationItem,
  createScreenTextItem,
  isScreenWidgetItem,
  placeScreenItemAtPoint,
  readScreenChromeDrag,
  SCREEN_CHROME_DRAG_MIME,
} from '../screenItems';

const emptyViewSets: ScreenViewSets = {
  viewport: { width: 1920, height: 1080, adapter: 'fill' },
  items: [],
  decorations: {},
};

describe('screen widget appearance defaults', () => {
  it('uses structural defaults by chart type', () => {
    expect(getDefaultScreenWidgetAppearance('single').frame).toBe('panel');
    expect(getDefaultScreenWidgetAppearance('table').frame).toBe('panel');
    expect(getDefaultScreenWidgetAppearance('line').frame).toBe('panel');
    expect(getDefaultScreenWidgetAppearance('pie').frame).toBe('panel');
    expect(getDefaultScreenWidgetAppearance('networkStatusTopology').frame).toBe(
      'panel',
    );
    expect(getDefaultScreenWidgetAppearance('room3D').frame).toBe('bare');
    expect(getDefaultScreenWidgetAppearance('application3D').frame).toBe('bare');
  });

  it('keeps an existing 3D bare frame instead of rewriting it', () => {
    expect(
      resolveScreenWidgetAppearance('application3D', { frame: 'bare' }).frame,
    ).toBe('bare');
    expect(
      resolveScreenWidgetAppearance('line', { frame: 'panel' }).frame,
    ).toBe('panel');
    expect(
      resolveScreenWidgetAppearance('line', { frame: 'light' as 'panel' }).frame,
    ).toBe('panel');
  });
});

describe('buildFiltersFromScreenItems', () => {
  it('ignores text, clock and decorations when discovering filters', () => {
    const hostParam: ParamItem = {
      name: 'instance_ids',
      alias_name: '主机',
      type: 'string',
      filterType: 'filter',
      value: null,
    };
    const dataSources = [
      {
        id: 7,
        name: 'hosts',
        desc: '',
        params: [hostParam],
        chart_type: ['single'],
        namespaces: [],
      },
    ] as unknown as DatasourceItem[];

    const viewSets: ScreenViewSets = {
      ...emptyViewSets,
      items: [
        {
          id: 'kpi',
          type: 'widget',
          chartType: 'single',
          title: 'CPU',
          x: 0,
          y: 0,
          w: 200,
          h: 120,
          zIndex: 1,
          valueConfig: {
            chartType: 'single',
            dataSource: 7,
            dataSourceParams: [hostParam],
          },
        },
        createScreenTextItem([], { content: '说明' }),
        createScreenClockItem([]),
      ],
    };

    const definitions = buildFiltersFromScreenItems({
      viewSets,
      previousDefinitions: [],
      dataSources,
    });

    expect(definitions.map((item) => item.key)).toEqual(['instance_ids']);
  });
});

describe('buildScreenElementList', () => {
  it('orders by zIndex descending and suffixes duplicate base names', () => {
    const viewSets: ScreenViewSets = {
      ...emptyViewSets,
      items: [
        createScreenClockItem([], { id: 'clock-a', zIndex: 1 }),
        createScreenClockItem([], { id: 'clock-b', zIndex: 3 }),
        createScreenTextItem([], {
          id: 'text-a',
          zIndex: 2,
          content: '运行趋势',
        }),
        createScreenTextItem([], {
          id: 'text-b',
          zIndex: 4,
          content: '业务运行总览',
        }),
      ],
    };

    const listed = buildScreenElementList(viewSets.items, {
      clock: '时钟',
      text: '文本',
    });

    expect(listed.map((item) => item.id)).toEqual([
      'text-b',
      'clock-b',
      'text-a',
      'clock-a',
    ]);
    expect(listed.map((item) => item.label)).toEqual([
      '业务运行总览',
      '时钟',
      '运行趋势',
      '时钟-1',
    ]);
  });

  it('names a frame by its preset and suffixes the next copy', () => {
    const listed = buildScreenElementList(
      [
        createScreenDecorationItem([], 'panelFrame', 'border-21', {
          id: 'frame-a',
          zIndex: 2,
        }),
        createScreenDecorationItem([], 'panelFrame', 'border-21', {
          id: 'frame-b',
          zIndex: 1,
        }),
        createScreenDecorationItem([], 'panelFrame', 'border-22', {
          id: 'frame-c',
          zIndex: 3,
        }),
      ],
      {
        panelFramePreset: (preset) => (preset === 'border-22' ? '边框 2' : '边框 1'),
      },
    );

    expect(listed.map((item) => item.label)).toEqual(['边框2', '边框1', '边框1-1']);
  });

  it('recomputes suffixes after the upper duplicate is removed', () => {
    const remaining = [
      createScreenClockItem([], { id: 'clock-a', zIndex: 1 }),
    ];
    const listed = buildScreenElementList(remaining, { clock: '时钟' });
    expect(listed.map((item) => item.label)).toEqual(['时钟']);
  });
});

describe('screen chrome drag placement', () => {
  it('centers the dropped item on the pointer and keeps it inside the canvas', () => {
    const item = createScreenTextItem([], { id: 'text-drop', w: 100, h: 40 });
    const placed = placeScreenItemAtPoint(item, { x: 10, y: 2000 }, {
      width: 1920,
      height: 1080,
    });
    expect(placed.x).toBe(0);
    expect(placed.y).toBe(1040);
  });

  it('ignores a drop that is not a screen chrome payload', () => {
    const dataTransfer = {
      getData: (type: string) => (type === SCREEN_CHROME_DRAG_MIME ? '{"kind":"widget"}' : ''),
    } as DataTransfer;
    expect(readScreenChromeDrag(dataTransfer)).toBeNull();
  });
});

describe('chrome factories', () => {
  it('do not look like data widgets', () => {
    expect(isScreenWidgetItem(createScreenTextItem([]))).toBe(false);
    expect(isScreenWidgetItem(createScreenClockItem([]))).toBe(false);
  });

  it('gives new clocks a default text style', () => {
    expect(createScreenClockItem([]).textStyle).toEqual({
      fontSize: 20,
      fontWeight: 600,
      color: 'canvas',
    });
  });
});
