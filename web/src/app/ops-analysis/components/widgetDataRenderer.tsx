import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { createPortal } from "react-dom";
import { Spin, message } from "antd";
import { useTranslation } from "@/utils/i18n";
import {
  FilterValue,
  ScreenRenderContext,
  UnifiedFilterDefinition,
  ValueConfig,
} from "@/app/ops-analysis/types/dashBoard";
import { DatasourceItem } from "@/app/ops-analysis/types/dataSource";
import {
  buildWidgetExtraParams,
  buildWidgetRequestParams,
  buildWidgetRequestSignatureParams,
  createWidgetRequestHistory,
  decideWidgetRequest,
  hasActiveWidgetRuntimeParams,
  shouldShowInitialWidgetLoading,
} from "@/app/ops-analysis/utils/widgetDataTransform";
import {
  beginOwnerRequest,
  finishOwnerRequest,
  isSilentCanvasRuntimeRefresh,
  isStartedOwnerRequest,
  resolveWidgetFetchCause,
  shouldKeepWidgetRuntimeDataOnError,
  shouldShowWidgetRuntimeLoading,
  type CanvasRuntimeRefreshCause,
} from "@/app/ops-analysis/utils/canvasRefreshTimer";
import {
  findComponentSwitchParams,
  getTypedValueKey,
  reconcileComponentSwitchValue,
  resolveComponentSwitchRequestGate,
  resolveComponentSwitchRuntime,
  supportsComponentSwitch,
} from "@/app/ops-analysis/utils/componentParamSwitch";
import { useParamInputOptions } from "@/app/ops-analysis/hooks/useParamInputOptions";
import { fetchCompareData } from "@/app/ops-analysis/utils/compareQuery";
import { useDataSourceApi, withRuntimeSourceDataErrorSuppression } from "@/app/ops-analysis/api/dataSource";
import { ChartDataTransformer } from "@/app/ops-analysis/utils/chartDataTransform";
import { getRequestErrorMessage, classifyWidgetQueryError } from "@/app/ops-analysis/utils/requestError";
import { getValueByPath } from "@/app/ops-analysis/utils/objectPath";
import { buildWidgetRequestCacheKey } from "@/app/ops-analysis/utils/widgetRequestCache";
import { useDashboardRuntimeScheduler } from "@/app/ops-analysis/context/dashboardRuntimeScheduler";
import {
  RuntimeRequestCancelledError,
  type RuntimeRequestPriority,
} from "@/app/ops-analysis/utils/dashboardRuntimeScheduler";
import {
  buildWidgetRequestVersionKey,
  resolveWidgetDataSourceState,
  shouldWaitForInitialWidgetData,
} from "@/app/ops-analysis/utils/widgetRequestVersion";
import WidgetRenderer from "@/app/ops-analysis/components/widgetRenderer";
import WidgetErrorState from "@/app/ops-analysis/components/widgetErrorState";
import WidgetState from "@/app/ops-analysis/components/widget-state";
import { useWidgetHeaderRuntimeSlot } from "@/app/ops-analysis/components/widgetHeaderRuntimeSlot";
import ComponentParamSwitchControl from "@/app/ops-analysis/components/componentParamSwitchControl";
import ScreenWidgetThemeProvider from "@/app/ops-analysis/components/screenWidgetThemeProvider";
import { getDateRangeTimezone } from "@/app/ops-analysis/utils/dateRange";
import {
  areTableQueryParamsEquivalent,
  serializeTableQueryKey,
} from "@/app/ops-analysis/utils/tablePagination";
import { validateMultiValueData } from "@/app/ops-analysis/utils/multiValueData";
import { validateEventTimelinePayload } from "@/app/ops-analysis/utils/eventTimeline";
import { validateCardListPayload } from "@/app/ops-analysis/utils/cardList";
import { resolveRadarSeriesData } from "@/app/ops-analysis/utils/radarData";
import { useOpsAnalysis } from "@/app/ops-analysis/context/common";
import type { DashboardWidgetRenderResult } from "@/app/ops-analysis/renderContract";
import {
  hasRenderableChartData,
  validateTopologyMapWidgetData,
} from "@/app/ops-analysis/utils/topologyMapWidgetContract";
import { isSelfFetchSceneWidget } from "@/app/ops-analysis/types/sceneWidgetCapability";

const validateTopNData = (
  data: unknown,
  config?: ValueConfig,
  errorMessage?: string,
): { isValid: boolean; message?: string } => {
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return { isValid: true };
  }

  if (!Array.isArray(data)) {
    return { isValid: false, message: errorMessage || "数据格式不匹配" };
  }

  const labelField = config?.topNLabelField;
  const valueField = config?.topNValueField;

  const hasValidData = data.some((item) => {
    if (Array.isArray(item) && item.length >= 2) {
      const rawName = getValueByPath(item, labelField);
      const rawValue = getValueByPath(item, valueField);
      const name =
        rawName === undefined || rawName === null ? "" : String(rawName).trim();
      const value = Number(rawValue);
      return !!name && !Number.isNaN(value);
    }

    if (!item || typeof item !== "object") {
      return false;
    }

    const rawName = getValueByPath(item, labelField);
    const rawValue = getValueByPath(item, valueField);

    const name =
      rawName === undefined || rawName === null ? "" : String(rawName).trim();
    const value = Number(rawValue);
    return !!name && !Number.isNaN(value);
  });

  return hasValidData
    ? { isValid: true }
    : { isValid: false, message: errorMessage || "数据格式不匹配" };
};

const DEFAULT_RUNTIME_PRIORITY: RuntimeRequestPriority = {
  cause: 1,
  visibility: 0,
  distance: 0,
  order: 0,
};

const validateGaugeData = (
  data: unknown,
  config?: ValueConfig,
): { isValid: boolean; message?: string } => {
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return { isValid: true };
  }

  const selectedField = config?.selectedFields?.[0];
  const failMessage =
    "数据结构不符：仪表盘期望 number，或包含数值字段的对象/数组（可通过“展示字段”指定）";

  const hasNumericValue = (value: unknown) => {
    if (typeof value === "number") return Number.isFinite(value);
    if (typeof value === "string") {
      const parsed = Number(value);
      return Number.isFinite(parsed);
    }
    return false;
  };

  if (Array.isArray(data)) {
    const firstItem = data[0];
    if (selectedField && firstItem && typeof firstItem === "object") {
      return hasNumericValue(getValueByPath(firstItem, selectedField))
        ? { isValid: true }
        : { isValid: false, message: failMessage };
    }

    if (hasNumericValue(firstItem)) {
      return { isValid: true };
    }

    if (firstItem && typeof firstItem === "object") {
      const values = Object.values(firstItem as Record<string, unknown>);
      return values.some((item) => hasNumericValue(item))
        ? { isValid: true }
        : { isValid: false, message: failMessage };
    }

    return { isValid: false, message: failMessage };
  }

  if (typeof data === "object") {
    if (selectedField) {
      return hasNumericValue(getValueByPath(data, selectedField))
        ? { isValid: true }
        : { isValid: false, message: failMessage };
    }

    const values = Object.values(data as Record<string, unknown>);
    return values.some((item) => hasNumericValue(item))
      ? { isValid: true }
      : { isValid: false, message: failMessage };
  }

  return hasNumericValue(data)
    ? { isValid: true }
    : { isValid: false, message: failMessage };
};

const validateEventTableData = (
  data: unknown,
): { isValid: boolean; message?: string } => {
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return { isValid: true };
  }

  const failMessage =
    "数据结构不符：事件表期望数组，或包含 items 数组的分页结构";

  const list = Array.isArray(data)
    ? data
    : data &&
        typeof data === "object" &&
        Array.isArray((data as Record<string, unknown>).items)
      ? ((data as Record<string, unknown>).items as unknown[])
      : null;

  if (!list) {
    return { isValid: false, message: failMessage };
  }

  if (list.length === 0) {
    return { isValid: true };
  }

  const hasExpectedRow = list.some((item) => {
    return Boolean(item) && typeof item === "object";
  });

  return hasExpectedRow
    ? { isValid: true }
    : { isValid: false, message: failMessage };
};

const validateEventTimelineData = (
  data: unknown,
): { isValid: boolean; message?: string } =>
  validateEventTimelinePayload(data);

const validateRadarData = (
  data: unknown,
  config?: ValueConfig,
): { isValid: boolean; message?: string } => {
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return { isValid: true };
  }

  const series = resolveRadarSeriesData(
    data,
    config?.radar,
    config?.selectedFields || [],
  );

  if (series.unsupported === "multi_series") {
    return {
      isValid: false,
      message: "雷达图当前仅支持单实体多维数据，不支持多实体对比输入",
    };
  }

  if (series.indicatorLabels.length === 0) {
    return {
      isValid: false,
      message:
        "数据结构不符：雷达图期望 [{name,value}] 或对象 + 指标字段映射",
    };
  }

  return { isValid: true };
};

export interface WidgetWrapperProps {
  dashboardId?: number | string;
  widgetId: string;
  chartType?: string;
  config?: ValueConfig;
  onReady?: (hasData?: boolean) => void;
  dataSource?: DatasourceItem;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterDefinitions?: UnifiedFilterDefinition[];
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  reloadVersion?: string;
  refreshCause?: CanvasRuntimeRefreshCause;
  builtinNamespaceId?: number;
  screenRenderContext?: ScreenRenderContext;
  onRenderStatus?: (result: DashboardWidgetRenderResult) => void;
  layoutEditable?: boolean;
  runtimeActive?: boolean;
  runtimePriority?: RuntimeRequestPriority;
  surface?: import('@/app/ops-analysis/utils/chartTypeSurface').OpsAnalysisWidgetSurface;
  onTopologyLayoutChange?: (
    next: NonNullable<ValueConfig['networkStatusTopology']>,
  ) => void;
}

const WidgetWrapper: React.FC<WidgetWrapperProps> = ({
  dashboardId,
  chartType,
  config,
  onReady,
  dataSource,
  unifiedFilterValues,
  filterDefinitions,
  filterSearchVersion = 0,
  namespaceSearchVersion = 0,
  reloadVersion = "0:0",
  refreshCause = "manual",
  builtinNamespaceId,
  screenRenderContext,
  widgetId,
  onRenderStatus,
  layoutEditable,
  runtimeActive = true,
  runtimePriority = DEFAULT_RUNTIME_PRIORITY,
  surface = 'dashboard',
  onTopologyLayoutChange,
}) => {
  const { t } = useTranslation();
  const headerRuntimeSlot = useWidgetHeaderRuntimeSlot();
  const [rawData, setRawData] = useState<any>(null);
  const [baselineData, setBaselineData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [hasSettledRequest, setHasSettledRequest] = useState(false);
  const hasSettledRequestRef = useRef(false);
  const [tableLoading, setTableLoading] = useState(false);
  const [dataValidation, setDataValidation] = useState<{
    isValid: boolean;
    message?: string;
    errorCode?: string;
  } | null>(null);
  const [tableQueryParams, setTableQueryParams] = useState<Record<string, any>>(
    {},
  );
  const { canvasDataSourceLookupStatus, dataSources } = useOpsAnalysis();
  const runtimeScheduler = useDashboardRuntimeScheduler();
  const { getSourceDataByApiId } = useDataSourceApi();
  const optionConsumerSequenceRef = useRef(0);
  const getRuntimeSourceDataByApiId = useMemo(
    () => withRuntimeSourceDataErrorSuppression(getSourceDataByApiId),
    [getSourceDataByApiId],
  );
  const isSceneWidget = isSelfFetchSceneWidget(config?.sceneWidgetType);
  const effectiveComponentParams = useMemo(() => {
    const overrides = config?.dataSourceParams || [];
    if (!dataSource?.params?.length) return overrides;
    return dataSource.params.map((param) => {
      const override = overrides.find((item) => item.name === param.name);
      return override ? { ...param, ...override } : param;
    });
  }, [config?.dataSourceParams, dataSource?.params]);
  const componentSwitchParam = useMemo(
    () => supportsComponentSwitch(chartType) ? findComponentSwitchParams(effectiveComponentParams)[0] : undefined,
    [chartType, effectiveComponentParams],
  );
  const componentSwitchOptionsLoaderOptions = useMemo(
    () => ({
      suppressErrorNotification: true as const,
      fallbackErrorMessage: t("dashboard.dataFetchFailed"),
      knownDataSources: dataSources,
    }),
    [dataSources, t],
  );
  const scheduleOptionsPhysical = useCallback(
    <T,>(physicalKey: string, start: () => Promise<T>) => {
      if (!runtimeActiveRef.current) {
        return Promise.reject(new RuntimeRequestCancelledError());
      }
      if (!runtimeScheduler) return start();
      return runtimeScheduler.schedule({
        consumerId: `${widgetId}:options:${++optionConsumerSequenceRef.current}`,
        ownerId: widgetId,
        physicalKey,
        priority: { ...runtimePriority, cause: 1 },
        start,
      });
    },
    [runtimePriority, runtimeScheduler, widgetId],
  );
  const scheduledOptionsSourceData = useCallback(
    (id: number, params?: unknown, options?: { suppressErrorNotification?: boolean }) => {
      return scheduleOptionsPhysical(
        `options:source:${JSON.stringify(componentSwitchParam?.inputConfig)}:${id}:${JSON.stringify(params ?? {})}`,
        () => getSourceDataByApiId(id, params, options),
      );
    },
    [
      componentSwitchParam?.inputConfig,
      getSourceDataByApiId,
      scheduleOptionsPhysical,
    ],
  );
  const optionState = useParamInputOptions(
    componentSwitchParam?.inputConfig,
    componentSwitchOptionsLoaderOptions,
    {
      enabled: runtimeActive,
      getSourceDataByApiId: scheduledOptionsSourceData,
    },
  );
  const rawSavedComponentSwitchValue = componentSwitchParam
    ? config?.params?.[componentSwitchParam.name] ?? componentSwitchParam.value
    : undefined;
  const savedComponentSwitchValue =
    typeof rawSavedComponentSwitchValue === "string" || typeof rawSavedComponentSwitchValue === "number"
      ? rawSavedComponentSwitchValue
      : undefined;
  const runtimeParamScopeKey = useMemo(
    () =>
      JSON.stringify({
        chartType,
        dataSource: config?.dataSource,
        param: componentSwitchParam?.name,
        inputConfig: componentSwitchParam?.inputConfig,
        savedValue:
          typeof savedComponentSwitchValue === "string" || typeof savedComponentSwitchValue === "number"
            ? getTypedValueKey(savedComponentSwitchValue)
            : null,
      }),
    [
      chartType,
      config?.dataSource,
      componentSwitchParam?.inputConfig,
      componentSwitchParam?.name,
      savedComponentSwitchValue,
    ],
  );
  const runtimeParamInitialValue = useMemo(
    () => {
      const reconciled = optionState.status === "success"
        ? reconcileComponentSwitchValue(savedComponentSwitchValue, optionState.options)
        : savedComponentSwitchValue;
      return typeof reconciled === "string" || typeof reconciled === "number"
        ? reconciled
        : undefined;
    },
    [optionState.status, optionState.options, savedComponentSwitchValue],
  );
  const [runtimeParamState, setRuntimeParamState] = useState<{
    scopeKey: string;
    value?: string | number;
  }>(() => ({
    scopeKey: runtimeParamScopeKey,
    value: runtimeParamInitialValue,
  }));
  const runtimeParamValue =
    runtimeParamState.scopeKey === runtimeParamScopeKey
      ? runtimeParamState.value
      : runtimeParamInitialValue;

  useEffect(() => {
    setRuntimeParamState((previous) =>
      previous.scopeKey === runtimeParamScopeKey
        ? previous
        : {
          scopeKey: runtimeParamScopeKey,
          value: runtimeParamInitialValue,
        },
    );
  }, [runtimeParamInitialValue, runtimeParamScopeKey]);

  useEffect(() => {
    if (optionState.status !== "success") return;
    setRuntimeParamState((previous) => {
      if (previous.scopeKey !== runtimeParamScopeKey) {
        return { scopeKey: runtimeParamScopeKey, value: runtimeParamInitialValue };
      }
      const reconciled = reconcileComponentSwitchValue(
        previous.value,
        optionState.options,
      );
      if (typeof reconciled !== "string" && typeof reconciled !== "number") {
        return previous;
      }
      return reconciled === previous.value
        ? previous
        : { ...previous, value: reconciled };
    });
  }, [optionState.status, optionState.options, runtimeParamInitialValue, runtimeParamScopeKey]);

  const handleRuntimeParamChange = useCallback(
    (value: string | number) => {
      setRuntimeParamState({ scopeKey: runtimeParamScopeKey, value });
    },
    [runtimeParamScopeKey],
  );
  const componentSwitchControl = optionState.status === "success" ? (
    <ComponentParamSwitchControl
      inputConfig={componentSwitchParam?.inputConfig}
      options={optionState.options}
      value={runtimeParamValue as string | number | undefined}
      onChange={handleRuntimeParamChange}
      block={!headerRuntimeSlot}
      chartThemeMode={config?.chartThemeMode}
    />
  ) : null;
  const runtimeHeaderControl =
    chartType === "topN" && headerRuntimeSlot && componentSwitchControl
      ? createPortal(
        componentSwitchControl,
        headerRuntimeSlot,
      )
      : null;
  const inlineComponentSwitchControl = chartType === "room3D"
    ? componentSwitchControl
    : headerRuntimeSlot ? null : componentSwitchControl;

  const fetchIdRef = useRef(0);
  const inflightCountRef = useRef(0);
  const mountedRef = useRef(true);
  const lifecycleRef = useRef(0);
  const physicalConsumerSequenceRef = useRef(0);
  const runtimeActiveRef = useRef(runtimeActive);
  runtimeActiveRef.current = runtimeActive;
  const rawDataRef = useRef<unknown>(null);
  rawDataRef.current = rawData;
  const tableQueryKey = useMemo(
    () => serializeTableQueryKey(tableQueryParams, dataSource?.params),
    [dataSource?.params, tableQueryParams],
  );
  const normalizedDataSourceId = useMemo(() => {
    if (typeof config?.dataSource === "string") {
      return parseInt(config.dataSource, 10);
    }
    return config?.dataSource;
  }, [config?.dataSource]);
  const widgetDataSourceState = resolveWidgetDataSourceState({
    hasDataSourceId: Boolean(normalizedDataSourceId),
    hasResolvedDataSource: Boolean(dataSource),
    lookupStatus: canvasDataSourceLookupStatus,
  });
  const isTableLikeChart = chartType === "table" || chartType === "eventTable";
  const widgetUsesNamespace = useMemo(
    () =>
      Array.isArray(dataSource?.namespaces) && dataSource.namespaces.length > 0,
    [dataSource?.namespaces],
  );
  const effectiveNamespaceId = useMemo(() => {
    if (builtinNamespaceId !== undefined) {
      return builtinNamespaceId;
    }

    return dataSource?.namespaces?.[0];
  }, [builtinNamespaceId, dataSource?.namespaces]);
  const runtimeParams = useMemo(
    () => optionState.status === "success"
      ? resolveComponentSwitchRuntime(
        chartType,
        componentSwitchParam,
        optionState.options,
        runtimeParamValue,
      ).params
      : {},
    [
      chartType,
      componentSwitchParam,
      optionState.status,
      optionState.options,
      runtimeParamValue,
    ],
  );
  const componentSwitchRequestGate = useMemo(
    () =>
      resolveComponentSwitchRequestGate({
        hasComponentSwitchParam: Boolean(componentSwitchParam),
        optionStatus: optionState.status,
        runtimeParams,
      }),
    [componentSwitchParam, optionState.status, runtimeParams],
  );
  const switchOptionsLoadError =
    optionState.status === "error" ? optionState.errorMessage : undefined;
  const isEmptyComponentSwitch =
    componentSwitchRequestGate === "blocked" && !switchOptionsLoadError;
  const requestEnabled =
    Boolean(normalizedDataSourceId) &&
    Boolean(dataSource) &&
    dataSource?.hasAuth !== false &&
    (!widgetUsesNamespace || effectiveNamespaceId !== undefined) &&
    componentSwitchRequestGate === "ready";
  const requestExtraParams = useMemo(
    () =>
      buildWidgetExtraParams({
        namespaceId: widgetUsesNamespace ? effectiveNamespaceId : undefined,
        isTableLikeChart,
        tableQueryParams,
        runtimeParams,
        dataSourceParams: dataSource?.params,
      }),
    [
      effectiveNamespaceId,
      isTableLikeChart,
      runtimeParams,
      tableQueryParams,
      dataSource?.params,
      widgetUsesNamespace,
    ],
  );
  const dateRangeResolutionInputKey = useMemo(
    () => JSON.stringify({
      dataSource: normalizedDataSourceId,
      dataSourceParams: config?.dataSourceParams ?? dataSource?.params,
      requestExtraParams,
      unifiedFilterValues,
      filterBindings: config?.filterBindings,
      filterDefinitions,
      compare: config?.compare,
    }),
    [
      normalizedDataSourceId,
      config?.dataSourceParams,
      dataSource?.params,
      requestExtraParams,
      unifiedFilterValues,
      config?.filterBindings,
      filterDefinitions,
      config?.compare,
    ],
  );
  const dateRangeResolutionContext = useMemo(
    () => ({
      referenceNow: Date.now(),
      timezone: getDateRangeTimezone(),
    }),
    [
      dateRangeResolutionInputKey,
      reloadVersion,
      filterSearchVersion,
      namespaceSearchVersion,
      tableQueryKey,
    ],
  );

  const requestParams = useMemo(() => {
    if (!requestEnabled) {
      return null;
    }

    return buildWidgetRequestParams({
      config,
      dataSource,
      extraParams: requestExtraParams,
      unifiedFilterValues,
      filterBindings: config?.filterBindings,
      filterDefinitions,
      resolutionContext: dateRangeResolutionContext,
    });
  }, [
    requestEnabled,
    config,
    dataSource,
    requestExtraParams,
    unifiedFilterValues,
    filterDefinitions,
    dateRangeResolutionContext,
  ]);

  const requestSignatureParams = useMemo(() => {
    if (!requestEnabled) {
      return null;
    }

    return buildWidgetRequestSignatureParams({
      config,
      dataSource,
      extraParams: requestExtraParams,
      unifiedFilterValues,
      filterBindings: config?.filterBindings,
      filterDefinitions,
      resolutionContext: dateRangeResolutionContext,
    });
  }, [
    requestEnabled,
    config,
    dataSource,
    requestExtraParams,
    unifiedFilterValues,
    filterDefinitions,
    dateRangeResolutionContext,
  ]);

  const requestSignature = useMemo(() => {
    if (isSceneWidget || !normalizedDataSourceId || !requestSignatureParams) {
      return null;
    }

    return JSON.stringify({
      dataSourceId: normalizedDataSourceId,
      compare: Boolean(config?.compare),
      requestParams: requestSignatureParams,
    });
  }, [
    config?.compare,
    isSceneWidget,
    normalizedDataSourceId,
    requestSignatureParams,
  ]);

  const hasEnabledFilterBindings = useMemo(() => {
    const bindings = config?.filterBindings;
    return Boolean(
      bindings && Object.values(bindings).some((enabled) => enabled),
    );
  }, [config?.filterBindings]);

  const requestVersionKey = useMemo(
    () =>
      buildWidgetRequestVersionKey({
        reloadVersion,
        filterSearchVersion,
        namespaceSearchVersion,
        hasEnabledFilterBindings,
        widgetUsesNamespace,
      }),
    [
      filterSearchVersion,
      hasEnabledFilterBindings,
      namespaceSearchVersion,
      reloadVersion,
      widgetUsesNamespace,
    ],
  );

  const requestKey = useMemo(() => {
    if (!requestSignature) {
      return null;
    }

    return buildWidgetRequestCacheKey({
      scopeId: dashboardId,
      requestVersionKey,
      requestSignature,
    });
  }, [dashboardId, requestSignature, requestVersionKey]);

  const handleTableQueryChange = useCallback((params: Record<string, any>) => {
    setTableQueryParams((prev) => {
      const next = params || {};
      return areTableQueryParamsEquivalent(prev, next, dataSource?.params)
        ? prev
        : next;
    });
  }, [dataSource?.params]);

  const validateChartData = useCallback(
    (data: unknown, type?: string) => {
      const errorMessage = t("dashboard.dataFormatMismatch");
      if (type === "topologyMap") {
        return validateTopologyMapWidgetData(data, errorMessage);
      }
      if (type === "cardList") {
        return validateCardListPayload(data, {
          titleField: config?.cardList?.titleField || "",
        });
      }

      const isDataEmpty = () =>
        !data || (Array.isArray(data) && data.length === 0);

      if (isDataEmpty()) {
        return { isValid: true };
      }

      switch (type) {
        case "pie":
          return ChartDataTransformer.validatePieData(data, errorMessage);
        case "line":
        case "bar":
          return ChartDataTransformer.validateLineBarData(data, errorMessage);
        case "topN":
          return validateTopNData(data, config, errorMessage);
        case "gauge":
          return validateGaugeData(data, config);
        case "eventTable":
          return validateEventTableData(data);
        case "eventTimeline":
          return validateEventTimelineData(data);
        case "radar":
          return validateRadarData(data, config);
        case "multiValue":
          const result = validateMultiValueData(data, errorMessage);
          return { isValid: result.isValid, message: result.errorMessage };
        case "table":
          return { isValid: true };
        default:
          return { isValid: true };
      }
    },
    [config, t],
  );

  const fetchDataRef = useRef<
    (key: string, cause: CanvasRuntimeRefreshCause) => Promise<void>
      >(undefined!);
  fetchDataRef.current = async (requestKey: string, cause: CanvasRuntimeRefreshCause) => {
    if (!normalizedDataSourceId) {
      return;
    }

    const silent = isSilentCanvasRuntimeRefresh(cause);
    const gate = beginOwnerRequest({
      silent,
      latestGeneration: fetchIdRef.current,
      inflightCount: inflightCountRef.current,
    });
    if (!isStartedOwnerRequest(gate)) {
      return;
    }
    const currentFetchId = gate.generation;
    fetchIdRef.current = currentFetchId;
    inflightCountRef.current += 1;
    runtimeScheduler?.cancelQueuedForOwner(widgetId);
    const hasSuccessfulPayload =
      rawDataRef.current !== null && rawDataRef.current !== undefined;
    const causePriority = isSilentCanvasRuntimeRefresh(cause)
      ? 2
      : cause === "initial"
        ? 1
        : 0;
    const scheduledSourceData = (id: number, params?: unknown) => {
      if (
        !mountedRef.current
        || currentFetchId !== fetchIdRef.current
        || !runtimeActiveRef.current
      ) {
        return Promise.reject(new RuntimeRequestCancelledError());
      }
      if (!runtimeScheduler) {
        return getRuntimeSourceDataByApiId(id, params);
      }
      const consumerId = `${widgetId}:${currentFetchId}:${++physicalConsumerSequenceRef.current}`;
      return runtimeScheduler.schedule({
        consumerId,
        ownerId: widgetId,
        physicalKey: `${requestKey}:source:${id}:${JSON.stringify(params ?? {})}`,
        priority: { ...runtimePriority, cause: causePriority },
        start: () => getRuntimeSourceDataByApiId(id, params),
      });
    };

    try {
      if (shouldShowWidgetRuntimeLoading(cause)) {
        if (isTableLikeChart) {
          setTableLoading(true);
        } else {
          setLoading(true);
        }
        setDataValidation(null);
      }

      const data = await fetchCompareData({
        dataSourceId: normalizedDataSourceId,
        getSourceDataByApiId: scheduledSourceData,
        config,
        dataSource,
        extraParams: requestExtraParams,
        unifiedFilterValues,
        filterBindings: config?.filterBindings,
        filterDefinitions,
        resolutionContext: dateRangeResolutionContext,
      });

      // Discard stale response if a newer fetch has started
      if (!mountedRef.current || currentFetchId !== fetchIdRef.current) return;

      setRawData(data.currentData);
      setBaselineData(data.baselineData);

      if (data.warnings?.length) {
        message.warning(data.warnings.join("\n"));
      }

      const validation = validateChartData(data.currentData, chartType);
      setDataValidation(validation);
    } catch (err) {
      if (err instanceof RuntimeRequestCancelledError) {
        if (currentFetchId === fetchIdRef.current) {
          previousRequestRef.current = {
            ...previousRequestRef.current,
            hasRequested: false,
          };
        }
        return;
      }
      if (!mountedRef.current || currentFetchId !== fetchIdRef.current) return;
      console.error("获取数据失败:", err);
      if (
        !shouldKeepWidgetRuntimeDataOnError({
          cause,
          hasSuccessfulPayload,
        })
      ) {
        setRawData(null);
        setBaselineData(null);
        const errorMessage = getRequestErrorMessage(
          err,
          t("dashboard.dataFetchFailed"),
        );
        const errorCode = classifyWidgetQueryError(err);
        setDataValidation({
          isValid: false,
          message: errorMessage,
          ...(errorCode ? { errorCode } : {}),
        });
      }
    } finally {
      inflightCountRef.current = finishOwnerRequest({
        inflightCount: inflightCountRef.current,
      }).inflightCount;
      if (!mountedRef.current || currentFetchId !== fetchIdRef.current) return;
      hasSettledRequestRef.current = true;
      setHasSettledRequest(true);
      if (isTableLikeChart) {
        setTableLoading(false);
      } else {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (runtimeActive) {
      runtimeScheduler?.updateOwnerPriority(widgetId, runtimePriority);
      return;
    }
    runtimeScheduler?.cancelQueuedForOwner(widgetId);
  }, [runtimeActive, runtimePriority, runtimeScheduler, widgetId]);

  useEffect(() => {
    const lifecycle = ++lifecycleRef.current;
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      queueMicrotask(() => {
        if (lifecycleRef.current === lifecycle) {
          runtimeScheduler?.cancelQueuedForOwner(widgetId);
        }
      });
    };
  }, [runtimeScheduler, widgetId]);

  useEffect(() => {
    if (isSceneWidget) {
      setRawData(null);
      setBaselineData(null);
      setLoading(false);
      setTableLoading(false);
      setDataValidation(null);
      return;
    }

    if (!normalizedDataSourceId) {
      setRawData(null);
      setLoading(false);
      setTableLoading(false);
      setDataValidation(null);
      return;
    }

    if (!dataSource) {
      setRawData(null);
      setLoading(widgetDataSourceState === "loading");
      setTableLoading(false);
      if (widgetDataSourceState === "loading") {
        setDataValidation(null);
      } else {
        setDataValidation((previous) => {
          const next = {
            isValid: false as const,
            message: t("dashboard.dataFetchFailed"),
            errorCode: "datasource_missing" as const,
          };
          return previous?.isValid === next.isValid
            && previous.message === next.message
            && previous.errorCode === next.errorCode
            ? previous
            : next;
        });
      }
      return;
    }

    if (dataSource?.hasAuth === false) {
      setRawData(null);
      setLoading(false);
      setTableLoading(false);
      setDataValidation((previous) => {
        const next = {
          isValid: false as const,
          message: t("common.noAuth"),
          errorCode: "widget_data_forbidden" as const,
        };
        return previous?.isValid === next.isValid
          && previous.message === next.message
          && previous.errorCode === next.errorCode
          ? previous
          : next;
      });
      return;
    }

    if (componentSwitchRequestGate === "blocked") {
      setRawData(null);
      setBaselineData(null);
      setLoading(false);
      setTableLoading(false);
      hasSettledRequestRef.current = true;
      setHasSettledRequest(true);
      const optionsLoadErrorMessage =
        optionState.status === "error" ? optionState.errorMessage : undefined;
      if (optionsLoadErrorMessage) {
        setDataValidation((previous) => {
          if (
            previous
            && previous.isValid === false
            && previous.message === optionsLoadErrorMessage
            && previous.errorCode === undefined
          ) {
            return previous;
          }
          return { isValid: false, message: optionsLoadErrorMessage };
        });
        return;
      }
      setDataValidation((previous) => (
        previous?.isValid === true && previous.message === undefined
          ? previous
          : { isValid: true }
      ));
    }
  }, [
    isSceneWidget,
    normalizedDataSourceId,
    dataSource,
    dataSource?.hasAuth,
    widgetDataSourceState,
    componentSwitchRequestGate,
    optionState.status,
    optionState.status === "error" ? optionState.errorMessage : undefined,
    t,
  ]);

  const previousRequestRef = useRef(
    createWidgetRequestHistory({
      requestEnabled: false,
      requestSignature: null,
      hasRequestParams: false,
      hasRequestKey: false,
      filterSearchVersion,
      namespaceSearchVersion,
      reloadVersion,
      tableQueryKey,
      hasEnabledFilterBindings: false,
      widgetUsesNamespace: false,
      isTableLikeChart: false,
    }),
  );

  useEffect(() => {
    if (!runtimeActive) {
      return;
    }
    const current = {
      requestEnabled,
      requestSignature,
      hasRequestParams: Boolean(requestParams),
      hasRequestKey: Boolean(requestKey),
      filterSearchVersion,
      namespaceSearchVersion,
      reloadVersion,
      tableQueryKey,
      hasEnabledFilterBindings,
      widgetUsesNamespace,
      isTableLikeChart,
    };
    const history = previousRequestRef.current;
    const decision = decideWidgetRequest({
      history,
      current,
    });
    previousRequestRef.current = decision.nextHistory;

    if (!decision.shouldFetch || !requestKey) {
      return;
    }

    const cause = resolveWidgetFetchCause({
      hasRequested: history.hasRequested,
      filterSearchChanged:
        history.filterSearchVersion !== current.filterSearchVersion &&
        current.hasEnabledFilterBindings,
      namespaceSearchChanged:
        history.namespaceSearchVersion !== current.namespaceSearchVersion &&
        current.widgetUsesNamespace,
      signatureChanged: history.signature !== current.requestSignature,
      reloadVersionChanged: history.reloadVersion !== current.reloadVersion,
      tableQueryChanged: history.tableQueryKey !== current.tableQueryKey,
      reloadCause: refreshCause,
    });
    fetchDataRef.current(requestKey, cause);
  }, [
    requestEnabled,
    requestKey,
    requestSignature,
    requestParams,
    filterSearchVersion,
    namespaceSearchVersion,
    reloadVersion,
    refreshCause,
    tableQueryKey,
    chartType,
    isTableLikeChart,
    hasEnabledFilterBindings,
    widgetUsesNamespace,
    runtimeActive,
  ]);

  const renderError = (message: string) => (
    <WidgetErrorState message={message} />
  );
  const handleRendererReady = useCallback(
    (hasData?: boolean) => {
      onReady?.(hasData);
      if (isTableLikeChart ? tableLoading : loading) {
        onRenderStatus?.({ widgetId, status: "loading" });
        return;
      }
      if (requestEnabled && !hasSettledRequest) {
        onRenderStatus?.({ widgetId, status: "loading" });
        return;
      }
      if (!hasData && hasRenderableChartData(chartType, rawData, config)) {
        onRenderStatus?.({ widgetId, status: "loading" });
        return;
      }
      onRenderStatus?.({
        widgetId,
        status: hasData ? "ready" : "empty",
      });
    },
    [
      hasSettledRequest,
      chartType,
      config,
      isTableLikeChart,
      loading,
      onReady,
      onRenderStatus,
      rawData,
      requestEnabled,
      tableLoading,
      widgetId,
    ],
  );
  const handleRendererError = useCallback(
    (message: string) => {
      onRenderStatus?.({ widgetId, status: "failed", error: message });
    },
    [onRenderStatus, widgetId],
  );
  const hasRawPayload = rawData !== null && rawData !== undefined;
  const hasActiveRuntimeControl =
    hasActiveWidgetRuntimeParams(chartType, runtimeParams);
  const isWaitingForInitialData = shouldWaitForInitialWidgetData({
    isSceneWidget,
    isTableLikeChart,
    hasDataSourceId: Boolean(normalizedDataSourceId),
    hasResolvedDataSource: Boolean(dataSource),
    dataSourceLookupLoading: widgetDataSourceState === "loading",
    hasRawPayload,
    hasDataValidation: Boolean(dataValidation),
    requestEnabled,
    hasRequested: previousRequestRef.current.hasRequested,
  });
  const isWaitingForSwitchOptions = componentSwitchRequestGate === "pending";
  const isInitialNonTableLoading =
    shouldShowInitialWidgetLoading({
      loading,
      isTableLikeChart,
      hasRawPayload,
      hasSettledRequest,
    });

  useEffect(() => {
    if (
      isInitialNonTableLoading
      || isWaitingForInitialData
      || isWaitingForSwitchOptions
      || (isTableLikeChart && tableLoading)
    ) {
      onRenderStatus?.({ widgetId, status: "loading" });
      return;
    }

    if (isEmptyComponentSwitch) {
      onRenderStatus?.({ widgetId, status: "empty" });
      return;
    }

    if (dataValidation && !dataValidation.isValid && !hasActiveRuntimeControl) {
      onRenderStatus?.({
        widgetId,
        status: "failed",
        error:
          dataValidation.message || t("dashboard.dataCannotRenderAsChart"),
        ...(dataValidation.errorCode
          ? { errorCode: dataValidation.errorCode }
          : {}),
      });
    }
  }, [
    dataValidation,
    hasActiveRuntimeControl,
    isEmptyComponentSwitch,
    isInitialNonTableLoading,
    isTableLikeChart,
    isWaitingForInitialData,
    isWaitingForSwitchOptions,
    onRenderStatus,
    t,
    tableLoading,
    widgetId,
  ]);

  let body: React.ReactNode;
  if (isSceneWidget) {
    body = (
      <div
        style={{
          position: "relative",
          height: "100%",
        }}
      >
        <WidgetRenderer
          chartType={chartType}
          rawData={null}
          loading={false}
          config={config}
          refreshKey={reloadVersion}
          refreshCause={refreshCause}
          screenRenderContext={screenRenderContext}
          onReady={handleRendererReady}
          onError={handleRendererError}
          layoutEditable={layoutEditable}
          onTopologyLayoutChange={onTopologyLayoutChange}
          runtimeOwnerId={widgetId}
          runtimeActive={runtimeActive}
          runtimePriority={runtimePriority}
          surface={surface}
          fallback={renderError(
            `${t("dashboard.unknownComponentType")}: ${chartType}`,
          )}
        />
      </div>
    );
  } else if (isInitialNonTableLoading || isWaitingForInitialData || isWaitingForSwitchOptions) {
    body = (
      <div className="h-full flex items-center justify-center">
        <Spin spinning />
      </div>
    );
  } else if (widgetDataSourceState === "data-source-load-error") {
    body = renderError(t("dashboard.dataSourceLoadFailed"));
  } else if (widgetDataSourceState === "data-source-not-found") {
    body = renderError(t("dashboard.dataSourceNotFound"));
  } else if (isEmptyComponentSwitch) {
    body = <WidgetState kind="empty" description={t("dashboard.noData")} />;
  } else if (
    dataValidation &&
    !dataValidation.isValid &&
    !hasActiveRuntimeControl
  ) {
    body = renderError(
      dataValidation.message || t("dashboard.dataCannotRenderAsChart"),
    );
  } else {
    body = (
      <div
        style={{
          position: "relative",
          height: "100%",
        }}
      >
        <WidgetRenderer
          chartType={chartType}
          rawData={rawData}
          baselineData={baselineData}
          loading={isTableLikeChart ? tableLoading : loading}
          config={config}
          refreshKey={reloadVersion}
          refreshCause={refreshCause}
          dataSource={dataSource}
          screenRenderContext={screenRenderContext}
          onReady={handleRendererReady}
          onError={handleRendererError}
          onQueryChange={isTableLikeChart ? handleTableQueryChange : undefined}
          componentSwitchControl={inlineComponentSwitchControl}
          errorMessage={
            hasActiveRuntimeControl && dataValidation && !dataValidation.isValid
              ? dataValidation.message || t("dashboard.dataCannotRenderAsChart")
              : undefined
          }
          runtimeOwnerId={widgetId}
          runtimeActive={runtimeActive}
          runtimePriority={runtimePriority}
          surface={surface}
          fallback={renderError(
            `${t("dashboard.unknownComponentType")}: ${chartType}`,
          )}
        />
      </div>
    );
  }

  return (
    <ScreenWidgetThemeProvider mode={config?.chartThemeMode}>
      {runtimeHeaderControl}
      {body}
    </ScreenWidgetThemeProvider>
  );
};

export default React.memo(WidgetWrapper);
