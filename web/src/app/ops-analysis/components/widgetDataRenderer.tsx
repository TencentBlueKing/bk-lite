import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { createPortal } from "react-dom";
import { Spin } from "antd";
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
  resolveComponentSwitchRuntime,
} from "@/app/ops-analysis/utils/componentParamSwitch";
import { useParamInputOptions } from "@/app/ops-analysis/hooks/useParamInputOptions";
import { fetchCompareData } from "@/app/ops-analysis/utils/compareQuery";
import { useDataSourceApi } from "@/app/ops-analysis/api/dataSource";
import { ChartDataTransformer } from "@/app/ops-analysis/utils/chartDataTransform";
import { getRequestErrorMessage } from "@/app/ops-analysis/utils/requestError";
import { getValueByPath } from "@/app/ops-analysis/utils/objectPath";
import {
  buildWidgetRequestCacheKey,
  getCachedWidgetRequest,
  setWidgetRequestFailureCache,
  setWidgetRequestSuccessCache,
} from "@/app/ops-analysis/utils/widgetRequestCache";
import {
  buildWidgetRequestVersionKey,
  shouldWaitForInitialWidgetData,
} from "@/app/ops-analysis/utils/widgetRequestVersion";
import WidgetRenderer from "@/app/ops-analysis/components/widgetRenderer";
import WidgetErrorState from "@/app/ops-analysis/components/widgetErrorState";
import { useWidgetHeaderRuntimeSlot } from "@/app/ops-analysis/components/widgetHeaderRuntimeSlot";
import ComponentParamSwitchControl from "@/app/ops-analysis/components/componentParamSwitchControl";
import { getDateRangeTimezone } from "@/app/ops-analysis/utils/dateRange";
import { validateMultiValueData } from "@/app/ops-analysis/utils/multiValueData";

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

const inflightWidgetRequests = new Map<string, Promise<unknown>>();
const getOrCreateInflightRequest = async <T,>(
  requestKey: string,
  createRequest: () => Promise<T>,
): Promise<T> => {
  const existingRequest = inflightWidgetRequests.get(requestKey) as
    | Promise<T>
    | undefined;
  if (existingRequest) {
    return existingRequest;
  }

  const requestPromise = createRequest().finally(() => {
    inflightWidgetRequests.delete(requestKey);
  });

  inflightWidgetRequests.set(requestKey, requestPromise as Promise<unknown>);
  return requestPromise;
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
}) => {
  const { t } = useTranslation();
  const headerRuntimeSlot = useWidgetHeaderRuntimeSlot();
  const [rawData, setRawData] = useState<any>(null);
  const [baselineData, setBaselineData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [hasSettledRequest, setHasSettledRequest] = useState(false);
  const hasSettledRequestRef = useRef(false);
  const suppressInitialCacheRequestKeyRef = useRef<string | null>(null);
  const [tableLoading, setTableLoading] = useState(false);
  const [dataValidation, setDataValidation] = useState<{
    isValid: boolean;
    message?: string;
  } | null>(null);
  const [tableQueryParams, setTableQueryParams] = useState<Record<string, any>>(
    { page: 1, page_size: 20 },
  );
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
    () => chartType === "topN" ? findComponentSwitchParams(effectiveComponentParams)[0] : undefined,
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
  const requestEnabled =
    Boolean(normalizedDataSourceId) &&
    Boolean(dataSource) &&
    dataSource?.hasAuth !== false &&
    (!widgetUsesNamespace || effectiveNamespaceId !== undefined);
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
  const requestExtraParams = useMemo(
    () =>
      buildWidgetExtraParams({
        namespaceId: widgetUsesNamespace ? effectiveNamespaceId : undefined,
        isTableLikeChart,
        tableQueryParams,
        runtimeParams,
      }),
    [
      effectiveNamespaceId,
      isTableLikeChart,
      runtimeParams,
      tableQueryParams,
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
      const isDataEmpty = () =>
        !data || (Array.isArray(data) && data.length === 0);

      if (isDataEmpty()) {
        return { isValid: true };
      }

      const errorMessage = t("dashboard.dataFormatMismatch");
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

      const data = await getOrCreateInflightRequest(requestKey, () =>
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

      const validation = validateChartData(data.currentData, chartType);
      setDataValidation(validation);
      setWidgetRequestSuccessCache(requestKey, {
        rawData: data.currentData,
        baselineData: data.baselineData,
      });
    } catch (err) {
      if (currentFetchId !== fetchIdRef.current) return;
      console.error("获取数据失败:", err);
      setRawData(null);
      setBaselineData(null);
      const message = getRequestErrorMessage(
        err,
        t("dashboard.dataFetchFailed"),
      );
      setDataValidation({
        isValid: false,
        message,
      });
      setWidgetRequestFailureCache(requestKey, message);
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
      setLoading(false);
      setTableLoading(false);
      setDataValidation(null);
      return;
    }

    if (dataSource?.hasAuth === false) {
      setRawData(null);
      setLoading(false);
      setTableLoading(false);
      setDataValidation({
        isValid: false,
        message: t("common.noAuth"),
      });
      return;
    }
  }, [
    isSceneWidget,
    normalizedDataSourceId,
    dataSource,
    dataSource?.hasAuth,
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
    if (!requestEnabled || !requestSignature || !requestKey) {
      return;
    }

    const cached = getCachedWidgetRequest(requestKey);

    if (!cached) {
      return;
    }

    setRawData(cached.rawData);
    setBaselineData(cached.baselineData);
    setDataValidation(
      cached.errorMessage
        ? {
          isValid: false,
          message: cached.errorMessage,
        }
        : validateChartData(cached.rawData, chartType),
    );
    setLoading(false);
    setTableLoading(false);
    if (
      !hasSettledRequestRef.current &&
      !previousRequestRef.current.hasRequested
    ) {
      suppressInitialCacheRequestKeyRef.current = requestKey;
    }
    hasSettledRequestRef.current = true;
    setHasSettledRequest(true);
  }, [
    filterSearchVersion,
    namespaceSearchVersion,
    reloadVersion,
    requestEnabled,
    requestKey,
    requestSignature,
    tableQueryKey,
    chartType,
    validateChartData,
  ]);

  useEffect(() => {
    const suppressInitialCacheFetch =
      suppressInitialCacheRequestKeyRef.current === requestKey;
    if (suppressInitialCacheFetch) {
      suppressInitialCacheRequestKeyRef.current = null;
    }
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
      suppressInitialCacheFetch,
    });
    previousRequestRef.current = decision.nextHistory;

    if (!decision.shouldFetch || !requestKey) {
      return;
    }

    fetchDataRef.current(requestKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const hasRawPayload = rawData !== null && rawData !== undefined;
  const hasActiveRuntimeControl =
    hasActiveWidgetRuntimeParams(chartType, runtimeParams);
  const isWaitingForInitialData = shouldWaitForInitialWidgetData({
    isSceneWidget,
    isTableLikeChart,
    hasDataSourceId: Boolean(normalizedDataSourceId),
    hasResolvedDataSource: Boolean(dataSource),
    hasRawPayload,
    hasDataValidation: Boolean(dataValidation),
    requestEnabled,
    hasRequested: previousRequestRef.current.hasRequested,
  });

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
            onReady={onReady}
            fallback={renderError(
              `${t("dashboard.unknownComponentType")}: ${chartType}`,
            )}
          />
        </div>
      </>
    );
  }

  const isInitialNonTableLoading =
    shouldShowInitialWidgetLoading({
      loading,
      isTableLikeChart,
      hasRawPayload,
      hasSettledRequest,
    });
  if (isInitialNonTableLoading || isWaitingForInitialData) {
    return (
      <>
        {runtimeHeaderControl}
        <div className="h-full flex items-center justify-center">
          <Spin spinning />
        </div>
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
          onReady={onReady}
          onQueryChange={isTableLikeChart ? handleTableQueryChange : undefined}
          componentSwitchControl={headerRuntimeSlot ? null : componentSwitchControl}
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
