import type { ScreenWidgetChartType } from '@/app/ops-analysis/types/screen';

export interface ScreenWidgetDefinition {
  chartType: ScreenWidgetChartType;
  titleKey: string;
  descriptionKey: string;
  defaultWidth: number;
  defaultHeight: number;
}

export const SCREEN_WIDGET_DEFINITIONS: ScreenWidgetDefinition[] = [
  {
    chartType: 'single',
    titleKey: 'opsAnalysis.screen.widgets.single',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.single',
    defaultWidth: 300,
    defaultHeight: 150,
  },
  {
    chartType: 'gauge',
    titleKey: 'opsAnalysis.screen.widgets.gauge',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.gauge',
    defaultWidth: 340,
    defaultHeight: 240,
  },
  {
    chartType: 'line',
    titleKey: 'opsAnalysis.screen.widgets.line',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.line',
    defaultWidth: 520,
    defaultHeight: 300,
  },
  {
    chartType: 'bar',
    titleKey: 'opsAnalysis.screen.widgets.bar',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.bar',
    defaultWidth: 520,
    defaultHeight: 300,
  },
  {
    chartType: 'pie',
    titleKey: 'opsAnalysis.screen.widgets.pie',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.pie',
    defaultWidth: 360,
    defaultHeight: 300,
  },
  {
    chartType: 'table',
    titleKey: 'dataSource.table',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.table',
    defaultWidth: 560,
    defaultHeight: 360,
  },
  {
    chartType: 'topN',
    titleKey: 'opsAnalysis.screen.widgets.topN',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.topN',
    defaultWidth: 420,
    defaultHeight: 320,
  },
  {
    chartType: 'eventTable',
    titleKey: 'opsAnalysis.screen.widgets.eventTable',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.eventTable',
    defaultWidth: 520,
    defaultHeight: 360,
  },
  {
    chartType: 'room3D',
    titleKey: 'dataSource.room3D',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.room3D',
    defaultWidth: 640,
    defaultHeight: 420,
  },
  {
    chartType: 'networkStatusTopology',
    titleKey: 'opsAnalysis.screen.widgets.networkStatusTopology',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.networkStatusTopology',
    defaultWidth: 620,
    defaultHeight: 420,
  },
];

export const getScreenWidgetDefinition = (chartType: ScreenWidgetChartType) =>
  SCREEN_WIDGET_DEFINITIONS.find((item) => item.chartType === chartType);
