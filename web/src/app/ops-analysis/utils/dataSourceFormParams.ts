import dayjs, { type Dayjs } from 'dayjs';

import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import type { ConditionFilterValue, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { parseConditionGroup } from '@/app/ops-analysis/utils/conditionFilter';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';

export type DataSourceFormParamValue =
  | string
  | number
  | boolean
  | Dayjs
  | Array<string | number>
  | [number, number]
  | DateRangeValue
  | ConditionFilterValue
  | null
  | undefined;

export type DataSourceFormParams = Record<string, DataSourceFormParamValue>;
type SubmittedParamValue = Exclude<DataSourceFormParamValue, Dayjs | undefined>;

/**
 * 已保存的页码 / 每页条数为空时，保留数据源给出的数字默认值。
 * 用户填过的数字仍然覆盖默认值。
 */
export const mergeRestoredParamValue = (
  current: DataSourceFormParamValue,
  param: Pick<ParamItem, 'name' | 'type' | 'value'>,
): DataSourceFormParamValue => {
  const saved = param.value;
  if (saved === undefined) return current;
  if (
    (param.name === 'page' || param.name === 'page_size')
    && (saved === null || saved === '')
    && typeof current === 'number'
  ) {
    return current;
  }
  if (param.type === 'date' && saved) {
    if (typeof saved === 'string' || typeof saved === 'number') {
      return dayjs(saved);
    }
    return current;
  }
  return saved as DataSourceFormParamValue;
};

export const getDataSourceFormParamInitialValue = (
  param: ParamItem,
): DataSourceFormParamValue => {
  const { type = 'string', value } = param;
  if (type === 'conditionFilter') {
    return parseConditionGroup(value);
  }
  if (param.filterType !== 'fixed' && value === null) {
    return null;
  }

  switch (type) {
    case 'boolean':
      return value ?? false;
    case 'number':
      return value === undefined ? null : value;
    case 'timeRange':
      return value ?? 10080;
    case 'dateRange':
      if (value === undefined || value === '' || value === null) {
        return null;
      }
      return value;
    case 'date':
      if (value && (typeof value === 'string' || typeof value === 'number')) {
        return dayjs(value);
      }
      return null;
    default:
      return value ?? '';
  }
};

export const processDataSourceFormParamsForSubmit = (
  formParams: DataSourceFormParams,
  sourceParams: ParamItem[],
): ParamItem[] => {
  const processedParams: Record<string, SubmittedParamValue> = {};

  sourceParams.forEach((param) => {
    const hasFormValue = Object.prototype.hasOwnProperty.call(
      formParams,
      param.name,
    );
    const value = formParams[param.name];
    if (
      param.hidden
      && (value === undefined || value === null || value === '')
      && param.value !== undefined
      && param.value !== null
      && param.value !== ''
    ) {
      processedParams[param.name] = param.value as SubmittedParamValue;
      return;
    }
    if (
      hasFormValue
      && param.filterType !== 'fixed'
      && (value === null || value === undefined || value === '')
    ) {
      processedParams[param.name] = null;
      return;
    }
    if (value === null) {
      processedParams[param.name] = null;
      return;
    }
    if (param.type === 'date' && value) {
      if (dayjs.isDayjs(value)) {
        processedParams[param.name] = formatOpsRequestTime(value);
      } else if (typeof value === 'string' || typeof value === 'number') {
        processedParams[param.name] = formatOpsRequestTime(value);
      }
      return;
    }
    if (param.type === 'dateRange' && value !== undefined) {
      processedParams[param.name] = value as DateRangeValue | null;
      return;
    }
    if (
      param.type === 'conditionFilter'
      && value
      && typeof value === 'object'
      && !Array.isArray(value)
    ) {
      processedParams[param.name] = value as ConditionFilterValue;
      return;
    }
    if (
      value !== undefined
      && value !== null
      && (typeof value === 'string'
        || typeof value === 'number'
        || typeof value === 'boolean'
        || Array.isArray(value))
    ) {
      processedParams[param.name] = value;
    }
  });

  return sourceParams.map((param) => ({
    ...param,
    value: Object.prototype.hasOwnProperty.call(processedParams, param.name)
      ? processedParams[param.name]
      : param.value,
  }));
};
