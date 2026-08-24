import type {
  FilterValue,
  FilterBindings,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { InputOption, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { supportsComponentSwitch } from '@/app/ops-analysis/utils/componentParamSwitch';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';
import { buildTableQueryParams } from '@/app/ops-analysis/utils/tablePagination';
import {
  isBindableDataSourceParamType,
  type BindableDataSourceParamType,
} from '@/app/ops-analysis/utils/dataSourceParamContract';
import {
  coerceRequestValueForMultiple,
  isMultipleSelectInputConfig,
  migrateFilterBindings,
  migrateParamItemsFromStringList,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';
import {
  DateRangeResolutionContext,
  getDateRangeTimezone,
  resolveDateRange,
} from '@/app/ops-analysis/utils/dateRange';

export type BindableParamType = BindableDataSourceParamType;
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

  const multiple =
    definition.type === 'string'
    && definition.inputConfig
    && definition.inputConfig.control !== 'input'
    && Boolean(definition.inputConfig.multiple);

  const defaultValue = sanitizeFilterDefaultValue(
    definition.defaultValue,
    staticOptions,
    multiple,
  );

  return {
    ...definition,
    inputMode,
    options: Array.isArray(definition.options) ? definition.options : undefined,
    defaultValue,
  };
};

const isScalarFilterValue = (value: unknown): value is string | number =>
  typeof value === 'string' || typeof value === 'number';

const sanitizeFilterDefaultValue = (
  defaultValue: FilterValue | undefined,
  staticOptions?: InputOption[],
  multiple = false,
): FilterValue | undefined => {
  if (multiple) {
    const asList = Array.isArray(defaultValue)
      ? defaultValue.filter(isScalarFilterValue)
      : isScalarFilterValue(defaultValue)
        ? [defaultValue]
        : defaultValue == null
          ? defaultValue
          : null;
    if (!Array.isArray(asList)) {
      return asList;
    }
    if (!staticOptions) {
      return asList;
    }
    const allowed = asList.filter((item) =>
      staticOptions.some((option) => option.value === item),
    );
    return allowed.length === asList.length ? asList : allowed.length ? allowed : null;
  }

  if (!staticOptions) {
    return defaultValue;
  }
  return staticOptions.some((item) => item.value === defaultValue)
    ? defaultValue
    : null;
};

export const getFilterDefinitionId = (
  key: string,
  type: BindableParamType,
): string => `${key}__${type}`;

export const getBindableFilterParams = (
  params?: ParamItem[],
): Array<ParamItem & { type: BindableParamType }> => {
  const { params: migratedParams } = migrateParamItemsFromStringList(params);
  return migratedParams.filter(
    (param): param is ParamItem & { type: BindableParamType } =>
      param.filterType === 'filter' &&
      isBindableDataSourceParamType(param.type),
  );
};

export const buildDefaultFilterBindings = (
  params: ParamItem[] | undefined,
  definitions: UnifiedFilterDefinition[],
  existingBindings?: FilterBindings,
): FilterBindings | undefined => {
  const migratedExisting = existingBindings
    ? migrateFilterBindings(existingBindings)
    : undefined;
  const bindableParams = getBindableFilterParams(params);
  if (!bindableParams.length || !definitions.length) {
    return migratedExisting ?? existingBindings;
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
    return migratedExisting ?? existingBindings;
  }

  const retainedBindings = Object.entries(migratedExisting || {}).reduce<FilterBindings>(
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

/**
 * 已有 bindings：仅 remap legacy `__stringList` → `__string`，保留显式 enabled/disabled。
 * 无 bindings：才按定义生成默认绑定。
 */
export const resolveEffectiveFilterBindings = (
  params: ParamItem[] | undefined,
  definitions: UnifiedFilterDefinition[],
  existingBindings?: FilterBindings | null,
): FilterBindings | undefined => {
  if (existingBindings && Object.keys(existingBindings).length > 0) {
    return migrateFilterBindings(existingBindings);
  }
  return buildDefaultFilterBindings(params, definitions, undefined);
};

const getRelativeTimeRangeMinutes = (timeParams: unknown): number | null => {
  if (typeof timeParams === 'number' && Number.isFinite(timeParams) && timeParams > 0) {
    return timeParams;
  }
  if (!timeParams || typeof timeParams !== 'object' || Array.isArray(timeParams)) {
    return null;
  }
  const selectValue = (timeParams as { selectValue?: unknown }).selectValue;
  if (typeof selectValue === 'number' && Number.isFinite(selectValue) && selectValue > 0) {
    return selectValue;
  }
  return null;
};

export const formatTimeRange = (timeParams: any): unknown => {
  const relativeMinutes = getRelativeTimeRangeMinutes(timeParams);
  if (relativeMinutes !== null) {
    return { selectValue: relativeMinutes };
  }

  if (timeParams && Array.isArray(timeParams) && timeParams.length === 2) {
    return [
      formatOpsRequestTime(timeParams[0]),
      formatOpsRequestTime(timeParams[1]),
    ];
  }

  if (timeParams && timeParams.start && timeParams.end) {
    return {
      start: formatOpsRequestTime(timeParams.start),
      end: formatOpsRequestTime(timeParams.end),
    };
  }

  return timeParams;
};

const formatTimeRangeForSignature = (timeParams: any): unknown => {
  const relativeMinutes = getRelativeTimeRangeMinutes(timeParams);
  if (relativeMinutes !== null) {
    return { mode: 'relative', value: relativeMinutes };
  }

  if (timeParams && Array.isArray(timeParams) && timeParams.length === 2) {
    return [
      formatOpsRequestTime(timeParams[0]),
      formatOpsRequestTime(timeParams[1]),
    ];
  }

  if (timeParams && timeParams.start && timeParams.end) {
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
  if (value === null || value === undefined || value === '') {
    return OMIT_DATA_SOURCE_PARAM;
  }
  if (Array.isArray(value) && value.length === 0) {
    return OMIT_DATA_SOURCE_PARAM;
  }
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

    const result = await getSourceDataByApiId(config.dataSource, finalRequestParams);
    return result.data;
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
  dataSourceParams,
}: {
  namespaceId?: number;
  isTableLikeChart: boolean;
  tableQueryParams: Record<string, unknown>;
  runtimeParams: Record<string, unknown>;
  dataSourceParams?: ParamItem[];
}) => ({
  ...(namespaceId !== undefined ? { namespace_id: namespaceId } : {}),
  ...(isTableLikeChart
    ? buildTableQueryParams({ dataSourceParams, queryParams: tableQueryParams })
    : {}),
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
}: {
  history: WidgetRequestHistory;
  current: WidgetRequestSnapshot;
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
    !history.hasRequested ||
      history.signature !== current.requestSignature ||
      history.reloadVersion !== current.reloadVersion ||
      shouldFetchForFilterSearch ||
      shouldFetchForNamespaceSearch ||
      shouldFetchForTableQuery;

  return {
    shouldFetch,
    nextHistory: {
      signature: current.requestSignature,
      filterSearchVersion: current.filterSearchVersion,
      namespaceSearchVersion: current.namespaceSearchVersion,
      reloadVersion: current.reloadVersion,
      tableQueryKey: current.tableQueryKey,
      hasRequested: history.hasRequested || shouldFetch,
    },
  };
};

export const shouldShowInitialWidgetLoading = ({
  loading,
  hasRawPayload,
  hasSettledRequest,
}: {
  loading: boolean;
  isTableLikeChart: boolean;
  hasRawPayload: boolean;
  hasSettledRequest: boolean;
}): boolean =>
  loading && !hasRawPayload && !hasSettledRequest;

export const hasActiveWidgetRuntimeParams = (
  chartType: string | undefined,
  runtimeParams: Record<string, unknown>,
): boolean => supportsComponentSwitch(chartType) && Object.keys(runtimeParams).length > 0;

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
    return Object.fromEntries(
      Object.entries(userParams).filter(
        ([, value]) => value !== null && value !== undefined && value !== '',
      ),
    );
  }

  const processedParams: Record<string, unknown> = { ...userParams };
  const migratedSourceParams = migrateParamItemsFromStringList(sourceParams).params;
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
  // - definition: 匹配到的筛选项（用于 multiple 形状）
  const getUnifiedFilterValue = (
    paramName: string,
    paramType: string,
  ): {
    hasBinding: boolean;
    bindingDisabled: boolean;
    value: FilterValue | undefined;
    definition?: UnifiedFilterDefinition;
  } => {
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
          return {
            hasBinding: true,
            bindingDisabled: true,
            value: undefined,
            definition: def,
          };
        }
        // 头部筛选配置的 enabled 开关关闭：不传该参数
        if (!def.enabled) {
          return {
            hasBinding: true,
            bindingDisabled: true,
            value: undefined,
            definition: def,
          };
        }
        const value = unifiedFilterValues[filterId];
        return {
          hasBinding: true,
          bindingDisabled: false,
          value,
          definition: def,
        };
      }
    }
    return { hasBinding: false, bindingDisabled: false, value: undefined };
  };

  const resolveConsumerMultiple = (
    param: ParamItem,
    boundDefinition?: UnifiedFilterDefinition,
  ): boolean => {
    if (boundDefinition) {
      return isMultipleSelectInputConfig(boundDefinition.inputConfig);
    }
    return isMultipleSelectInputConfig(param.inputConfig);
  };

  const setShapedParam = (
    name: string,
    type: string,
    value: unknown,
    multiple: boolean,
  ) => {
    // 仅字符串侧按 multiple 规范形状；timeRange/dateRange 等保持原协议
    if (type === 'string') {
      const shaped = coerceRequestValueForMultiple(value, multiple);
      if (shaped === null) {
        delete processedParams[name];
        return;
      }
      setProcessedParam(name, type, shaped);
      return;
    }
    if (
      value === null ||
      value === undefined ||
      value === '' ||
      (Array.isArray(value) && value.length === 0)
    ) {
      delete processedParams[name];
      return;
    }
    setProcessedParam(name, type, value);
  };

  migratedSourceParams.forEach((param: any) => {
    const { name, filterType, value: defaultValue, type } = param;

    // 优先级：fixed > 统一筛选 > params > 默认值
    switch (filterType) {
      case 'fixed':
        // 固定参数：直接使用配置值（形状仍按参数自身 multiple）
        setShapedParam(
          name,
          type,
          defaultValue,
          resolveConsumerMultiple(param),
        );
        break;

      case 'filter': {
        // 筛选参数：检查统一筛选绑定
        const {
          hasBinding,
          bindingDisabled,
          value: unifiedValue,
          definition,
        } = getUnifiedFilterValue(name, type);

        if (hasBinding) {
          if (bindingDisabled) {
            // 绑定的统一筛选被禁用：不传该参数
            delete processedParams[name];
          } else {
            // 有绑定：按筛选项 multiple 决定形状；空则省略
            setShapedParam(
              name,
              type,
              unifiedValue,
              resolveConsumerMultiple(param, definition),
            );
          }
        } else {
          // 无绑定：使用默认值，按参数自身 multiple
          setShapedParam(
            name,
            type,
            defaultValue,
            resolveConsumerMultiple(param),
          );
        }
        break;
      }

      case 'params':
        // 私有参数：使用用户传入的参数值，按组件参数/覆盖的 multiple
        if (Object.prototype.hasOwnProperty.call(processedParams, name)) {
          setShapedParam(
            name,
            type,
            processedParams[name],
            resolveConsumerMultiple(param),
          );
        } else {
          setShapedParam(
            name,
            type,
            defaultValue,
            resolveConsumerMultiple(param),
          );
        }
        break;

      default:
        // 默认：使用配置的默认值
        if (defaultValue !== undefined) {
          setShapedParam(
            name,
            type,
            defaultValue,
            resolveConsumerMultiple(param),
          );
        }
    }
  });

  return Object.fromEntries(
    Object.entries(processedParams).filter(
      ([, value]) =>
        value !== null &&
        value !== undefined &&
        value !== '' &&
        !(Array.isArray(value) && value.length === 0),
    ),
  );
};
