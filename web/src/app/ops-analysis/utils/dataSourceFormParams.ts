import dayjs, { type Dayjs } from 'dayjs';

import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';

export type DataSourceFormParamValue =
  | string
  | number
  | boolean
  | Dayjs
  | [number, number]
  | DateRangeValue
  | null;

export type DataSourceFormParams = Record<string, DataSourceFormParamValue>;
type SubmittedParamValue = Exclude<DataSourceFormParamValue, Dayjs>;

export const processDataSourceFormParamsForSubmit = (
  formParams: DataSourceFormParams,
  sourceParams: ParamItem[],
): ParamItem[] => {
  const processedParams: Record<string, SubmittedParamValue> = {};

  sourceParams.forEach((param) => {
    const value = formParams[param.name];
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
