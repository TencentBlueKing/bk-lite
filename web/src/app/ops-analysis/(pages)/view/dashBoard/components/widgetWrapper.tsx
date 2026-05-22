import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Spin, Tooltip } from 'antd';
import { ExclamationCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  FilterValue,
  UnifiedFilterDefinition,
  BindingValidationResult,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import {
  buildWidgetRequestParams,
  buildWidgetRequestSignatureParams,
} from '../../../../utils/widgetDataTransform';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { datasourceSupportsNamespace } from '@/app/ops-analysis/utils/namespaceFilter';
import { getRequestErrorMessage } from '@/app/ops-analysis/utils/requestError';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import ComPie from '../widgets/comPie';
import ComLine from '../widgets/comLine';
import ComBar from '../widgets/comBar';
import ComTable from '../widgets/comTable';
import ComSingle from '../widgets/comSingle';
import ComTopN from '../widgets/comTopN';

const componentMap: Record<string, React.ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
  single: ComSingle,
  topN: ComTopN,
};

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
      const name = String(item[0] ?? '').trim();
      const value = Number(item[1]);
      return !!name && !Number.isNaN(value);
    }

    if (!item || typeof item !== 'object') {
      return false;
    }

    const rawName = labelField
      ? getValueByPath(item, labelField)
      : ((item as Record<string, unknown>).name ?? (item as Record<string, unknown>).label);
    const rawValue = valueField
      ? getValueByPath(item, valueField)
      : ((item as Record<string, unknown>).value ?? (item as Record<string, unknown>).count);

    const name = rawName === undefined || rawName === null ? '' : String(rawName).trim();
    const value = Number(rawValue);
    return !!name && !Number.isNaN(value);
  });

  return hasValidData
    ? { isValid: true }
    : { isValid: false, message: errorMessage || '数据格式不匹配' };
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

interface WidgetWrapperProps {
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
}

const WidgetWrapper: React.FC<WidgetWrapperProps> = ({
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
}) => {
  const { t } = useTranslation();
  const [rawData, setRawData] = useState<any>(null);
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
  const widgetUsesNamespace = useMemo(
    () =>
      Array.isArray(dataSource?.namespaces) && dataSource.namespaces.length > 0,
    [dataSource?.namespaces],
  );
  const nsSupported = useMemo(
    () => datasourceSupportsNamespace(dataSource, builtinNamespaceId),
    [dataSource, builtinNamespaceId],
  );
  const canFetchInCurrentNamespace = !widgetUsesNamespace || nsSupported;
  const requestEnabled =
    Boolean(normalizedDataSourceId) &&
    dataSource?.hasAuth !== false &&
    (!widgetUsesNamespace || builtinNamespaceId !== undefined) &&
    canFetchInCurrentNamespace;

  const requestParams = useMemo(() => {
    if (!requestEnabled) {
      return null;
    }

    return buildWidgetRequestParams({
      config,
      dataSource,
      extraParams: {
        ...(widgetUsesNamespace && builtinNamespaceId !== undefined
          ? { namespace_id: builtinNamespaceId }
          : {}),
        ...(chartType === 'table' ? tableQueryParams : {}),
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
    builtinNamespaceId,
    chartType,
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
        ...(widgetUsesNamespace && builtinNamespaceId !== undefined
          ? { namespace_id: builtinNamespaceId }
          : {}),
        ...(chartType === 'table' ? tableQueryParams : {}),
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
    builtinNamespaceId,
    chartType,
    tableQueryParams,
    unifiedFilterValues,
    filterDefinitions,
  ]);

  const requestSignature = useMemo(() => {
    if (!normalizedDataSourceId || !requestSignatureParams) {
      return null;
    }

    return JSON.stringify({
      dataSourceId: normalizedDataSourceId,
      requestParams: requestSignatureParams,
    });
  }, [normalizedDataSourceId, requestSignatureParams]);

  const invalidBindings = useMemo((): BindingValidationResult[] => {
    const bindings = config?.filterBindings;
    if (!bindings || !filterDefinitions || !Array.isArray(dataSource?.params)) {
      return [];
    }

    const results: BindingValidationResult[] = [];
    const enabledBindingIds = Object.entries(bindings)
      .filter(([, enabled]) => enabled)
      .map(([filterId]) => filterId);

    for (const filterId of enabledBindingIds) {
      const definition = filterDefinitions.find((d) => d.id === filterId);
      if (!definition) {
        results.push({
          filterId,
          isValid: false,
          reason: 'filter_not_found',
        });
        continue;
      }

      const matchingParams = dataSource.params.filter(
        (p) => p.name === definition.key && p.filterType === 'filter',
      );

      if (matchingParams.length === 0) {
        results.push({
          filterId,
          isValid: false,
          reason: 'param_not_found',
        });
        continue;
      }

      const exactMatch = matchingParams.find((p) => p.type === definition.type);
      if (!exactMatch) {
        results.push({
          filterId,
          isValid: false,
          reason: 'type_mismatch',
        });
      }
    }

    return results;
  }, [config?.filterBindings, filterDefinitions, dataSource?.params]);

  const hasEnabledFilterBindings = useMemo(() => {
    const bindings = config?.filterBindings;
    return Boolean(
      bindings && Object.values(bindings).some((enabled) => enabled),
    );
  }, [config?.filterBindings]);

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
        case 'table':
          return { isValid: true };
        default:
          return { isValid: true };
      }
    },
    [config, t],
  );

  const fetchData = useCallback(
    async (nextRequestParams: Record<string, any>, requestKey: string) => {
      const isTableChart = chartType === 'table';

      if (!normalizedDataSourceId) {
        return;
      }

      const currentFetchId = ++fetchIdRef.current;

      try {
        if (isTableChart) {
          setTableLoading(true);
        } else {
          setLoading(true);
        }
        setDataValidation(null);

        const data = await getOrCreateInflightRequest(requestKey, () =>
          getSourceDataByApiId(normalizedDataSourceId, nextRequestParams),
        );

        // Discard stale response if a newer fetch has started
        if (currentFetchId !== fetchIdRef.current) return;

        setRawData(data);

        const validation = validateChartData(data, chartType);
        setDataValidation(validation);
      } catch (err) {
        if (currentFetchId !== fetchIdRef.current) return;
        console.error('获取数据失败:', err);
        setRawData(null);
        setDataValidation({
          isValid: false,
          message: getRequestErrorMessage(err, t('dashboard.dataFetchFailed')),
        });
      } finally {
        if (currentFetchId !== fetchIdRef.current) return;
        if (isTableChart) {
          setTableLoading(false);
        } else {
          setLoading(false);
        }
      }
    },
    [
      normalizedDataSourceId,
      chartType,
      getSourceDataByApiId,
      validateChartData,
      t,
    ],
  );

  const fetchDataRef = useRef(fetchData);
  fetchDataRef.current = fetchData;

  useEffect(() => {
    if (!normalizedDataSourceId) {
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

    if (!canFetchInCurrentNamespace) {
      setRawData(null);
      setLoading(false);
      setTableLoading(false);
      setDataValidation(null);
    }
  }, [
    normalizedDataSourceId,
    dataSource?.hasAuth,
    canFetchInCurrentNamespace,
    t,
  ]);

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
    const previousRequest = previousRequestRef.current;
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
    const shouldFetchForTableQuery = chartType === 'table' && tableQueryChanged;

    if (!requestEnabled || !requestSignature || !requestParams) {
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

    const requestKey = `${widgetId}:${reloadVersion}:${filterSearchVersion}:${namespaceSearchVersion}:${requestSignature}`;
    fetchDataRef.current(requestParams, requestKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    widgetId,
    requestEnabled,
    requestSignature,
    requestParams,
    filterSearchVersion,
    namespaceSearchVersion,
    reloadVersion,
    tableQueryKey,
    chartType,
    hasEnabledFilterBindings,
    widgetUsesNamespace,
  ]);

  const getInvalidBindingReasonText = (
    reason: BindingValidationResult['reason'],
  ): string => {
    switch (reason) {
      case 'filter_not_found':
        return t('dashboard.bindingInvalidFilterNotFound');
      case 'param_not_found':
        return t('dashboard.bindingInvalidParamNotFound');
      case 'type_mismatch':
        return t('dashboard.bindingInvalidTypeMismatch');
      default:
        return t('dashboard.bindingInvalidUnknown');
    }
  };

  const renderBindingWarning = () => {
    if (invalidBindings.length === 0) {
      return null;
    }

    const tooltipContent = (
      <div>
        <div style={{ fontWeight: 500, marginBottom: 4 }}>
          {t('dashboard.bindingInvalidTitle')}
        </div>
        {invalidBindings.map((binding) => {
          const definition = filterDefinitions?.find(
            (d) => d.id === binding.filterId,
          );
          const name = definition?.name || binding.filterId;
          return (
            <div key={binding.filterId} style={{ fontSize: 12 }}>
              • {name}: {getInvalidBindingReasonText(binding.reason)}
            </div>
          );
        })}
      </div>
    );

    return (
      <Tooltip title={tooltipContent} placement="topRight">
        <div
          style={{
            position: 'absolute',
            top: 4,
            right: 4,
            zIndex: 10,
            cursor: 'pointer',
          }}
        >
          <WarningOutlined style={{ color: '#faad14', fontSize: 16 }} />
        </div>
      </Tooltip>
    );
  };

  const renderError = (message: string) => (
    <div className="h-full flex flex-col items-center justify-center">
      <ExclamationCircleOutlined
        style={{ color: '#faad14', fontSize: '24px', marginBottom: '12px' }}
      />
      <span style={{ fontSize: '14px', color: '#666' }}>{message}</span>
    </div>
  );

  if (loading && chartType !== 'table') {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin spinning={loading} />
      </div>
    );
  }

  const Component = chartType ? componentMap[chartType] : null;
  if (!Component) {
    return renderError(`${t('dashboard.unknownComponentType')}: ${chartType}`);
  }

  // 如果数据校验失败，显示错误提示
  if (dataValidation && !dataValidation.isValid) {
    return renderError(
      dataValidation.message || t('dashboard.dataCannotRenderAsChart'),
    );
  }

  if (builtinNamespaceId !== undefined && !nsSupported) {
    return renderError(t('dashboard.namespaceNotSupported'));
  }

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      {renderBindingWarning()}
      <Component
        rawData={rawData}
        loading={chartType === 'table' ? tableLoading : loading}
        config={config}
        dataSource={dataSource}
        onReady={onReady}
        onQueryChange={
          chartType === 'table' ? handleTableQueryChange : undefined
        }
      />
    </div>
  );
};

export default React.memo(WidgetWrapper);
