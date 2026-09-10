import type { ParamItem } from '@/app/ops-analysis/types/dataSource';

export type BindableDataSourceParamType =
  | 'string'
  | 'timeRange'
  | 'dateRange'
  | 'number';

const BINDABLE_DATA_SOURCE_PARAM_TYPES = new Set<string>([
  'string',
  'timeRange',
  'dateRange',
  'number',
]);

export const isBindableDataSourceParamType = (
  type?: string,
): type is BindableDataSourceParamType =>
  Boolean(type && BINDABLE_DATA_SOURCE_PARAM_TYPES.has(type));

export const ensurePrometheusQueryRequired = (
  params: ParamItem[],
): ParamItem[] =>
  params.map((param) =>
    param.name === 'query' && param.required !== true
      ? { ...param, required: true }
      : param,
  );
