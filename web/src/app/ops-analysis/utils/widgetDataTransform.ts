import dayjs from 'dayjs';
import type {
  FilterValue,
  FilterBindings,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { InputOption, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';
import {
  DateRangeResolutionContext,
  getDateRangeTimezone,
  resolveDateRange,
} from '@/app/ops-analysis/utils/dateRange';

export type BindableParamType = 'string' | 'timeRange' | 'dateRange';
export type UnifiedFilterInputMode = 'input' | 'select' | 'radio' | 'organization';

const UNIFIED_FILTER_INPUT_MODES: UnifiedFilterInputMode[] = [
  'input',
  'select',
  'radio',
  'organization',
];
const OPTION_INPUT_MODES: UnifiedFilterInputMode[] = ['select', 'radio'];

export const normalizeUnifiedFilterInputMode = (
  inputMode?: string,
): UnifiedFilterInputMode =>
  UNIFIED_FILTER_INPUT_MODES.includes(inputMode as UnifiedFilterInputMode)
    ? (inputMode as UnifiedFilterInputMode)
    : 'input';

export const isOptionInputMode = (inputMode?: string): boolean =>
  OPTION_INPUT_MODES.includes(normalizeUnifiedFilterInputMode(inputMode));

export const sanitizeUnifiedFilterDefinition = <T extends UnifiedFilterDefinition>(
  definition: T,
): T => {
  if (definition.type === 'timeRange' || definition.type === 'dateRange') {
    const next = { ...definition };
    delete next.inputMode;
    delete next.options;
    delete next.inputConfig;
    return next;
  }

  const inputMode = normalizeUnifiedFilterInputMode(definition.inputMode);
  if (!isOptionInputMode(inputMode)) {
    const next = { ...definition };
    delete next.options;
    if (inputMode === 'organization') {
      delete next.inputConfig;
    }
    return { ...next, inputMode };
  }

  let staticOptions: InputOption[] | undefined;
  if (
    definition.inputConfig?.control === 'select' ||
    definition.inputConfig?.control === 'radio'
  ) {
    if (definition.inputConfig.optionsSource.type === 'static') {
      staticOptions = definition.inputConfig.optionsSource.staticItems;
    }
  } else if (Array.isArray(definition.options)) {
    staticOptions = definition.options;
  }

  const defaultValue = staticOptions
    ? staticOptions.some((item) => item.value === definition.defaultValue)
      ? definition.defaultValue
      : null
    : definition.defaultValue;

  return {
    ...definition,
    inputMode,
    options: Array.isArray(definition.options) ? definition.options : undefined,
    defaultValue,
  };
};

export const getFilterDefinitionId = (
  key: string,
  type: BindableParamType,
): string => `${key}__${type}`;

export const getBindableFilterParams = (
  params?: ParamItem[],
): Array<ParamItem & { type: BindableParamType }> =>
  (Array.isArray(params) ? params : []).filter(
    (param): param is ParamItem & { type: BindableParamType } =>
      param.filterType === 'filter' &&
      (param.type === 'string' || param.type === 'timeRange' || param.type === 'dateRange'),
  );

export const buildDefaultFilterBindings = (
  params: ParamItem[] | undefined,
  definitions: UnifiedFilterDefinition[],
  existingBindings?: FilterBindings,
): FilterBindings | undefined => {
  const bindableParams = getBindableFilterParams(params);
  if (!bindableParams.length || !definitions.length) {
    return existingBindings;
  }

  const autoBindings = definitions.reduce<FilterBindings>((acc, definition) => {
    const matched = bindableParams.some(
      (param) => param.name === definition.key && param.type === definition.type,
    );
    if (matched) {
      acc[definition.id] = true;
    }
    return acc;
  }, {});

  if (!Object.keys(autoBindings).length) {
    return existingBindings;
  }

  const retainedBindings = Object.entries(existingBindings || {}).reduce<FilterBindings>(
    (bindings, [filterId, enabled]) => {
      if (filterId in autoBindings) bindings[filterId] = enabled;
      return bindings;
    },
    {},
  );

  return {
    ...autoBindings,
    ...retainedBindings,
  };
};

export const formatTimeRange = (timeParams: any): string[] => {
  let startTime, endTime;

  if (timeParams && typeof timeParams === 'number') {
    // 数值类型：表示分钟数
    endTime = dayjs().valueOf();
    startTime = dayjs().subtract(timeParams, 'minute').valueOf();
  } else if (timeParams && Array.isArray(timeParams) && timeParams.length === 2) {
    // 数组类型：[startTime, endTime]
    startTime = timeParams[0];
    endTime = timeParams[1];
  } else if (timeParams && timeParams.start && timeParams.end) {
    // 对象类型：{ start, end, selectValue? }
    if (timeParams.selectValue && timeParams.selectValue > 0) {
      // 有快捷选项时，基于当前时间重新计算相对时间
      endTime = dayjs().valueOf();
      startTime = dayjs().subtract(timeParams.selectValue, 'minute').valueOf();
    } else {
      startTime = timeParams.start;
      endTime = timeParams.end;
    }
  } else {
    // 默认时间范围：最近7天
    endTime = dayjs().valueOf();
    startTime = dayjs().subtract(7, 'day').valueOf();
  }

  const startTimeStr = formatOpsRequestTime(startTime);
  const endTimeStr = formatOpsRequestTime(endTime);

  return [startTimeStr, endTimeStr];
};

const formatTimeRangeForSignature = (timeParams: any): unknown => {
  if (timeParams && typeof timeParams === 'number') {
    return { mode: 'relative', value: timeParams };
  }

  if (timeParams && Array.isArray(timeParams) && timeParams.length === 2) {
    return [
      formatOpsRequestTime(timeParams[0]),
      formatOpsRequestTime(timeParams[1]),
    ];
  }

  if (timeParams && timeParams.start && timeParams.end) {
    if (timeParams.selectValue && timeParams.selectValue > 0) {
      return { mode: 'relative', value: timeParams.selectValue };
    }

    return {
      start: formatOpsRequestTime(timeParams.start),
      end: formatOpsRequestTime(timeParams.end),
    };
  }

  return { mode: 'relative', value: 10080 };
};

export const OMIT_DATA_SOURCE_PARAM = Symbol('omit-data-source-param');

const createDateRangeResolutionContext = (): DateRangeResolutionContext => ({
  referenceNow: Date.now(),
  timezone: getDateRangeTimezone(),
});

export const formatDataSourceParamValue = (
  type: string,
  value: unknown,
  resolutionContext: DateRangeResolutionContext,
  timeRangeFormatter: (timeParams: any) => unknown = formatTimeRange,
): unknown | typeof OMIT_DATA_SOURCE_PARAM => {
  if (type === 'dateRange') {
    return resolveDateRange(value, resolutionContext) ?? OMIT_DATA_SOURCE_PARAM;
  }
  return type === 'timeRange' ? timeRangeFormatter(value) : value;
};

export const fetchWidgetData = async ({
  config,
  dataSource,
  extraParams,
  getSourceDataByApiId,
  unifiedFilterValues,
  filterBindings,
  filterDefinitions,
  throwError = false,
}: {
  config: any;
  dataSource?: any;
  extraParams?: Record<string, any>;
  getSourceDataByApiId: (dataSource: any, params: any) => Promise<any>;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
    throwError?: boolean;
}) => {
  if (!config?.dataSource) {
    return null;
  }

  try {
    const finalRequestParams = buildWidgetRequestParams({
      config,
      dataSource,
      extraParams,
      unifiedFilterValues,
      filterBindings,
      filterDefinitions,
    });

    const rawData = await getSourceDataByApiId(config.dataSource, finalRequestParams);
    return rawData;
  } catch (err: any) {
    console.error('获取数据失败:', err);
    if (throwError) {
      throw err;
    }
    return null;
  }
};

export const buildWidgetExtraParams = ({
  namespaceId,
  isTableLikeChart,
  tableQueryParams,
  runtimeParams,
}: {
  namespaceId?: number;
  isTableLikeChart: boolean;
  tableQueryParams: Record<string, unknown>;
  runtimeParams: Record<string, unknown>;
}) => ({
  ...(namespaceId !== undefined ? { namespace_id: namespaceId } : {}),
  ...(isTableLikeChart ? tableQueryParams : {}),
  ...runtimeParams,
});

export interface WidgetRequestHistory {
  signature: string | null;
  filterSearchVersion: number;
  namespaceSearchVersion: number;
  reloadVersion: string;
  tableQueryKey: string;
  hasRequested: boolean;
}

export interface WidgetRequestSnapshot {
  requestEnabled: boolean;
  requestSignature: string | null;
  hasRequestParams: boolean;
  hasRequestKey: boolean;
  filterSearchVersion: number;
  namespaceSearchVersion: number;
  reloadVersion: string;
  tableQueryKey: string;
  hasEnabledFilterBindings: boolean;
  widgetUsesNamespace: boolean;
  isTableLikeChart: boolean;
}

export const createWidgetRequestHistory = (
  current: WidgetRequestSnapshot,
): WidgetRequestHistory => ({
  signature: null,
  filterSearchVersion: current.filterSearchVersion,
  namespaceSearchVersion: current.namespaceSearchVersion,
  reloadVersion: current.reloadVersion,
  tableQueryKey: current.tableQueryKey,
  hasRequested: false,
});

export const decideWidgetRequest = ({
  history,
  current,
  suppressInitialCacheFetch,
}: {
  history: WidgetRequestHistory;
  current: WidgetRequestSnapshot;
  suppressInitialCacheFetch: boolean;
}): { shouldFetch: boolean; nextHistory: WidgetRequestHistory } => {
  const requestAvailable =
    current.requestEnabled &&
    Boolean(current.requestSignature) &&
    current.hasRequestParams &&
    current.hasRequestKey;

  if (!requestAvailable) {
    return {
      shouldFetch: false,
      nextHistory: {
        signature: current.requestSignature,
        filterSearchVersion: current.filterSearchVersion,
        namespaceSearchVersion: current.namespaceSearchVersion,
        reloadVersion: current.reloadVersion,
        tableQueryKey: current.tableQueryKey,
        hasRequested: false,
      },
    };
  }

  const shouldFetchForFilterSearch =
    history.filterSearchVersion !== current.filterSearchVersion &&
    current.hasEnabledFilterBindings;
  const shouldFetchForNamespaceSearch =
    history.namespaceSearchVersion !== current.namespaceSearchVersion &&
    current.widgetUsesNamespace;
  const shouldFetchForTableQuery =
    current.isTableLikeChart &&
    history.tableQueryKey !== current.tableQueryKey;
  const shouldFetch =
    !suppressInitialCacheFetch &&
    (!history.hasRequested ||
      history.signature !== current.requestSignature ||
      history.reloadVersion !== current.reloadVersion ||
      shouldFetchForFilterSearch ||
      shouldFetchForNamespaceSearch ||
      shouldFetchForTableQuery);

  return {
    shouldFetch,
    nextHistory: {
      signature: current.requestSignature,
      filterSearchVersion: current.filterSearchVersion,
      namespaceSearchVersion: current.namespaceSearchVersion,
      reloadVersion: current.reloadVersion,
      tableQueryKey: current.tableQueryKey,
      hasRequested:
        history.hasRequested || shouldFetch || suppressInitialCacheFetch,
    },
  };
};

export const shouldShowInitialWidgetLoading = ({
  loading,
  isTableLikeChart,
  hasRawPayload,
  hasSettledRequest,
}: {
  loading: boolean;
  isTableLikeChart: boolean;
  hasRawPayload: boolean;
  hasSettledRequest: boolean;
}): boolean =>
  loading && !isTableLikeChart && !hasRawPayload && !hasSettledRequest;

export const hasActiveWidgetRuntimeParams = (
  chartType: string | undefined,
  runtimeParams: Record<string, unknown>,
): boolean => chartType === 'topN' && Object.keys(runtimeParams).length > 0;

export const buildWidgetRequestParams = ({
  config,
  dataSource,
  extraParams,
  unifiedFilterValues,
  filterBindings,
  filterDefinitions,
  resolutionContext = createDateRangeResolutionContext(),
}: {
  config: any;
  dataSource?: any;
  extraParams?: Record<string, any>;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
  resolutionContext?: DateRangeResolutionContext;
}) => {
  const rawParams =
    Array.isArray(config?.dataSourceParams) && config.dataSourceParams.length > 0
      ? config.dataSourceParams
      : dataSource?.params;
  const sourceParams = Array.isArray(rawParams) ? rawParams : [];

  const userParams: Record<string, unknown> = {};
  sourceParams.forEach((param: any) => {
    userParams[param.name] = param.value;
  });
  Object.assign(userParams, extraParams || {});

  const requestParams = processDataSourceParams({
    sourceParams,
    userParams,
    unifiedFilterValues,
    filterBindings,
    filterDefinitions,
    resolutionContext,
  });

  return requestParams;
};

export const buildWidgetRequestSignatureParams = ({
  config,
  dataSource,
  extraParams,
  unifiedFilterValues,
  filterBindings,
  filterDefinitions,
  resolutionContext = createDateRangeResolutionContext(),
}: {
  config: any;
  dataSource?: any;
  extraParams?: Record<string, any>;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
  resolutionContext?: DateRangeResolutionContext;
}) => {
  const rawParams =
    Array.isArray(config?.dataSourceParams) && config.dataSourceParams.length > 0
      ? config.dataSourceParams
      : dataSource?.params;
  const sourceParams = Array.isArray(rawParams) ? rawParams : [];

  const userParams: Record<string, unknown> = {};
  sourceParams.forEach((param: any) => {
    userParams[param.name] = param.value;
  });
  Object.assign(userParams, extraParams || {});

  const requestParams = processDataSourceParams({
    sourceParams,
    userParams,
    unifiedFilterValues,
    filterBindings,
    filterDefinitions,
    resolutionContext,
    timeRangeFormatter: formatTimeRangeForSignature,
  });

  return requestParams;
};

export const processDataSourceParams = ({
  sourceParams,
  userParams = {},
  unifiedFilterValues,
  filterBindings,
  filterDefinitions,
  resolutionContext = createDateRangeResolutionContext(),
  timeRangeFormatter = formatTimeRange,
}: {
  sourceParams: any;
  userParams?: Record<string, any>;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
  resolutionContext?: DateRangeResolutionContext;
  timeRangeFormatter?: (timeParams: any) => unknown;
}) => {

  if (!sourceParams || !Array.isArray(sourceParams)) {
    return userParams;
  }

  const processedParams: Record<string, unknown> = { ...userParams };
  const setProcessedParam = (name: string, type: string, value: unknown) => {
    const formatted = formatDataSourceParamValue(
      type,
      value,
      resolutionContext,
      timeRangeFormatter,
    );
    if (formatted === OMIT_DATA_SOURCE_PARAM) {
      delete processedParams[name];
    } else {
      processedParams[name] = formatted;
    }
  };

  // 构建统一筛选定义映射：filterId -> definition
  const definitionsMap = new Map(
    (filterDefinitions || []).map((d) => [d.id, d]),
  );

  // 构建参数名到绑定的统一筛选ID的映射
  // 返回值：
  // - hasBinding: 组件是否绑定了统一筛选
  // - bindingDisabled: 绑定的统一筛选是否被禁用
  // - value: 统一筛选的当前值
  const getUnifiedFilterValue = (
    paramName: string,
    paramType: string,
  ): { hasBinding: boolean; bindingDisabled: boolean; value: FilterValue | undefined } => {
    if (!filterBindings || !unifiedFilterValues) {
      return { hasBinding: false, bindingDisabled: false, value: undefined };
    }

    // 查找绑定到该参数的统一筛选
    for (const [filterId, isEnabled] of Object.entries(filterBindings)) {
      const def = definitionsMap.get(filterId);
      // 严格匹配 key 和 type
      if (def && def.key === paramName && def.type === paramType) {
        // 组件配置的 filterBindings 开关关闭：不传该参数
        if (!isEnabled) {
          return { hasBinding: true, bindingDisabled: true, value: undefined };
        }
        // 头部筛选配置的 enabled 开关关闭：不传该参数
        if (!def.enabled) {
          return { hasBinding: true, bindingDisabled: true, value: undefined };
        }
        const value = unifiedFilterValues[filterId];
        return { hasBinding: true, bindingDisabled: false, value };
      }
    }
    return { hasBinding: false, bindingDisabled: false, value: undefined };
  };

  sourceParams.forEach((param: any) => {
    const { name, filterType, value: defaultValue, type } = param;

    // 优先级：fixed > 统一筛选 > params > 默认值
    switch (filterType) {
      case 'fixed':
        // 固定参数：直接使用配置值
        setProcessedParam(name, type, defaultValue);
        break;

      case 'filter': {
        // 筛选参数：检查统一筛选绑定
        const { hasBinding, bindingDisabled, value: unifiedValue } = getUnifiedFilterValue(name, type);
        
        if (hasBinding) {
          if (bindingDisabled) {
            // 绑定的统一筛选被禁用：不传该参数
            delete processedParams[name];
          } else if (unifiedValue !== null && unifiedValue !== undefined && unifiedValue !== '') {
            // 有绑定且有值：使用统一筛选值
            setProcessedParam(name, type, unifiedValue);
          } else {
            // 有绑定但无值：不传该参数
            delete processedParams[name];
          }
        } else {
          // 无绑定：使用默认值
          if (defaultValue !== null && defaultValue !== undefined && defaultValue !== '') {
            setProcessedParam(name, type, defaultValue);
          }
        }
        break;
      }

      case 'params':
        // 私有参数：使用用户传入的参数值
        if (processedParams[name] !== undefined) {
          setProcessedParam(name, type, processedParams[name]);
        } else if (defaultValue !== undefined) {
          setProcessedParam(name, type, defaultValue);
        }
        break;

      default:
        // 默认：使用配置的默认值
        if (defaultValue !== undefined) {
          setProcessedParam(name, type, defaultValue);
        }
    }
  });

  return processedParams;
};
