import type { InputOption, ParamItem } from '@/app/ops-analysis/types/dataSource';

export const ANALYSIS_MODE_PARAM = 'analysis_mode';

export interface AnalysisModeOption {
  label: string;
  value: string;
  charts: string[];
  result?: InputOption['result'];
}

const staticItemsOf = (param?: ParamItem): InputOption[] => {
  const config = param?.inputConfig;
  if (!config || !('optionsSource' in config)) return [];
  if (config.optionsSource.type !== 'static') return [];
  return config.optionsSource.staticItems;
};

export const findAnalysisModeParam = (
  params?: ParamItem[] | null,
): ParamItem | undefined =>
  (Array.isArray(params) ? params : []).find((param) => param?.name === ANALYSIS_MODE_PARAM);

export const analysisModeOptions = (
  params?: ParamItem[] | null,
): AnalysisModeOption[] =>
  staticItemsOf(findAnalysisModeParam(params))
    .filter((item) => item.value !== undefined && item.value !== null && String(item.value) !== '')
    .map((item) => ({
      label: String(item.label ?? item.value),
      value: String(item.value),
      charts: Array.isArray(item.charts) ? item.charts.map((chart) => String(chart)) : [],
      result: item.result,
    }));

/**
 * 分析方式只看用户选择和数据源配置的默认值。
 * chartType 保留在类型里，避免旧调用把图表传进来后又改回用户的选择。
 */
export const resolveAnalysisModeValue = ({
  params,
  selected,
}: {
  params?: ParamItem[] | null;
  selected?: unknown;
  chartType?: string;
}): string | undefined => {
  const options = analysisModeOptions(params);
  if (!options.length) return undefined;
  const chosen = selected === undefined || selected === null ? '' : String(selected);
  if (chosen && options.some((item) => item.value === chosen)) return chosen;
  const configured = findAnalysisModeParam(params)?.value;
  const fallback = configured === undefined || configured === null ? '' : String(configured);
  if (fallback && options.some((item) => item.value === fallback)) return fallback;
  return options[0]?.value;
};

export const filterChartTypesForAnalysisMode = <ChartType extends { value: string }>(
  chartTypes: ChartType[],
  params: ParamItem[] | null | undefined,
  mode: string | undefined,
): ChartType[] => {
  // 分析方式不再收窄可选图表，切图也不改用户已选的分析方式。
  void mode;
  if (!findAnalysisModeParam(params)) return chartTypes;
  return chartTypes;
};
