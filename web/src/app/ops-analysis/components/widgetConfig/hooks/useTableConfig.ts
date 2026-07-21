import { useState, useCallback } from 'react';
import { message } from 'antd';
import type { FormInstance } from 'antd';
import type {
  TableFilterFieldConfig,
  TableColumnConfigItem,
  FilterBindings,
  UnifiedFilterDefinition,
  FilterValue,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import {
  formatTimeRange,
  processDataSourceParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import {
  DisplayColumnRow,
  buildDisplayColumnsFromSchema,
  extractFirstRecordFromSourceData,
  mergeDetectedFieldsWithSchema,
  createDefaultDisplayColumn as createDefaultColumn,
} from '../utils/columnProbing';
import { createOperationColumnKey } from '@/app/ops-analysis/utils/dashboardActions';

export type FilterFieldRow = TableFilterFieldConfig & { id: string };

interface UseTableConfigProps {
  form: FormInstance;
  chartType: string;
  selectedDataSource: DatasourceItem | undefined;
  availableFields: import('@/app/ops-analysis/types/dataSource').ResponseFieldDefinition[];
  getSourceDataByApiId: (
    id: number,
    params: Record<string, any>,
  ) => Promise<any>;
  processFormParamsForSubmit: (
    formParams: Record<string, any>,
    sourceParams: ParamItem[],
  ) => ParamItem[];
  unifiedFilterValues?: Record<string, FilterValue>;
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
  builtinNamespaceId?: number;
  t: (key: string) => string;
}

interface FilterFieldOption {
  label: string;
  value: string;
}

export function useTableConfig({
  form,
  chartType,
  selectedDataSource,
  availableFields,
  getSourceDataByApiId,
  processFormParamsForSubmit,
  unifiedFilterValues,
  filterBindings,
  filterDefinitions,
  builtinNamespaceId,
  t,
}: UseTableConfigProps) {
  const isTableLikeChartType =
    chartType === 'table' || chartType === 'eventTable';
  const [filterFields, setFilterFields] = useState<FilterFieldRow[]>([]);
  const [displayColumns, setDisplayColumns] = useState<DisplayColumnRow[]>([]);
  const [detectedDisplayColumns, setDetectedDisplayColumns] = useState<
    DisplayColumnRow[]
  >([]);
  const [isProbingColumns, setIsProbingColumns] = useState(false);
  const [paramsChangedAfterProbe, setParamsChangedAfterProbe] = useState(false);
  const [displayColumnsError, setDisplayColumnsError] = useState('');

  const createDefaultFilterField = useCallback(
    (): FilterFieldRow => ({
      id: `filter_${Date.now()}`,
      key: '',
      label: '',
      inputType: 'keyword',
    }),
    [],
  );

  const createDefaultDisplayColumn = useCallback(
    (): DisplayColumnRow => createDefaultColumn(displayColumns.length),
    [displayColumns.length],
  );

  const createDefaultOperationColumn = useCallback(
    (): DisplayColumnRow => ({
      id: `column_actions_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
      key: createOperationColumnKey(displayColumns),
      title: t('dashboard.operationColumnTitle'),
      visible: true,
      order: displayColumns.length,
      columnType: 'actions',
      isDefault: false,
    }),
    [displayColumns, t],
  );

  const handleAddFilterField = useCallback(
    (index: number) => {
      const newField = createDefaultFilterField();
      const newFields = [...filterFields];
      newFields.splice(index + 1, 0, newField);
      setFilterFields(newFields);
    },
    [filterFields, createDefaultFilterField],
  );

  const handleDeleteFilterField = useCallback(
    (id: string) => {
      setFilterFields((prev) => prev.filter((f) => f.id !== id));
    },
    [],
  );

  const handleFilterFieldChange = useCallback(
    (
      id: string,
      fieldName: keyof TableFilterFieldConfig,
      value: string,
      filterFieldOptions: FilterFieldOption[],
    ) => {
      setFilterFields((prev) =>
        prev.map((f) => {
          if (f.id !== id) return f;
          if (fieldName === 'key') {
            const selectedField = filterFieldOptions.find(
              (option) => option.value === value,
            );
            return {
              ...f,
              key: value,
              label: selectedField?.label || value,
            };
          }
          return { ...f, [fieldName]: value };
        }),
      );
    },
    [],
  );

  const handleAddDisplayColumn = useCallback(
    (index: number) => {
      const newColumn = createDefaultDisplayColumn();
      setDisplayColumns((prev) => {
        const nextColumns = [...prev];
        nextColumns.splice(index + 1, 0, newColumn);
        return nextColumns.map((col, idx) => ({ ...col, order: idx }));
      });
    },
    [createDefaultDisplayColumn],
  );

  const handleDeleteDisplayColumn = useCallback((id: string) => {
    setDisplayColumns((prev) => {
      const nextColumns = prev.filter((col) => col.id !== id);
      return nextColumns.map((col, idx) => ({ ...col, order: idx }));
    });
  }, []);

  const getDisplayColumnTitle = useCallback(
    (key: string) => {
      const normalizedKey = key.trim();
      if (!normalizedKey) return '';

      const matchedField =
        availableFields.find((field) => field.key === normalizedKey) ||
        detectedDisplayColumns.find((column) => column.key === normalizedKey);

      const matchedTitle = (matchedField?.title || '').trim();
      return matchedTitle || normalizedKey;
    },
    [availableFields, detectedDisplayColumns],
  );

  const handleDisplayColumnChange = useCallback(
    (id: string, fieldName: keyof TableColumnConfigItem, value: string | boolean) => {
      setDisplayColumns((prev) =>
        prev.map((col) => {
          if (col.id !== id) return col;
          if (fieldName === 'key' && typeof value === 'string') {
            const nextKey = value;
            const currentTitle = (col.title || '').trim();
            const currentKey = (col.key || '').trim();
            const shouldSyncTitle = !currentTitle || currentTitle === currentKey;

            return {
              ...col,
              key: nextKey,
              title: shouldSyncTitle
                ? getDisplayColumnTitle(nextKey)
                : col.title,
            };
          }
          return { ...col, [fieldName]: value };
        }),
      );
    },
    [getDisplayColumnTitle],
  );

  const handleDisplayColumnKeyBlur = useCallback((id: string) => {
    setDisplayColumns((prev) =>
      prev.map((col) => {
        if (col.id !== id) return col;
        const keyValue = (col.key || '').trim();
        const titleValue = (col.title || '').trim();
        if (!keyValue || titleValue) return col;
        return { ...col, title: getDisplayColumnTitle(keyValue) };
      }),
    );
  }, [getDisplayColumnTitle]);

  const handleDisplayColumnDragEnd = useCallback(
    (targetTableData: DisplayColumnRow[]) => {
      const nextColumns = (targetTableData || []).map((item, idx) => ({
        ...item,
        order: idx,
      }));
      setDisplayColumns(nextColumns);
    },
    [],
  );

  const buildProbeParams = useCallback(
    (
      targetDataSource: DatasourceItem,
      formParams: Record<string, any>,
    ): Record<string, any> => {
      const payload: Record<string, any> = {};
      const sourceParams = targetDataSource.params || [];
      const processedParams = processFormParamsForSubmit(formParams, sourceParams);
      const userParams = processedParams.reduce<Record<string, any>>((acc, param) => {
        acc[param.name] = param.value;
        return acc;
      }, {});

      Object.assign(
        payload,
        processDataSourceParams({
          sourceParams: processedParams,
          userParams,
          unifiedFilterValues,
          filterBindings,
          filterDefinitions,
          timeRangeFormatter: formatTimeRange,
        }),
      );

      if (isTableLikeChartType) {
        payload.page = 1;
        payload.page_size = 20;
      }

      if (
        builtinNamespaceId !== undefined &&
        Array.isArray(targetDataSource.namespaces) &&
        targetDataSource.namespaces.length > 0
      ) {
        payload.namespace_id = builtinNamespaceId;
      }

      return payload;
    },
    [
      isTableLikeChartType,
      processFormParamsForSubmit,
      unifiedFilterValues,
      filterBindings,
      filterDefinitions,
      builtinNamespaceId,
    ],
  );

  const probeDefaultDisplayColumns = useCallback(
    async (
      targetDataSource: DatasourceItem,
      formParams: Record<string, any>,
    ): Promise<DisplayColumnRow[]> => {
      try {
        const payload = buildProbeParams(targetDataSource, formParams);
        const sourceData = await getSourceDataByApiId(targetDataSource.id, payload);
        const firstRecord = extractFirstRecordFromSourceData(sourceData);
        if (!firstRecord) return [];

        const detectedKeys = Object.keys(firstRecord);
        if (detectedKeys.length === 0) return [];

        return mergeDetectedFieldsWithSchema(
          detectedKeys,
          targetDataSource?.field_schema || [],
        );
      } catch (error) {
        console.error('Failed to probe default display columns:', error);
        return [];
      }
    },
    [buildProbeParams, getSourceDataByApiId],
  );

  const handleReProbeColumns = useCallback(async () => {
    if (!selectedDataSource || !isTableLikeChartType) return;

    try {
      setIsProbingColumns(true);
      const currentParams = (form.getFieldValue('params') || {}) as Record<string, any>;
      const probedColumns = await probeDefaultDisplayColumns(
        selectedDataSource,
        currentParams,
      );

      if (probedColumns.length > 0) {
        setDetectedDisplayColumns(probedColumns);
        // 关键:把探测结果写入 displayColumns(实际渲染数组)
        // 同时保留用户自定义列(isDefault !== true 的列),与 tooltip 文案一致
        setDisplayColumns((prev) => {
          const customCols = prev.filter((c) => !c.isDefault);
          const customKeys = new Set(customCols.map((c) => c.key).filter(Boolean));
          const newDefaults = probedColumns.filter((c) => !customKeys.has(c.key));
          return [...customCols, ...newDefaults];
        });
        setParamsChangedAfterProbe(false);
        message.success(t('dashboard.reProbeSuccess'));
        return;
      }

      message.warning(t('dashboard.reProbeNoFields') || '未探测到可用字段');
    } finally {
      setIsProbingColumns(false);
    }
  }, [
    selectedDataSource,
    isTableLikeChartType,
    form,
    probeDefaultDisplayColumns,
    t,
  ]);

  const handleChartTypeChange = useCallback(
    async (newChartType: string) => {
      if (
        (newChartType === 'table' || newChartType === 'eventTable') &&
        selectedDataSource
      ) {
        const currentParams = (form.getFieldValue('params') || {}) as Record<string, any>;
        const schemaColumns = buildDisplayColumnsFromSchema(availableFields);

        if (schemaColumns.length > 0) {
          setDetectedDisplayColumns(schemaColumns);
          return;
        }

        const probedColumns = await probeDefaultDisplayColumns(
          selectedDataSource,
          currentParams,
        );
        setDetectedDisplayColumns(probedColumns);
      }
    },
    [selectedDataSource, form, probeDefaultDisplayColumns, availableFields],
  );

  const resetTableConfig = useCallback(() => {
    setFilterFields([]);
    setDisplayColumns([]);
    setDetectedDisplayColumns([]);
    setIsProbingColumns(false);
    setParamsChangedAfterProbe(false);
    setDisplayColumnsError('');
  }, []);

  return {
    filterFields,
    setFilterFields,
    displayColumns,
    setDisplayColumns,
    detectedDisplayColumns,
    setDetectedDisplayColumns,
    isProbingColumns,
    paramsChangedAfterProbe,
    setParamsChangedAfterProbe,
    displayColumnsError,
    setDisplayColumnsError,
    createDefaultFilterField,
    createDefaultDisplayColumn,
    createDefaultOperationColumn,
    handleAddFilterField,
    handleDeleteFilterField,
    handleFilterFieldChange,
    handleAddDisplayColumn,
    handleDeleteDisplayColumn,
    handleDisplayColumnChange,
    handleDisplayColumnKeyBlur,
    handleDisplayColumnDragEnd,
    handleReProbeColumns,
    handleChartTypeChange,
    probeDefaultDisplayColumns,
    resetTableConfig,
  };
}
