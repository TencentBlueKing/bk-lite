import dayjs, { type Dayjs } from 'dayjs';

import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import { DEFAULT_DATE_RANGE_VALUE } from '@/app/ops-analysis/types/dateRange';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';

export type DataSourceFormParamValue =
  | string
  | number
  | boolean
  | Dayjs
  | [number, number]
  | DateRangeValue
  | null
  | undefined;

export type DataSourceFormParams = Record<string, DataSourceFormParamValue>;
type SubmittedParamValue = Exclude<DataSourceFormParamValue, Dayjs | undefined>;

export const getDataSourceFormParamInitialValue = (
  param: ParamItem,
): DataSourceFormParamValue => {
  const { type = 'string', value } = param;
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
      return value === undefined ? { ...DEFAULT_DATE_RANGE_VALUE } : value;
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
