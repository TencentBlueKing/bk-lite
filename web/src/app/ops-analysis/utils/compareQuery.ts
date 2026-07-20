import dayjs from 'dayjs';
import type { ValueConfig, FilterBindings, UnifiedFilterDefinition, FilterValue } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { buildWidgetRequestParams } from '@/app/ops-analysis/utils/widgetDataTransform';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import type { DateRangeResolutionContext } from '@/app/ops-analysis/utils/dateRange';

type RequestParams = Record<string, any>;

/** fetchCompareData 只需要 dataSource 中的 params 字段 */
type MinimalDataSource = Pick<DatasourceItem, 'params'> | { params: ParamItem[] };

export interface CompareQueryResult<T = unknown> {
  currentData: T | null;
  baselineData: T | null;
}

interface BuildRequestParamsInput {
  config?: ValueConfig;
  dataSource?: MinimalDataSource;
  extraParams?: Record<string, any>;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
  resolutionContext?: DateRangeResolutionContext;
}

interface FetchCompareDataInput extends BuildRequestParamsInput {
  dataSourceId: number;
  getSourceDataByApiId: (id: number, params?: any) => Promise<any>;
}

const isTimeRangeTuple = (value: unknown): value is [string, string] =>
  Array.isArray(value) && value.length === 2 && value.every((item) => typeof item === 'string' && item.trim().length > 0);

const deriveBaselineTimeRange = (timeRange: [string, string]): [string, string] | null => {
  const [start, end] = timeRange;
  const startAt = dayjs(start);
  const endAt = dayjs(end);
  if (!startAt.isValid() || !endAt.isValid()) {
    return null;
  }

  const duration = endAt.valueOf() - startAt.valueOf();
  if (duration <= 0) {
    return null;
  }

  return [
    dayjs(startAt.valueOf() - duration).toISOString(),
    startAt.toISOString(),
  ];
};

const getTimeRangeParamName = (params?: ValueConfig['dataSourceParams']): string | null => {
  const timeRangeParams = (Array.isArray(params) ? params : []).filter((param) => param.type === 'timeRange');
  if (timeRangeParams.length !== 1) {
    return null;
  }
  return timeRangeParams[0].name;
};

export const canEnableCompare = ({
  config,
  dataSource,
}: Pick<BuildRequestParamsInput, 'config' | 'dataSource'>): boolean => {
  const sourceParams = Array.isArray(config?.dataSourceParams) && config.dataSourceParams.length > 0
    ? config.dataSourceParams
    : dataSource?.params;
  return getTimeRangeParamName(sourceParams) !== null;
};

export const buildCompareRequestParams = ({
  config,
  dataSource,
  extraParams,
  unifiedFilterValues,
  filterBindings,
  filterDefinitions,
  resolutionContext,
}: BuildRequestParamsInput): { currentParams: RequestParams; baselineParams: RequestParams | null } => {
  const currentParams = buildWidgetRequestParams({
    config,
    dataSource,
    extraParams,
    unifiedFilterValues,
    filterBindings,
    filterDefinitions,
    resolutionContext,
  });

  if (!config?.compare) {
    return { currentParams, baselineParams: null };
  }

  const sourceParams = Array.isArray(config?.dataSourceParams) && config.dataSourceParams.length > 0
    ? config.dataSourceParams
    : dataSource?.params;
  const timeRangeParamName = getTimeRangeParamName(sourceParams);
  if (!timeRangeParamName) {
    return { currentParams, baselineParams: null };
  }

  const rawTimeRange = currentParams[timeRangeParamName];
  if (!isTimeRangeTuple(rawTimeRange)) {
    return { currentParams, baselineParams: null };
  }

  const baselineTimeRange = deriveBaselineTimeRange(rawTimeRange);
  if (!baselineTimeRange) {
    return { currentParams, baselineParams: null };
  }

  return {
    currentParams,
    baselineParams: {
      ...currentParams,
      [timeRangeParamName]: baselineTimeRange,
    },
  };
};

export const fetchCompareData = async ({
  dataSourceId,
  getSourceDataByApiId,
  ...rest
}: FetchCompareDataInput): Promise<CompareQueryResult> => {
  const { currentParams, baselineParams } = buildCompareRequestParams(rest);
  const currentData = await getSourceDataByApiId(dataSourceId, currentParams);

  if (!baselineParams) {
    return {
      currentData,
      baselineData: null,
    };
  }

  const baselineData = await getSourceDataByApiId(dataSourceId, baselineParams);
  return {
    currentData,
    baselineData,
  };
};

export const extractComparableValue = (
  data: unknown,
  selectedField?: string,
): number | string | null => {
  if (data === null || data === undefined) {
    return null;
  }

  if (selectedField) {
    const extracted = getValueByPath(data, selectedField);
    if (typeof extracted === 'number' || typeof extracted === 'string') {
      return extracted;
    }
    // 明确指定了字段但其值非数字/字符串（如 null）→ 返回 null，
    // 不回退到对象里的其它字段（否则会错误地显示别的字段值，且 null 值映射失效）
    return null;
  }

  if (typeof data === 'number' || typeof data === 'string') {
    return data;
  }

  if (Array.isArray(data) && data.length > 0) {
    const firstItem = data[0];
    if (firstItem && typeof firstItem === 'object') {
      const values = Object.values(firstItem as Record<string, unknown>);
      for (const value of values) {
        if (typeof value === 'number') return value;
      }
      for (const value of values) {
        if (typeof value === 'string' && !Number.isNaN(parseFloat(value))) return value;
      }
    }
  }

  if (typeof data === 'object') {
    const values = Object.values(data as Record<string, unknown>);
    for (const value of values) {
      if (typeof value === 'number') return value;
    }
  }

  return null;
};

export const toComparableNumber = (value: number | string | null): number | null => {
  if (value === null) {
    return null;
  }
  const numericValue = typeof value === 'string' ? parseFloat(value) : value;
  return typeof numericValue === 'number' && !Number.isNaN(numericValue)
    ? numericValue
    : null;
};

export const getChangePercent = (
  currentValue: number | null,
  baselineValue: number | null,
): number | null => {
  if (currentValue === null || baselineValue === null) {
    return null;
  }
  if (baselineValue !== 0) {
    return ((currentValue - baselineValue) / baselineValue) * 100;
  }
  if (currentValue > 0) {
    return 100;
  }
  return null;
};
