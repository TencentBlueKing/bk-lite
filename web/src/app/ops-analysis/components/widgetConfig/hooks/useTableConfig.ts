import { useState, useCallback, useRef } from 'react';
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
import { getDateRangeTimezone } from '@/app/ops-analysis/utils/dateRange';
import {
  DisplayColumnRow,
  buildDisplayColumnsFromSchema,
  extractFirstRecordFromSourceData,
  mergeDetectedFieldsWithSchema,
  createDefaultDisplayColumn as createDefaultColumn,
} from '../utils/columnProbing';
import {
  columnsFromModelFields,
  isModelAttrTableSource,
  modelTableBindingKey,
  readModelColumnPayload,
} from '@/app/ops-analysis/utils/modelTableColumns';
import { readDeclaredFields } from '@/app/ops-analysis/utils/chartFieldContract';
import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
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
  const [columnModelKey, setColumnModelKey] = useState('');
  const probedModelKeyRef = useRef('');

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
    (
      id: string,
      fieldName: keyof TableColumnConfigItem,
      value: TableColumnConfigItem[keyof TableColumnConfigItem],
    ) => {
      setDisplayColumns((prev) =>
        prev.map((col) => {
          if (col.id !== id) return col;
          if (fieldName === 'key' && typeof value === 'string') {
            const nextKey = value;
            const currentTitle = (col.title || '').trim();
            const currentKey = (col.key || '').trim();
            const shouldSyncTitle = !currentTitle || currentTitle === currentKey;
            const keyChanged = nextKey.trim() !== currentKey;
            const next: DisplayColumnRow = {
              ...col,
              key: nextKey,
              title: shouldSyncTitle
                ? getDisplayColumnTitle(nextKey)
                : col.title,
            };

            if (keyChanged) {
              delete next.cellType;
              delete next.valueMappings;
              delete next.cellThresholdColors;
            }

            return next;
          }
          if (value === undefined) {
            const next = { ...col };
            delete next[fieldName];
            return next;
          }
          return { ...col, [fieldName]: value };
        }),
      );
    },
    [getDisplayColumnTitle],
  );

  const handleDisplayColumnStyleChange = useCallback(
    (
      id: string,
      style: Pick<
        TableColumnConfigItem,
        'cellType' | 'valueMappings' | 'cellThresholdColors'
      >,
    ) => {
      setDisplayColumns((prev) =>
        prev.map((col) => {
          if (col.id !== id) return col;
          const next: DisplayColumnRow = { ...col };
          delete next.cellType;
          delete next.valueMappings;
          delete next.cellThresholdColors;
          if (style.cellType) {
            next.cellType = style.cellType;
          }
          if (style.valueMappings?.length) {
            next.valueMappings = style.valueMappings;
          }
          if (style.cellThresholdColors?.length) {
            next.cellThresholdColors = style.cellThresholdColors;
          }
          return next;
        }),
      );
    },
    [],
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
      chartTypeOverride?: string,
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
          definitionParams: sourceParams,
          userParams,
          unifiedFilterValues,
          filterBindings,
          filterDefinitions,
          timeRangeFormatter: formatTimeRange,
          resolutionContext: {
            referenceNow: Date.now(),
            timezone: getDateRangeTimezone(),
          },
          chartType: chartTypeOverride || chartType,
          t,
        }),
      );

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
      chartType,
      processFormParamsForSubmit,
      unifiedFilterValues,
      filterBindings,
      filterDefinitions,
      builtinNamespaceId,
      t,
    ],
  );

  const probeDefaultDisplayColumns = useCallback(
    async (
      targetDataSource: DatasourceItem,
      formParams: Record<string, any>,
      chartTypeOverride?: string,
    ): Promise<DisplayColumnRow[]> => {
      if (isModelAttrTableSource(targetDataSource.rest_api)) {
        const minimal = buildDisplayColumnsFromSchema(targetDataSource.field_schema || []);
        if (!modelTableBindingKey(targetDataSource.rest_api, formParams)) {
          probedModelKeyRef.current = '';
          return minimal;
        }
        try {
          const payload = buildProbeParams(targetDataSource, formParams, chartTypeOverride);
          const { data: sourceData } = await getSourceDataByApiId(targetDataSource.id, payload);
          const modelColumns = readModelColumnPayload(sourceData);
          if (!modelColumns) {
            probedModelKeyRef.current = '';
            const declared = readDeclaredFields(sourceData) || [];
            const firstRecord = extractFirstRecordFromSourceData(sourceData);
            const detectedKeys = firstRecord
              ? Object.keys(firstRecord)
              : declared.map((field) => field.key);
            if (detectedKeys.length === 0) {
              return minimal;
            }
            const titles: ResponseFieldDefinition[] = [
              ...(targetDataSource.field_schema || []),
              ...declared.map((field) => ({
                key: field.key,
                title: field.title || field.key,
                value_type: (field.value_type as ResponseFieldDefinition['value_type']) || 'string',
              })),
            ];
            return mergeDetectedFieldsWithSchema(detectedKeys, titles);
          }
          probedModelKeyRef.current = modelColumns.model_key;
          return columnsFromModelFields(modelColumns.fields).map((column, index) => ({
            ...column,
            id: `column_model_${index}_${column.key}`,
            isDefault: true,
          }));
        } catch (error) {
          console.error('Failed to probe model attribute columns:', error);
          probedModelKeyRef.current = '';
          return minimal;
        }
      }
      try {
        const payload = buildProbeParams(targetDataSource, formParams, chartTypeOverride);
        const { data: sourceData } = await getSourceDataByApiId(targetDataSource.id, payload);
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
        chartType,
      );

      if (isModelAttrTableSource(selectedDataSource.rest_api)) {
        setColumnModelKey(probedModelKeyRef.current);
        setDetectedDisplayColumns(probedColumns);
        setDisplayColumns(probedColumns.map((column, index) => ({ ...column, order: index })));
        setParamsChangedAfterProbe(false);
        if (probedColumns.length > 0) {
          message.success(t('dashboard.reProbeSuccess'));
        } else {
          message.warning(t('dashboard.reProbeNoFields'));
        }
        return;
      }

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

      message.warning(t('dashboard.reProbeNoFields'));
    } finally {
      setIsProbingColumns(false);
    }
  }, [
    chartType,
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
        if (isModelAttrTableSource(selectedDataSource.rest_api)) {
          const probedColumns = await probeDefaultDisplayColumns(
            selectedDataSource,
            currentParams,
            newChartType,
          );
          const modelKey = probedModelKeyRef.current;
          if (modelTableBindingKey(selectedDataSource.rest_api, currentParams) && !modelKey) {
            return;
          }
          setColumnModelKey(modelKey);
          setDetectedDisplayColumns(probedColumns);
          setDisplayColumns(probedColumns);
          return;
        }
        const schemaColumns = buildDisplayColumnsFromSchema(
          availableFields,
          currentParams?.query_object,
        );

        if (schemaColumns.length > 0) {
          setDetectedDisplayColumns(schemaColumns);
          return;
        }

        const probedColumns = await probeDefaultDisplayColumns(
          selectedDataSource,
          currentParams,
          newChartType,
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
    setColumnModelKey('');
    probedModelKeyRef.current = '';
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
    handleAddFilterField,
    handleDeleteFilterField,
    handleFilterFieldChange,
    handleAddDisplayColumn,
    handleDeleteDisplayColumn,
    handleDisplayColumnChange,
    handleDisplayColumnStyleChange,
    handleDisplayColumnKeyBlur,
    handleDisplayColumnDragEnd,
    handleReProbeColumns,
    handleChartTypeChange,
    probeDefaultDisplayColumns,
    resetTableConfig,
    columnModelKey,
    setColumnModelKey,
    probedModelKeyRef,
  };
}
