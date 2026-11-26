import { describe, expect, it } from 'vitest';

import { buildFiltersFromDashboardLayout } from '@/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync';
import { buildFiltersFromScreenItems } from '@/app/ops-analysis/(pages)/view/screen/utils/layoutUtils';
import { buildFiltersFromNodes } from '@/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils';
import type {
  DashboardLayoutItem,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import { buildFiltersFromReportSections } from '@/app/ops-analysis/utils/reportBuilder';

const timeParam: ParamItem = {
  name: 'time',
  alias_name: '时间范围',
  type: 'timeRange',
  filterType: 'filter',
  value: 360,
};

const savedDefault: UnifiedFilterDefinition = {
  id: 'time__timeRange',
  key: 'time',
  name: '时间范围',
  type: 'timeRange',
  defaultValue: {
    selectValue: 360,
    start: '2020-01-01T00:00:00.000Z',
    end: '2020-01-01T06:00:00.000Z',
  },
  order: 0,
  enabled: true,
};

const dashboardLayout = (): DashboardLayoutItem[] => [{
  i: 'widget-0',
  x: 0,
  y: 0,
  w: 4,
  h: 4,
  name: '组件',
  valueConfig: {
    chartType: 'single',
    dataSourceParams: [timeParam],
  },
}];

const screenView = (): ScreenViewSets => ({
  viewport: { width: 1920, height: 1080, adapter: 'fill' },
  decorations: {},
  items: [{
    id: 'screen-0',
    type: 'widget',
    chartType: 'single',
    title: '组件',
    x: 0,
    y: 0,
    w: 200,
    h: 120,
    zIndex: 1,
    valueConfig: {
      chartType: 'single',
      dataSourceParams: [timeParam],
    },
  }],
});

describe('第一次从数据源分钟数生成时间筛选', () => {
  it('仪表盘、大屏、拓扑、报表都只留下分钟数', () => {
    const dashboard = buildFiltersFromDashboardLayout({
      layout: dashboardLayout(),
      previousDefinitions: [],
      dataSources: [],
    });
    const screen = buildFiltersFromScreenItems({
      viewSets: screenView(),
      previousDefinitions: [],
      dataSources: [],
    });
    const topology = buildFiltersFromNodes(
      {
        getNodes: () => [{
          getData: () => ({
            type: 'single-value',
            valueConfig: { dataSourceParams: [timeParam] },
          }),
        }],
      } as never,
      [],
      [],
    );
    const report = buildFiltersFromReportSections(
      [{
        id: 'section-0',
        valueConfig: { name: '组件', dataSourceParams: [timeParam] },
      }],
      [],
      [],
    );

    for (const filters of [dashboard, screen, topology, report]) {
      expect(filters).toHaveLength(1);
      expect(filters[0]?.defaultValue).toEqual({ selectValue: 360 });
    }
  });

  it('已经保存过的默认值保持原样', () => {
    const filters = buildFiltersFromDashboardLayout({
      layout: dashboardLayout(),
      previousDefinitions: [savedDefault],
      dataSources: [],
    });
    expect(filters[0]?.defaultValue).toEqual(savedDefault.defaultValue);
  });
});
