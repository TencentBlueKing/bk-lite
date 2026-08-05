export type BindableDataSourceParamType =
  | 'string'
  | 'timeRange'
  | 'dateRange';

const BINDABLE_DATA_SOURCE_PARAM_TYPES = new Set<string>([
  'string',
  'timeRange',
  'dateRange',
]);

export const isBindableDataSourceParamType = (
  type?: string,
): type is BindableDataSourceParamType =>
  Boolean(type && BINDABLE_DATA_SOURCE_PARAM_TYPES.has(type));
