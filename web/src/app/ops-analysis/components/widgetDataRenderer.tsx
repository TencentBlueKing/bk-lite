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
  findComponentSwitchParams,
  getTypedValueKey,
  reconcileComponentSwitchValue,
  resolveComponentSwitchRequestGate,
  resolveComponentSwitchRuntime,
  supportsComponentSwitch,
} from "@/app/ops-analysis/utils/componentParamSwitch";
import { useParamInputOptions } from "@/app/ops-analysis/hooks/useParamInputOptions";
import { fetchCompareData } from "@/app/ops-analysis/utils/compareQuery";
import { useDataSourceApi } from "@/app/ops-analysis/api/dataSource";
import { ChartDataTransformer } from "@/app/ops-analysis/utils/chartDataTransform";
import { getRequestErrorMessage, classifyWidgetQueryError } from "@/app/ops-analysis/utils/requestError";
import { getValueByPath } from "@/app/ops-analysis/utils/objectPath";
import {
  buildWidgetRequestCacheKey,
  getOrCreateInflightWidgetRequest,
} from "@/app/ops-analysis/utils/widgetRequestCache";
import {
  buildWidgetRequestVersionKey,
  resolveWidgetDataSourceState,
  shouldWaitForInitialWidgetData,
} from "@/app/ops-analysis/utils/widgetRequestVersion";
import WidgetRenderer from "@/app/ops-analysis/components/widgetRenderer";
import WidgetErrorState from "@/app/ops-analysis/components/widgetErrorState";
import { useWidgetHeaderRuntimeSlot } from "@/app/ops-analysis/components/widgetHeaderRuntimeSlot";
import ComponentParamSwitchControl from "@/app/ops-analysis/components/componentParamSwitchControl";
import { getDateRangeTimezone } from "@/app/ops-analysis/utils/dateRange";
import { validateMultiValueData } from "@/app/ops-analysis/utils/multiValueData";
import { validateEventTimelinePayload } from "@/app/ops-analysis/utils/eventTimeline";
import { resolveRadarSeriesData } from "@/app/ops-analysis/utils/radarData";
import { useOpsAnalysis } from "@/app/ops-analysis/context/common";
import type { DashboardWidgetRenderResult } from "@/app/ops-analysis/renderContract";
import {
  hasRenderableChartData,
  validateTopologyMapWidgetData,
} from "@/app/ops-analysis/utils/topologyMapWidgetContract";

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
  builtinNamespaceId?: number;
  screenRenderContext?: ScreenRenderContext;
  onRenderStatus?: (result: DashboardWidgetRenderResult) => void;
  layoutEditable?: boolean;
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
  builtinNamespaceId,
  screenRenderContext,
  widgetId,
  onRenderStatus,
  layoutEditable,
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
  const { canvasDataSourceLookupStatus } = useOpsAnalysis();
  const { getSourceDataByApiId } = useDataSourceApi();
  const isSceneWidget = config?.sceneWidgetType === "networkStatusTopology";
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
  const optionState = useParamInputOptions(componentSwitchParam?.inputConfig);
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
    [optionState, savedComponentSwitchValue],
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
  }, [optionState, runtimeParamInitialValue, runtimeParamScopeKey]);

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
  const tableQueryKey = useMemo(
    () => JSON.stringify(tableQueryParams),
    [tableQueryParams],
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
      optionState,
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
      const same = JSON.stringify(prev) === JSON.stringify(next);
      return same ? prev : next;
    });
  }, []);

  const validateChartData = useCallback(
    (data: unknown, type?: string) => {
      const errorMessage = t("dashboard.dataFormatMismatch");
      if (type === "topologyMap") {
        return validateTopologyMapWidgetData(data, errorMessage);
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

  const fetchDataRef = useRef<(key: string) => Promise<void>>(undefined!);
  fetchDataRef.current = async (requestKey: string) => {
    if (!normalizedDataSourceId) {
      return;
    }

    const currentFetchId = ++fetchIdRef.current;

    try {
      if (isTableLikeChart) {
        setTableLoading(true);
      } else {
        setLoading(true);
      }
      setDataValidation(null);

      const data = await getOrCreateInflightWidgetRequest(requestKey, () =>
        fetchCompareData({
          dataSourceId: normalizedDataSourceId,
          getSourceDataByApiId,
          config,
          dataSource,
          extraParams: requestExtraParams,
          unifiedFilterValues,
          filterBindings: config?.filterBindings,
          filterDefinitions,
          resolutionContext: dateRangeResolutionContext,
        }),
      );

      // Discard stale response if a newer fetch has started
      if (currentFetchId !== fetchIdRef.current) return;

      setRawData(data.currentData);
      setBaselineData(data.baselineData);

      if (data.warnings?.length) {
        message.warning(data.warnings.join("\n"));
      }

      const validation = validateChartData(data.currentData, chartType);
      setDataValidation(validation);
    } catch (err) {
      if (currentFetchId !== fetchIdRef.current) return;
      console.error("获取数据失败:", err);
      setRawData(null);
      setBaselineData(null);
      const message = getRequestErrorMessage(
        err,
        t("dashboard.dataFetchFailed"),
      );
      const errorCode = classifyWidgetQueryError(err);
      setDataValidation({
        isValid: false,
        message,
        ...(errorCode ? { errorCode } : {}),
      });
    } finally {
      if (currentFetchId !== fetchIdRef.current) return;
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
        setDataValidation({
          isValid: false,
          message: t("dashboard.dataFetchFailed"),
          errorCode: "datasource_missing",
        });
      }
      return;
    }

    if (dataSource?.hasAuth === false) {
      setRawData(null);
      setLoading(false);
      setTableLoading(false);
      setDataValidation({
        isValid: false,
        message: t("common.noAuth"),
        errorCode: "widget_data_forbidden",
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
      setDataValidation({
        isValid: false,
        message: t("dashboard.noData"),
      });
    }
  }, [
    isSceneWidget,
    normalizedDataSourceId,
    dataSource,
    dataSource?.hasAuth,
    widgetDataSourceState,
    componentSwitchRequestGate,
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
    const decision = decideWidgetRequest({
      history: previousRequestRef.current,
      current: {
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
      },
    });
    previousRequestRef.current = decision.nextHistory;

    if (!decision.shouldFetch || !requestKey) {
      return;
    }

    fetchDataRef.current(requestKey);
  }, [
    requestEnabled,
    requestKey,
    requestSignature,
    requestParams,
    filterSearchVersion,
    namespaceSearchVersion,
    reloadVersion,
    tableQueryKey,
    chartType,
    isTableLikeChart,
    hasEnabledFilterBindings,
    widgetUsesNamespace,
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
      if (!hasData && hasRenderableChartData(chartType, rawData)) {
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
    if (isInitialNonTableLoading || isWaitingForInitialData || isWaitingForSwitchOptions) {
      onRenderStatus?.({ widgetId, status: "loading" });
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
    isInitialNonTableLoading,
    isWaitingForInitialData,
    isWaitingForSwitchOptions,
    onRenderStatus,
    t,
    widgetId,
  ]);

  if (isSceneWidget) {
    return (
      <>
        {runtimeHeaderControl}
        <div style={{ position: "relative", height: "100%" }}>
          <WidgetRenderer
            chartType={chartType}
            rawData={null}
            loading={false}
            config={config}
            refreshKey={reloadVersion}
            screenRenderContext={screenRenderContext}
            onReady={handleRendererReady}
            onError={handleRendererError}
            layoutEditable={layoutEditable}
            onTopologyLayoutChange={onTopologyLayoutChange}
            fallback={renderError(
              `${t("dashboard.unknownComponentType")}: ${chartType}`,
            )}
          />
        </div>
      </>
    );
  }

  if (isInitialNonTableLoading || isWaitingForInitialData || isWaitingForSwitchOptions) {
    return (
      <>
        {runtimeHeaderControl}
        <div className="h-full flex items-center justify-center">
          <Spin spinning />
        </div>
      </>
    );
  }

  if (widgetDataSourceState === "data-source-load-error") {
    return (
      <>
        {runtimeHeaderControl}
        {renderError(t("dashboard.dataSourceLoadFailed"))}
      </>
    );
  }

  if (widgetDataSourceState === "data-source-not-found") {
    return (
      <>
        {runtimeHeaderControl}
        {renderError(t("dashboard.dataSourceNotFound"))}
      </>
    );
  }

  // 如果数据校验失败，显示错误提示
  if (
    dataValidation &&
    !dataValidation.isValid &&
    !hasActiveRuntimeControl
  ) {
    return (
      <>
        {runtimeHeaderControl}
        {renderError(
          dataValidation.message || t("dashboard.dataCannotRenderAsChart"),
        )}
      </>
    );
  }

  return (
    <>
      {runtimeHeaderControl}
      <div style={{ position: "relative", height: "100%" }}>
        <WidgetRenderer
          chartType={chartType}
          rawData={rawData}
          baselineData={baselineData}
          loading={isTableLikeChart ? tableLoading : loading}
          config={config}
          refreshKey={reloadVersion}
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
          fallback={renderError(
            `${t("dashboard.unknownComponentType")}: ${chartType}`,
          )}
        />
      </div>
    </>
  );
};

export default React.memo(WidgetWrapper);
