import { describe, expect, it } from 'vitest';
import type {
  DashboardLayoutItem,
  UnifiedFilterDefinition,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import type { ReportViewSets } from '@/app/ops-analysis/types/report';
import {
  cloneAnalysisWidget,
  copyDashboardWidget,
  copyReportSection,
  copyScreenWidget,
  resolveAnalysisCanvasInteraction,
  shouldShowAnalysisWidgetCopyAction,
} from '../widgetCopy';

const filterDefinitions: UnifiedFilterDefinition[] = [
  {
    id: 'env__string',
    key: 'env',
    name: '环境',
    type: 'string',
    order: 0,
    enabled: true,
  },
];

const sourceValueConfig: ValueConfig = {
  chartType: 'line',
  dataSource: 42,
  dataSourceParams: [{ name: 'env', value: 'prod' }],
  filterBindings: { env__string: true },
  tableConfig: { columns: [{ key: 'host', title: '主机', visible: true, order: 0 }] },
  appearance: { frame: 'panel' },
};

describe('cloneAnalysisWidget', () => {
  it('assigns a new id and deep-copies valueConfig without cloning canvas filters', () => {
    const source = {
      id: 'widget-source',
      title: 'CPU 使用率',
      valueConfig: sourceValueConfig,
    };
    const cloned = cloneAnalysisWidget(source, { createId: () => 'widget-copy' });

    expect(cloned.id).toBe('widget-copy');
    expect(cloned.id).not.toBe(source.id);
    expect(cloned.valueConfig.dataSource).toBe(42);
    expect(cloned.valueConfig.filterBindings).toEqual({ env__string: true });
    expect(cloned.valueConfig.filterBindings).not.toBe(source.valueConfig.filterBindings);
    expect(cloned.valueConfig.dataSourceParams).not.toBe(source.valueConfig.dataSourceParams);
    expect(cloned.valueConfig.tableConfig).not.toBe(source.valueConfig.tableConfig);
    expect(cloned.valueConfig.appearance).not.toBe(source.valueConfig.appearance);

    cloned.valueConfig.filterBindings!.env__string = false;
    cloned.valueConfig.dataSourceParams![0].value = 'dev';
    cloned.valueConfig.tableConfig!.columns![0].title = '被改';
    cloned.valueConfig.appearance!.frame = 'bare';

    expect(source.valueConfig.filterBindings).toEqual({ env__string: true });
    expect(source.valueConfig.dataSourceParams?.[0].value).toBe('prod');
    expect(source.valueConfig.tableConfig?.columns?.[0].title).toBe('主机');
    expect(source.valueConfig.appearance?.frame).toBe('panel');
    expect(filterDefinitions).toHaveLength(1);
    expect(filterDefinitions[0].id).toBe('env__string');
  });

  it('suffixes a named title with 副本 and uses 副本 when the title is empty', () => {
    expect(
      cloneAnalysisWidget(
        { id: 'named', title: 'CPU 使用率', valueConfig: { chartType: 'line' } },
        { createId: () => 'named-copy' },
      ).title,
    ).toBe('CPU 使用率 副本');
    expect(
      cloneAnalysisWidget(
        { id: 'empty', title: '', valueConfig: { chartType: 'line' } },
        { createId: () => 'empty-copy' },
      ).title,
    ).toBe('副本');
    expect(
      cloneAnalysisWidget(
        { id: 'blank', title: '   ', valueConfig: { name: '' } },
        { createId: () => 'blank-copy' },
      ).title,
    ).toBe('副本');
  });
});

describe('shouldShowAnalysisWidgetCopyAction', () => {
  it('shows copy for data widgets in edit mode including room3D and topologyMap', () => {
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        chartType: 'line',
      }),
    ).toBe(true);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        chartType: 'room3D',
      }),
    ).toBe(true);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        chartType: 'topologyMap',
      }),
    ).toBe(true);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        chartType: 'cardList',
      }),
    ).toBe(true);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        chartType: 'eventTimeline',
      }),
    ).toBe(true);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        chartType: 'radar',
      }),
    ).toBe(true);
  });

  it('omits copy entirely for scene widgets rather than disabling it', () => {
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        sceneWidgetType: 'networkStatusTopology',
        chartType: 'networkStatusTopology',
      }),
    ).toBe(false);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        chartType: 'networkStatusTopology',
      }),
    ).toBe(false);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'edit',
        sceneWidgetType: 'application3D',
      }),
    ).toBe(false);
  });

  it('omits copy in view, share, and builtin modes', () => {
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'view',
        chartType: 'line',
      }),
    ).toBe(false);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'share',
        chartType: 'line',
      }),
    ).toBe(false);
    expect(
      shouldShowAnalysisWidgetCopyAction({
        interaction: 'builtin',
        chartType: 'line',
      }),
    ).toBe(false);
  });
});

describe('resolveAnalysisCanvasInteraction', () => {
  it('maps parent flags to share and builtin instead of collapsing them into view', () => {
    expect(
      resolveAnalysisCanvasInteraction({ editMode: true, shareMode: true }),
    ).toBe('share');
    expect(
      resolveAnalysisCanvasInteraction({ editMode: true, isBuiltIn: true }),
    ).toBe('builtin');
    expect(resolveAnalysisCanvasInteraction({ editMode: true })).toBe('edit');
    expect(resolveAnalysisCanvasInteraction({})).toBe('view');
  });
});

describe('copyDashboardWidget', () => {
  const groupedLayout: DashboardLayoutItem[] = [
    { i: 'group-a', itemType: 'group', x: 0, y: 0, w: 12, h: 1, name: '主机' },
    {
      i: 'cpu',
      x: 0,
      y: 1,
      w: 4,
      h: 3,
      name: 'CPU',
      groupId: 'group-a',
      valueConfig: { chartType: 'line', dataSource: 7 },
    },
    {
      i: 'mem',
      x: 4,
      y: 1,
      w: 4,
      h: 3,
      name: '内存',
      groupId: 'group-a',
      valueConfig: { chartType: 'gauge', dataSource: 8 },
    },
  ];

  it('keeps the source groupId instead of dumping the copy to ungrouped bottom', () => {
    const next = copyDashboardWidget(groupedLayout, 'cpu', {
      createId: () => 'cpu-copy',
    });
    const copied = next.find((item) => item.i === 'cpu-copy');
    expect(copied).toMatchObject({
      i: 'cpu-copy',
      name: 'CPU 副本',
      groupId: 'group-a',
      w: 4,
      h: 3,
    });
    expect(next.some((item) => item.i === 'cpu' && 'groupId' in item && item.groupId === 'group-a')).toBe(true);
    expect(copied && 'y' in copied && copied.y).not.toBeGreaterThanOrEqual(10);
  });

  it('places at x+1 same y when that cell is free in the group', () => {
    const layout: DashboardLayoutItem[] = [
      { i: 'group-a', itemType: 'group', x: 0, y: 0, w: 12, h: 1, name: '主机' },
      {
        i: 'narrow',
        x: 0,
        y: 1,
        w: 1,
        h: 3,
        name: '窄组件',
        groupId: 'group-a',
        valueConfig: { chartType: 'single', dataSource: 3 },
      },
    ];
    const next = copyDashboardWidget(layout, 'narrow', {
      createId: () => 'narrow-copy',
    });
    expect(next.find((item) => item.i === 'narrow-copy')).toMatchObject({
      x: 1,
      y: 1,
      groupId: 'group-a',
    });
  });

  it('falls back to in-group collision scan when x+1 still overlaps', () => {
    const next = copyDashboardWidget(groupedLayout, 'cpu', {
      createId: () => 'cpu-copy',
    });
    expect(next.find((item) => item.i === 'cpu-copy')).toMatchObject({
      x: 8,
      y: 1,
      groupId: 'group-a',
    });
  });
});

describe('copyScreenWidget', () => {
  const viewSets: ScreenViewSets = {
    viewport: { width: 1920, height: 1080 },
    decorations: {},
    filters: [
      {
        id: 'env__string',
        key: 'env',
        name: '环境',
        type: 'string',
        order: 0,
        enabled: true,
      },
    ],
    items: [
      {
        id: 'line-1',
        type: 'widget',
        chartType: 'line',
        title: 'CPU',
        x: 100,
        y: 80,
        w: 400,
        h: 240,
        zIndex: 2,
        valueConfig: {
          chartType: 'line',
          dataSource: 42,
          filterBindings: { env__string: true },
        },
      },
      {
        id: 'gauge-1',
        type: 'widget',
        chartType: 'gauge',
        title: '内存',
        x: 600,
        y: 80,
        w: 400,
        h: 240,
        zIndex: 5,
        valueConfig: { chartType: 'gauge', dataSource: 8 },
      },
    ],
  };

  it('selects the new widget and offsets it by 48px with zIndex max+1', () => {
    const result = copyScreenWidget(viewSets, 'line-1', {
      createId: () => 'line-copy',
    });
    expect(result).not.toBeNull();
    expect(result?.selectedItemId).toBe('line-copy');
    const copied = result?.viewSets.items.find((item) => item.id === 'line-copy');
    expect(copied).toMatchObject({
      id: 'line-copy',
      title: 'CPU 副本',
      x: 148,
      y: 128,
      zIndex: 6,
      w: 400,
      h: 240,
    });
    expect(copied?.valueConfig.dataSource).toBe(42);
    expect(copied?.valueConfig.filterBindings).toEqual({ env__string: true });
    expect(result?.viewSets.filters).toHaveLength(1);
    expect(result?.viewSets.items).toHaveLength(3);
  });

  it('clamps the copy into the viewport when +48 would overflow', () => {
    const nearEdge: ScreenViewSets = {
      ...viewSets,
      items: [
        {
          id: 'edge',
          type: 'widget',
          chartType: 'cardList',
          title: '列表',
          x: 1880,
          y: 1000,
          w: 80,
          h: 80,
          zIndex: 1,
          valueConfig: { chartType: 'cardList' },
        },
      ],
    };
    const result = copyScreenWidget(nearEdge, 'edge', {
      createId: () => 'edge-copy',
    });
    expect(result?.viewSets.items.find((item) => item.id === 'edge-copy')).toMatchObject({
      x: 1840,
      y: 1000,
      zIndex: 2,
    });
  });
});

describe('copyReportSection', () => {
  const viewSets: ReportViewSets = {
    schema_version: 1,
    filters: [
      {
        id: 'env__string',
        key: 'env',
        name: '环境',
        type: 'string',
        order: 0,
        enabled: true,
      },
    ],
    sections: [
      { id: 'sec-a', valueConfig: { name: 'A 表', chartType: 'table', dataSource: 1 } },
      { id: 'sec-b', valueConfig: { name: 'B 表', chartType: 'table', dataSource: 2, filterBindings: { env__string: true } } },
      { id: 'sec-c', valueConfig: { name: 'C 表', chartType: 'eventTable', dataSource: 3 } },
    ],
  };

  it('inserts the copy immediately below the source with a unique section id', () => {
    const next = copyReportSection(viewSets, 'sec-b', {
      createId: () => 'sec-b-copy',
    });
    expect(next.sections.map((section) => section.id)).toEqual([
      'sec-a',
      'sec-b',
      'sec-b-copy',
      'sec-c',
    ]);
    expect(new Set(next.sections.map((section) => section.id)).size).toBe(4);
    expect(next.sections[2]).toMatchObject({
      id: 'sec-b-copy',
      valueConfig: {
        name: 'B 表 副本',
        chartType: 'table',
        dataSource: 2,
        filterBindings: { env__string: true },
      },
    });
    expect(next.sections[2].valueConfig.filterBindings).not.toBe(
      viewSets.sections[1].valueConfig.filterBindings,
    );
    expect(next.filters).toHaveLength(1);
  });
});
