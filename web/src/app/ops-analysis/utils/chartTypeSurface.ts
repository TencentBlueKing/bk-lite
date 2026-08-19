export type OpsAnalysisWidgetSurface = 'dashboard' | 'screen' | 'report';

const SCREEN_ONLY_CHART_TYPES = new Set(['room3D']);
export const REPORT_CHART_TYPES: ReadonlySet<string> = new Set(['table', 'eventTable']);

export const isChartTypeSupportedOnSurface = (
  chartType: string,
  surface: OpsAnalysisWidgetSurface = 'dashboard',
) => {
  if (surface === 'report') {
    return REPORT_CHART_TYPES.has(chartType);
  }

  if (SCREEN_ONLY_CHART_TYPES.has(chartType)) {
    return surface === 'screen';
  }

  return true;
};

export const filterChartTypesForSurface = (
  chartTypes: string[] = [],
  surface: OpsAnalysisWidgetSurface = 'dashboard',
) => chartTypes.filter((type) => isChartTypeSupportedOnSurface(type, surface));

export const hasSupportedChartTypeForSurface = (
  chartTypes: string[] = [],
  surface: OpsAnalysisWidgetSurface = 'dashboard',
) => filterChartTypesForSurface(chartTypes, surface).length > 0;
