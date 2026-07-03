import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  FilterValue,
  ScreenRenderContext,
  UnifiedFilterDefinition,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import {
  buildWidgetRequestParams,
  buildWidgetRequestSignatureParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import { fetchCompareData } from '@/app/ops-analysis/utils/compareQuery';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { getRequestErrorMessage } from '@/app/ops-analysis/utils/requestError';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import {
  getCachedWidgetRequest,
  setWidgetRequestFailureCache,
  setWidgetRequestSuccessCache,
} from '@/app/ops-analysis/utils/widgetRequestCache';
import { buildWidgetRequestVersionKey } from '@/app/ops-analysis/utils/widgetRequestVersion';
import WidgetRenderer from '@/app/ops-analysis/components/widgetRenderer';
import WidgetErrorState from '@/app/ops-analysis/components/widgetErrorState';

const validateTopNData = (
  data: unknown,
  config?: ValueConfig,
  errorMessage?: string,
): { isValid: boolean; message?: string } => {
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return { isValid: true };
  }

  if (!Array.isArray(data)) {
    return { isValid: false, message: errorMessage || '数据格式不匹配' };
  }

  const labelField = config?.topNLabelField;
  const valueField = config?.topNValueField;

  const hasValidData = data.some((item) => {
    if (Array.isArray(item) && item.length >= 2) {
      const rawName = getValueByPath(item, labelField);
      const rawValue = getValueByPath(item, valueField);
      const name =
        rawName === undefined || rawName === null ? '' : String(rawName).trim();
      const value = Number(rawValue);
      return !!name && !Number.isNaN(value);
    }

    if (!item || typeof item !== 'object') {
      return false;
    }

    const rawName = getValueByPath(item, labelField);
    const rawValue = getValueByPath(item, valueField);

    const name = rawName === undefined || rawName === null ? '' : String(rawName).trim();
    const value = Number(rawValue);
    return !!name && !Number.isNaN(value);
  });

  return hasValidData
    ? { isValid: true }
    : { isValid: false, message: errorMessage || '数据格式不匹配' };
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
    '数据结构不符：仪表盘期望 number，或包含数值字段的对象/数组（可通过“展示字段”指定）';

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
    if (selectedField && firstItem && typeof firstItem === 'object') {
      return hasNumericValue(getValueByPath(firstItem, selectedField))
        ? { isValid: true }
        : { isValid: false, message: failMessage };
    }

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
    '数据结构不符：事件表期望数组，或包含 items 数组的分页结构';

  const list = Array.isArray(data)
    ? data
    : data &&
        typeof data === 'object' &&
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
    return Boolean(item) && typeof item === 'object';
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
  widgetId,
  chartType,
  config,
  onReady,
  dataSource,
  unifiedFilterValues,
  filterDefinitions,
  filterSearchVersion = 0,
  namespaceSearchVersion = 0,
  reloadVersion = '0:0',
  builtinNamespaceId,
  screenRenderContext,
}) => {
  const { t } = useTranslation();
  const [rawData, setRawData] = useState<any>(null);
  const [baselineData, setBaselineData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [dataValidation, setDataValidation] = useState<{
    isValid: boolean;
    message?: string;
  } | null>(null);
  const [tableQueryParams, setTableQueryParams] = useState<Record<string, any>>(
    { page: 1, page_size: 20 },
  );
  const { getSourceDataByApiId } = useDataSourceApi();
  const isSceneWidget = config?.sceneWidgetType === 'networkStatusTopology';

  const fetchIdRef = useRef(0);
  const tableQueryKey = useMemo(
    () => JSON.stringify(tableQueryParams),
    [tableQueryParams],
  );
  const normalizedDataSourceId = useMemo(() => {
    if (typeof config?.dataSource === 'string') {
      return parseInt(config.dataSource, 10);
    }
    return config?.dataSource;
  }, [config?.dataSource]);
  const isTableLikeChart = chartType === 'table' || chartType === 'eventTable';
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

  const requestParams = useMemo(() => {
    if (!requestEnabled) {
      return null;
    }

    return buildWidgetRequestParams({
      config,
      dataSource,
      extraParams: {
        ...(widgetUsesNamespace && effectiveNamespaceId !== undefined
          ? { namespace_id: effectiveNamespaceId }
          : {}),
        ...(isTableLikeChart ? tableQueryParams : {}),
      },
      unifiedFilterValues,
      filterBindings: config?.filterBindings,
      filterDefinitions,
    });
  }, [
    requestEnabled,
    config,
    dataSource,
    widgetUsesNamespace,
    effectiveNamespaceId,
    isTableLikeChart,
    tableQueryParams,
    unifiedFilterValues,
    filterDefinitions,
  ]);

  const requestSignatureParams = useMemo(() => {
    if (!requestEnabled) {
      return null;
    }

    return buildWidgetRequestSignatureParams({
      config,
      dataSource,
      extraParams: {
        ...(widgetUsesNamespace && effectiveNamespaceId !== undefined
          ? { namespace_id: effectiveNamespaceId }
          : {}),
        ...(isTableLikeChart ? tableQueryParams : {}),
      },
      unifiedFilterValues,
      filterBindings: config?.filterBindings,
      filterDefinitions,
    });
  }, [
    requestEnabled,
    config,
    dataSource,
    widgetUsesNamespace,
    effectiveNamespaceId,
    isTableLikeChart,
    tableQueryParams,
    unifiedFilterValues,
    filterDefinitions,
  ]);

  const requestSignature = useMemo(() => {
    if (isSceneWidget || !normalizedDataSourceId || !requestSignatureParams) {
      return null;
    }

    return JSON.stringify({
      dataSourceId: normalizedDataSourceId,
      requestParams: requestSignatureParams,
    });
  }, [isSceneWidget, normalizedDataSourceId, requestSignatureParams]);

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

    return `${dashboardId ?? 'dashboard'}:${widgetId}:${requestVersionKey}:${requestSignature}`;
  }, [dashboardId, requestSignature, requestVersionKey, widgetId]);

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

      const errorMessage = t('dashboard.dataFormatMismatch');
      switch (type) {
        case 'pie':
          return ChartDataTransformer.validatePieData(data, errorMessage);
        case 'line':
        case 'bar':
          return ChartDataTransformer.validateLineBarData(data, errorMessage);
        case 'topN':
          return validateTopNData(data, config, errorMessage);
        case 'gauge':
          return validateGaugeData(data, config);
        case 'eventTable':
          return validateEventTableData(data);
        case 'table':
          return { isValid: true };
        default:
          return { isValid: true };
      }
    },
    [config, t],
  );

  const fetchDataRef = useRef<
    (key: string) => Promise<void>
      >(undefined!);
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
          extraParams: {
            ...(widgetUsesNamespace && effectiveNamespaceId !== undefined
              ? { namespace_id: effectiveNamespaceId }
              : {}),
            ...(chartType === 'table' ? tableQueryParams : {}),
          },
          unifiedFilterValues,
          filterBindings: config?.filterBindings,
          filterDefinitions,
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
        dataValidation: validation,
      });
    } catch (err) {
      if (currentFetchId !== fetchIdRef.current) return;
      console.error('获取数据失败:', err);
      setRawData(null);
      setBaselineData(null);
      const message = getRequestErrorMessage(
        err,
        t('dashboard.dataFetchFailed'),
      );
      setDataValidation({
        isValid: false,
        message,
      });
      setWidgetRequestFailureCache(requestKey, message);
    } finally {
      if (currentFetchId !== fetchIdRef.current) return;
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
        message: t('common.noAuth'),
      });
      return;
    }
  }, [isSceneWidget, normalizedDataSourceId, dataSource, dataSource?.hasAuth, t]);

  const previousRequestRef = useRef<{
    signature: string | null;
    filterSearchVersion: number;
    namespaceSearchVersion: number;
    reloadVersion: string;
    tableQueryKey: string;
    hasRequested: boolean;
  }>({
    signature: null,
    filterSearchVersion,
    namespaceSearchVersion,
    reloadVersion,
    tableQueryKey,
    hasRequested: false,
  });

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
    setDataValidation(cached.dataValidation);
    setLoading(false);
    setTableLoading(false);
    previousRequestRef.current = {
      signature: requestSignature,
      filterSearchVersion,
      namespaceSearchVersion,
      reloadVersion,
      tableQueryKey,
      hasRequested: true,
    };
  }, [
    dashboardId,
    filterSearchVersion,
    namespaceSearchVersion,
    reloadVersion,
    requestEnabled,
    requestKey,
    requestSignature,
    tableQueryKey,
  ]);

  useEffect(() => {
    const previousRequest = previousRequestRef.current;
    const signatureChanged = previousRequest.signature !== requestSignature;
    const filterSearchChanged =
      previousRequest.filterSearchVersion !== filterSearchVersion;
    const namespaceSearchChanged =
      previousRequest.namespaceSearchVersion !== namespaceSearchVersion;
    const reloadChanged = previousRequest.reloadVersion !== reloadVersion;
    const tableQueryChanged = previousRequest.tableQueryKey !== tableQueryKey;
    const isInitialRequest = !previousRequest.hasRequested;
    const shouldFetchForFilterSearch =
      filterSearchChanged && hasEnabledFilterBindings;
    const shouldFetchForNamespaceSearch =
      namespaceSearchChanged && widgetUsesNamespace;
    const shouldFetchForTableQuery = isTableLikeChart && tableQueryChanged;

    if (!requestEnabled || !requestSignature || !requestParams || !requestKey) {
      previousRequestRef.current = {
        signature: requestSignature,
        filterSearchVersion,
        namespaceSearchVersion,
        reloadVersion,
        tableQueryKey,
        hasRequested: false,
      };
      return;
    }

    const shouldFetch =
      isInitialRequest ||
      signatureChanged ||
      reloadChanged ||
      shouldFetchForFilterSearch ||
      shouldFetchForNamespaceSearch ||
      shouldFetchForTableQuery;

    previousRequestRef.current = {
      signature: requestSignature,
      filterSearchVersion,
      namespaceSearchVersion,
      reloadVersion,
      tableQueryKey,
      hasRequested: previousRequest.hasRequested || shouldFetch,
    };

    if (!shouldFetch) {
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

  if (isSceneWidget) {
    return (
      <div style={{ position: 'relative', height: '100%' }}>
        <WidgetRenderer
          chartType={chartType}
          rawData={null}
          loading={false}
          config={config}
          refreshKey={reloadVersion}
          screenRenderContext={screenRenderContext}
          onReady={onReady}
          fallback={renderError(
            `${t('dashboard.unknownComponentType')}: ${chartType}`,
          )}
        />
      </div>
    );
  }

  if (loading && !isTableLikeChart) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin spinning={loading} />
      </div>
    );
  }

  // 如果数据校验失败，显示错误提示
  if (dataValidation && !dataValidation.isValid) {
    return renderError(
      dataValidation.message || t('dashboard.dataCannotRenderAsChart'),
    );
  }

  return (
    <div style={{ position: 'relative', height: '100%' }}>
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
        fallback={renderError(
          `${t('dashboard.unknownComponentType')}: ${chartType}`,
        )}
      />
    </div>
  );
};

export default React.memo(WidgetWrapper);
