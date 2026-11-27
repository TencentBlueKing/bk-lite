import dayjs from 'dayjs';
import type { ValueConfig, FilterBindings, UnifiedFilterDefinition, FilterValue } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { ColumnResult } from '@/app/ops-analysis/utils/dataVariable';
import { buildWidgetRequestParams } from '@/app/ops-analysis/utils/widgetDataTransform';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import {
  chartFieldMissingMessage,
  missingConfiguredField,
} from '@/app/ops-analysis/utils/chartFieldContract';
import { readScalarCalc } from '@/app/ops-analysis/utils/scalarReduction';
import { coerceTopNNumericValue, unwrapTopNData } from '@/app/ops-analysis/utils/topNData';
import type { DateRangeResolutionContext } from '@/app/ops-analysis/utils/dateRange';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';
import type { SourceDataResult } from '@/app/ops-analysis/utils/sourceDataResponse';

type RequestParams = Record<string, any>;

/** fetchCompareData 只需要 dataSource 中的 params 字段 */
type MinimalDataSource = Pick<DatasourceItem, 'params'> | { params: ParamItem[] };

export interface CompareQueryResult<T = unknown> {
  currentData: T | null;
  baselineData: T | null;
  warnings?: string[];
}

interface BuildRequestParamsInput {
  config?: ValueConfig;
  dataSource?: MinimalDataSource;
  extraParams?: Record<string, any>;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
  resolutionContext?: DateRangeResolutionContext;
  chartType?: string;
  dataVariableColumns?: Record<string, ColumnResult>;
  t?: (id: string, defaultMessage?: string) => string;
}

interface FetchCompareDataInput extends BuildRequestParamsInput {
  dataSourceId: number;
  getSourceDataByApiId: (id: number, params?: any) => Promise<SourceDataResult>;
}

const mergeWarnings = (...groups: Array<string[] | undefined>): string[] | undefined => {
  const merged = Array.from(new Set(groups.flatMap((group) => group ?? [])));
  return merged.length > 0 ? merged : undefined;
};

const referenceNowMs = (context?: DateRangeResolutionContext): number => {
  const parsed = dayjs(context?.referenceNow ?? Date.now());
  return parsed.isValid() ? parsed.valueOf() : Date.now();
};

const relativeMinutes = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return value;
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const selectValue = (value as { selectValue?: unknown }).selectValue;
  if (typeof selectValue === 'number' && Number.isFinite(selectValue) && selectValue > 0) {
    return selectValue;
  }
  return null;
};

const absoluteTimeEndpoints = (value: unknown): [string, string] | null => {
  if (relativeMinutes(value) !== null) {
    return null;
  }
  const pair = Array.isArray(value) && value.length === 2
    ? value
    : value && typeof value === 'object'
      ? [(value as { start?: unknown }).start, (value as { end?: unknown }).end]
      : null;
  if (!pair || pair[0] == null || pair[1] == null || pair[0] === '' || pair[1] === '') {
    return null;
  }
  const startAt = dayjs(formatOpsRequestTime(pair[0]));
  const endAt = dayjs(formatOpsRequestTime(pair[1]));
  if (!startAt.isValid() || !endAt.isValid() || endAt.valueOf() <= startAt.valueOf()) {
    return null;
  }
  return [startAt.toISOString(), endAt.toISOString()];
};

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

const deriveBaselineDateRange = (dateRange: [string, string]): [string, string] | null => {
  const [start, end] = dateRange;
  const startAt = dayjs(start, 'YYYY-MM-DD', true);
  const endAt = dayjs(end, 'YYYY-MM-DD', true);
  if (!startAt.isValid() || !endAt.isValid() || endAt.isBefore(startAt, 'day')) {
    return null;
  }

  const duration = endAt.diff(startAt, 'day') + 1;
  return [
    startAt.subtract(duration, 'day').format('YYYY-MM-DD'),
    startAt.subtract(1, 'day').format('YYYY-MM-DD'),
  ];
};

const isDateRangeTuple = (value: unknown): value is [string, string] =>
  Array.isArray(value)
  && value.length === 2
  && value.every((item) => typeof item === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item));

const getComparableRangeParam = (params?: ValueConfig['dataSourceParams']): { name: string; type: 'timeRange' | 'dateRange' } | null => {
  const rangeParams = (Array.isArray(params) ? params : []).filter(
    (param) => param.type === 'timeRange' || param.type === 'dateRange',
  );
  if (rangeParams.length !== 1) {
    return null;
  }
  return {
    name: rangeParams[0].name,
    type: rangeParams[0].type as 'timeRange' | 'dateRange',
  };
};

export const canEnableCompare = ({
  config,
  dataSource,
}: Pick<BuildRequestParamsInput, 'config' | 'dataSource'>): boolean => {
  const sourceParams = Array.isArray(config?.dataSourceParams) && config.dataSourceParams.length > 0
    ? config.dataSourceParams
    : dataSource?.params;
  return getComparableRangeParam(sourceParams) !== null;
};

export const buildCompareRequestParams = ({
  config,
  dataSource,
  extraParams,
  unifiedFilterValues,
  filterBindings,
  filterDefinitions,
  resolutionContext,
  chartType,
  dataVariableColumns,
  t,
}: BuildRequestParamsInput): {
  currentParams: RequestParams | null;
  baselineParams: RequestParams | null;
} => {
  const currentParams = buildWidgetRequestParams({
    config,
    dataSource,
    extraParams,
    unifiedFilterValues,
    filterBindings,
    filterDefinitions,
    resolutionContext,
    chartType: chartType || config?.chartType,
    dataVariableColumns,
    t,
  });

  if (!currentParams || !config?.compare) {
    return { currentParams, baselineParams: null };
  }

  const sourceParams = Array.isArray(config?.dataSourceParams) && config.dataSourceParams.length > 0
    ? config.dataSourceParams
    : dataSource?.params;
  const comparableRangeParam = getComparableRangeParam(sourceParams);
  if (!comparableRangeParam) {
    return { currentParams, baselineParams: null };
  }

  const rawRange = currentParams[comparableRangeParam.name];
  if (comparableRangeParam.type === 'timeRange') {
    const minutes = relativeMinutes(rawRange);
    const nowMs = referenceNowMs(resolutionContext);
    const currentWindow = minutes === null
      ? absoluteTimeEndpoints(rawRange)
      : absoluteTimeEndpoints([nowMs - minutes * 60_000, nowMs]);
    const baselineWindow = currentWindow ? deriveBaselineTimeRange(currentWindow) : null;
    if (!currentWindow || !baselineWindow) {
      return { currentParams, baselineParams: null };
    }
    return {
      currentParams: { ...currentParams, [comparableRangeParam.name]: currentWindow },
      baselineParams: { ...currentParams, [comparableRangeParam.name]: baselineWindow },
    };
  }

  const baselineRange = isDateRangeTuple(rawRange) ? deriveBaselineDateRange(rawRange) : null;
  if (!baselineRange) {
    return { currentParams, baselineParams: null };
  }

  return {
    currentParams,
    baselineParams: {
      ...currentParams,
      [comparableRangeParam.name]: baselineRange,
    },
  };
};

export const fetchCompareData = async ({
  dataSourceId,
  getSourceDataByApiId,
  ...rest
}: FetchCompareDataInput): Promise<CompareQueryResult> => {
  const { currentParams, baselineParams } = buildCompareRequestParams(rest);
  if (!currentParams) {
    return { currentData: null, baselineData: null };
  }
  const currentResult = await getSourceDataByApiId(dataSourceId, currentParams);

  if (!baselineParams) {
    return {
      currentData: currentResult.data,
      baselineData: null,
      warnings: mergeWarnings(currentResult.warnings),
    };
  }

  const baselineResult = await getSourceDataByApiId(dataSourceId, baselineParams);
  return {
    currentData: currentResult.data,
    baselineData: baselineResult.data,
    warnings: mergeWarnings(currentResult.warnings, baselineResult.warnings),
  };
};

const presentScalar = (value: unknown): number | string | boolean | null | undefined => {
  if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') {
    return value;
  }
  if (value === null) {
    return null;
  }
  return undefined;
};

export const extractComparableValue = (
  data: unknown,
  selectedField?: string,
): number | string | boolean | null => {
  if (data === null || data === undefined) {
    return null;
  }

  if (selectedField) {
    const extracted = getValueByPath(data, selectedField);
    const present = presentScalar(extracted);
    if (present !== undefined) {
      return present;
    }
    const rows = unwrapTopNData(data);
    if (rows !== data) {
      const fromRow = presentScalar(getValueByPath(rows, selectedField));
      if (fromRow !== undefined) {
        return fromRow;
      }
    }
    // 明确指定了字段但当前结果没有可用值时返回 null，不改读其它字段。
    return null;
  }

  if (typeof data === 'number' || typeof data === 'string' || typeof data === 'boolean') {
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

export const toComparableNumber = (value: number | string | boolean | null): number | null =>
  coerceTopNNumericValue(value);

export const validateSingleOrGaugeData = (
  data: unknown,
  chartType: string | undefined,
  config?: ValueConfig,
): { isValid: boolean; message?: string } => {
  if (readScalarCalc(config?.scalarCalc)) {
    return { isValid: true };
  }

  const missing = missingConfiguredField(data, [config?.selectedFields?.[0]]);
  if (missing) {
    return { isValid: false, message: chartFieldMissingMessage(missing) };
  }
  if (chartType === 'gauge') {
    return validateGaugeData(data, config);
  }
  return { isValid: true };
};

export const validateGaugeData = (
  data: unknown,
  config?: ValueConfig,
): { isValid: boolean; message?: string } => {
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return { isValid: true };
  }

  if (config?.selectedFields?.[0]) {
    return { isValid: true };
  }

  const failMessage = 'dashboard.gaugeStructureMismatch';

  const hasNumericValue = (value: unknown) => {
    if (typeof value === 'number') return Number.isFinite(value);
    if (typeof value === 'string') {
      const parsed = Number(value);
      return Number.isFinite(parsed);
    }
    return false;
  };

  if (Array.isArray(data)) {
    const firstItem = data[0];

    if (hasNumericValue(firstItem)) {
      return { isValid: true };
    }

    if (firstItem && typeof firstItem === 'object') {
      const values = Object.values(firstItem as Record<string, unknown>);
      return values.some((item) => hasNumericValue(item))
        ? { isValid: true }
        : { isValid: false, message: failMessage };
    }

    return { isValid: false, message: failMessage };
  }

  if (typeof data === 'object') {
    const values = Object.values(data as Record<string, unknown>);
    return values.some((item) => hasNumericValue(item))
      ? { isValid: true }
      : { isValid: false, message: failMessage };
  }

  return hasNumericValue(data)
    ? { isValid: true }
    : { isValid: false, message: failMessage };
};

export const formatPeriodCompare = ({
  current,
  baseline,
  compareMode,
  decimalPlaces,
  unitLabel,
}: {
  current: number | null;
  baseline: number | null;
  compareMode?: 'percent' | 'value';
  decimalPlaces?: number;
  unitLabel?: string;
}): { text: string; tone: 'up' | 'down' | 'flat' } => {
  const changeValue = current !== null && baseline !== null ? current - baseline : null;
  const changePercent = getChangePercent(current, baseline);
  const amount = compareMode === 'value' ? changeValue : changePercent;
  if (amount === null) {
    return { text: '--', tone: 'flat' };
  }
  const arrow = amount > 0 ? '↑' : amount < 0 ? '↓' : '';
  const digits = compareMode === 'value' ? (decimalPlaces ?? 0) : 1;
  const suffix = compareMode === 'value' ? (unitLabel || '') : '%';
  return {
    text: `${arrow}${Math.abs(amount).toFixed(digits)}${suffix}`,
    tone: amount > 0 ? 'up' : amount < 0 ? 'down' : 'flat',
  };
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
