import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  ViewConfigProps,
  ViewConfigItem,
  TableConfig,
  UnifiedFilterDefinition,
  FilterBindings,
  ValueConfig,
  FilterValue,
  WidgetConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  Drawer,
  Button,
  Form,
  Input,
  Radio,
  Tooltip,
  message,
} from 'antd';
import { QuestionCircleOutlined, SwapOutlined } from '@ant-design/icons';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useSingleValueConfig } from '@/app/ops-analysis/hooks/useSingleValueConfig';
import {
  getChartTypeList,
  ChartTypeItem,
} from '@/app/ops-analysis/constants/common';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import { SingleValueSettingsSection } from '@/app/ops-analysis/components/singleValueSettingsSection';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  getFilterDefinitionId,
  getBindableFilterParams,
  buildDefaultFilterBindings,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import { canEnableCompare } from '@/app/ops-analysis/utils/compareQuery';
import type {
  DatasourceItem,
  ParamItem,
  ResponseFieldDefinition,
} from '@/app/ops-analysis/types/dataSource';
import { initThresholdColors } from '@/app/ops-analysis/utils/thresholdUtils';
import ComponentSelector from './viewSelector';

import { useTableConfig } from './viewConfig/hooks/useTableConfig';
import { TableSettingsSection } from './viewConfig/sections/tableSettingsSection';
import { TopNSettingsSection } from './viewConfig/sections/topNSettingsSection';
import { GaugeSettingsSection } from './viewConfig/sections/gaugeSettingsSection';
import {
  buildDisplayColumnsFromSchema,
  isDisplayableDefaultField,
} from './viewConfig/utils/columnProbing';

interface FormValues {
  name: string;
  description?: string;
  chartType: string;
  dataSource: string | number;
  compare?: boolean;
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: TableConfig;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
}

interface ViewConfigPropsWithManager extends ViewConfigProps {
  dataSourceManager: ReturnType<typeof useDataSourceManager>;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
}

const ViewConfig: React.FC<ViewConfigPropsWithManager> = ({
  open,
  item: widgetItem,
  onConfirm,
  onClose,
  dataSourceManager,
  filterDefinitions = [],
  unifiedFilterValues = {},
  builtinNamespaceId,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [chartType, setChartType] = useState<string>('');
  const [filterBindings, setFilterBindings] = useState<FilterBindings>({});
  const [dataSourceSelectorVisible, setDataSourceSelectorVisible] = useState(false);
  const { getSourceDataByApiId } = useDataSourceApi();

  const {
    selectedDataSource,
    setSelectedDataSource,
    ensureDataSource,
    setDefaultParamValues,
    restoreUserParamValues,
    processFormParamsForSubmit,
  } = dataSourceManager;

  const availableFields = useMemo((): ResponseFieldDefinition[] => {
    return selectedDataSource?.field_schema || [];
  }, [selectedDataSource]);

  const getFilteredChartTypes = (
    dataSource: DatasourceItem | undefined,
  ): ChartTypeItem[] => {
    if (!dataSource?.chart_type?.length) {
      return [];
    }
    const allChartTypes = getChartTypeList();
    return dataSource.chart_type
      .map((type: string) =>
        allChartTypes.find((chart) => chart.value === type),
      )
      .filter((item): item is ChartTypeItem => Boolean(item));
  };

  const getDataSourceChartTypes = useMemo(() => {
    return getFilteredChartTypes(selectedDataSource);
  }, [selectedDataSource]);

  const computePreviewDefinitions = (
    existingDefinitions: UnifiedFilterDefinition[],
    dataSource: DatasourceItem | undefined,
  ): UnifiedFilterDefinition[] => {
    const existingMap = new Map(
      existingDefinitions.map((def) => [def.id, def]),
    );
    const bindableParams = getBindableFilterParams(dataSource?.params);
    bindableParams.forEach((param, index) => {
      const id = getFilterDefinitionId(param.name, param.type);
      if (!existingMap.has(id)) {
        existingMap.set(id, {
          id,
          key: param.name,
          name: param.alias_name || param.name,
          type: param.type,
          defaultValue: (param.value as FilterValue) ?? null,
          order: existingDefinitions.length + index,
          enabled: true,
        });
      }
    });
    return Array.from(existingMap.values());
  };

  const previewFilterDefinitions = useMemo(
    () => computePreviewDefinitions(filterDefinitions, selectedDataSource),
    [filterDefinitions, selectedDataSource],
  );

  const queryConfigParams = useMemo(
    () =>
      (Array.isArray(selectedDataSource?.params)
        ? selectedDataSource.params
        : []
      ).filter((param: ParamItem) =>
        ['params', 'fixed'].includes(param.filterType || 'fixed'),
      ),
    [selectedDataSource?.params],
  );

  const bindableFilterParams = useMemo(
    () =>
      Array.isArray(selectedDataSource?.params)
        ? getBindableFilterParams(selectedDataSource.params)
        : [],
    [selectedDataSource?.params],
  );

  const hasQueryParams = queryConfigParams.length > 0;
  const shouldShowUnifiedFilterSection =
    previewFilterDefinitions.length > 0 && Boolean(selectedDataSource?.params);
  const hasUnifiedFilterBindings = bindableFilterParams.length > 0;

  const gaugeFieldOptions = useMemo(
    () =>
      availableFields
        .filter((field) => field.value_type === 'number')
        .map((field) => ({
          label: field.title ? `${field.key} (${field.title})` : field.key,
          value: field.key,
        })),
    [availableFields],
  );

  const tableConfig = useTableConfig({
    form,
    chartType,
    selectedDataSource,
    availableFields,
    getSourceDataByApiId,
    processFormParamsForSubmit,
    unifiedFilterValues,
    filterBindings,
    filterDefinitions: previewFilterDefinitions,
    builtinNamespaceId,
    t,
  });

  const singleValueConfig = useSingleValueConfig({
    form,
    selectedDataSource,
    getSourceDataByApiId,
    builtinNamespaceId,
    open,
  });

  /** 用户通过弹窗选择了新的数据源，重置所有依赖配置 */
  const handleDataSourceChangeFromSelector = useCallback(
    async (item: DatasourceItem) => {
      setDataSourceSelectorVisible(false);

      // 重置依赖字段
      setChartType('');
      setFilterBindings({});
      tableConfig.resetTableConfig();
      singleValueConfig.resetSingleValueConfig();

      // 加载完整数据源（brief 模式不含 params）
      const fullItem = await ensureDataSource(item.id) || item;

      // 设置新数据源
      setSelectedDataSource(fullItem);
      const newChartTypes = getFilteredChartTypes(fullItem);
      const defaultChartType = newChartTypes[0]?.value || '';

      setChartType(defaultChartType);

      // 重置 form 中的依赖字段
      const params: Record<string, any> = {};
      if (fullItem.params?.length) {
        setDefaultParamValues(fullItem.params, params);
      }

      form.setFieldsValue({
        dataSource: fullItem.id,
        chartType: defaultChartType,
        params,
        selectedFields: [],
        topNLabelField: undefined,
        topNValueField: undefined,
        unit: undefined,
        conversionFactor: undefined,
        decimalPlaces: undefined,
        gaugeMin: 0,
        gaugeMax: 100,
        gaugeShape: 'semicircle',
        compare: false,
      });

      // 重建 filter bindings
      if (fullItem.params?.length) {
        const previewDefs = computePreviewDefinitions(filterDefinitions, fullItem);
        setFilterBindings(buildDefaultFilterBindings(fullItem.params, previewDefs));
      }

      // 如果默认图表类型是 table，尝试探测列
      if (defaultChartType === 'table') {
        const schemaFields = fullItem.field_schema;
        if (schemaFields && schemaFields.length > 0) {
          tableConfig.setDisplayColumns(buildDisplayColumnsFromSchema(schemaFields));
        } else {
          const probedColumns = await tableConfig.probeDefaultDisplayColumns(fullItem, params);
          tableConfig.setDisplayColumns(probedColumns);
        }
      }
    },
    [
      form,
      ensureDataSource,
      setSelectedDataSource,
      setDefaultParamValues,
      filterDefinitions,
      tableConfig,
      singleValueConfig,
    ],
  );

  const topNLabelFieldOptions = useMemo(
    () =>
      availableFields.map((field) => ({
        label: field.title ? `${field.key} (${field.title})` : field.key,
        value: field.key,
      })),
    [availableFields],
  );

  const topNValueFieldOptions = useMemo(
    () =>
      availableFields
        .filter((field) => field.value_type === 'number')
        .map((field) => ({
          label: field.title ? `${field.key} (${field.title})` : field.key,
          value: field.key,
        })),
    [availableFields],
  );

  const filterFieldOptions = useMemo(() => {
    const columnOptions = tableConfig.displayColumns
      .filter((col) => !!col.key?.trim())
      .map((col) => ({
        label: col.key,
        value: col.key,
      }));

    if (columnOptions.length > 0) {
      const unique = new Map<string, { label: string; value: string }>();
      columnOptions.forEach((item) => {
        if (!unique.has(item.value)) {
          unique.set(item.value, item);
        }
      });
      return Array.from(unique.values());
    }

    return availableFields.map((f) => ({
      label: f.key,
      value: f.key,
    }));
  }, [tableConfig.displayColumns, availableFields]);

  const invalidConfiguredFieldKeys = useMemo(() => {
    const availableFieldKeySet = new Set([
      ...availableFields.map((field) => field.key),
      ...tableConfig.displayColumns
        .filter((col) => col.isDefault)
        .map((col) => (col.key || '').trim())
        .filter(Boolean),
    ]);

    if (availableFieldKeySet.size === 0) {
      return [];
    }

    const configuredKeys = [
      ...tableConfig.displayColumns.map((col) => (col.key || '').trim()),
      ...tableConfig.filterFields.map((field) => (field.key || '').trim()),
    ].filter(Boolean);

    return Array.from(
      new Set(configuredKeys.filter((key) => !availableFieldKeySet.has(key))),
    );
  }, [availableFields, tableConfig.displayColumns, tableConfig.filterFields]);

  const handleChartTypeChange = async (e: any) => {
    const newChartType = e.target.value;
    setChartType(newChartType);
    form.setFieldsValue({ chartType: newChartType });
    await tableConfig.handleChartTypeChange(newChartType);
  };

  const initializeItemForm = async (
    widgetItem: ViewConfigItem,
  ): Promise<void> => {
    const { valueConfig } = widgetItem;
    const formValues: FormValues = {
      name: widgetItem?.name || '',
      description: widgetItem.description || '',
      chartType: valueConfig?.chartType || '',
      dataSource: valueConfig?.dataSource || '',
      dataSourceParams: valueConfig?.dataSourceParams || [],
      params: {},
      tableConfig: valueConfig?.tableConfig,
    };
    setChartType(formValues.chartType);

    if (valueConfig?.tableConfig?.filterFields) {
      tableConfig.setFilterFields(
        valueConfig.tableConfig.filterFields.map((f, idx) => ({
          ...f,
          id: `filter_${idx}_${Date.now()}`,
        })),
      );
    } else {
      tableConfig.setFilterFields([]);
    }

    const targetDataSource = await ensureDataSource(formValues.dataSource);
    if (targetDataSource) {
      setSelectedDataSource(targetDataSource);
      formValues.params = formValues.params || {};

      if (!formValues.chartType && targetDataSource.chart_type?.length) {
        const availableChartTypes = getFilteredChartTypes(targetDataSource);
        formValues.chartType = availableChartTypes[0]?.value;
        setChartType(formValues.chartType);
      }

      if (targetDataSource.params?.length) {
        setDefaultParamValues(targetDataSource.params, formValues.params);
        if (formValues.dataSourceParams?.length) {
          restoreUserParamValues(
            formValues.dataSourceParams,
            formValues.params,
          );
        }

        const previewDefs = computePreviewDefinitions(
          filterDefinitions,
          targetDataSource,
        );
        setFilterBindings(
          buildDefaultFilterBindings(
            formValues.dataSourceParams?.length
              ? formValues.dataSourceParams
              : targetDataSource.params,
            previewDefs,
            (valueConfig as ValueConfig | undefined)?.filterBindings,
          ),
        );
      } else {
        setFilterBindings({});
      }

      if (valueConfig?.tableConfig?.columns?.length) {
        const schemaDefaultKeys = new Set(
          (targetDataSource?.field_schema || [])
            .map((field) => field.key)
            .filter((key) => isDisplayableDefaultField(key)),
        );

        const probedColumns = await tableConfig.probeDefaultDisplayColumns(
          targetDataSource,
          formValues.params || {},
        );
        const probeDefaultKeys = new Set(
          (probedColumns || []).map((col) => col.key),
        );

        tableConfig.setDisplayColumns(
          valueConfig.tableConfig.columns.map((c, idx) => ({
            ...c,
            id: `column_${idx}_${Date.now()}`,
            isDefault:
              schemaDefaultKeys.has(c.key) || probeDefaultKeys.has(c.key),
          })),
        );
      }

      if (
        !valueConfig?.tableConfig?.columns?.length &&
        formValues.chartType === 'table'
      ) {
        const schemaFields = targetDataSource?.field_schema;
        if (schemaFields && schemaFields.length > 0) {
          tableConfig.setDisplayColumns(
            buildDisplayColumnsFromSchema(schemaFields),
          );
        } else {
          const probedColumns = await tableConfig.probeDefaultDisplayColumns(
            targetDataSource,
            formValues.params || {},
          );
          tableConfig.setDisplayColumns(probedColumns);
        }
      }
    } else {
      setSelectedDataSource(undefined);
      if (!valueConfig?.tableConfig?.columns?.length) {
        tableConfig.setDisplayColumns([]);
      }
    }

    if (valueConfig?.selectedFields) {
      singleValueConfig.setSelectedFields(valueConfig.selectedFields);
      formValues.selectedFields = valueConfig.selectedFields;
    } else {
      singleValueConfig.setSelectedFields([]);
    }

    if (valueConfig?.topNLabelField !== undefined) {
      formValues.topNLabelField = valueConfig.topNLabelField;
    }
    if (valueConfig?.topNValueField !== undefined) {
      formValues.topNValueField = valueConfig.topNValueField;
    }

    if (valueConfig?.unit !== undefined) {
      formValues.unit = valueConfig.unit;
    }
    if (valueConfig?.conversionFactor !== undefined) {
      formValues.conversionFactor = valueConfig.conversionFactor;
    }
    if (valueConfig?.decimalPlaces !== undefined) {
      formValues.decimalPlaces = valueConfig.decimalPlaces;
    }
    if (valueConfig?.gaugeMin !== undefined) {
      formValues.gaugeMin = valueConfig.gaugeMin;
    }
    if (valueConfig?.gaugeMax !== undefined) {
      formValues.gaugeMax = valueConfig.gaugeMax;
    }
    if (valueConfig?.gaugeShape !== undefined) {
      formValues.gaugeShape = valueConfig.gaugeShape;
    }
    if (valueConfig?.compare !== undefined) {
      formValues.compare = valueConfig.compare && canEnableCompare({
        config: { chartType: 'single', dataSourceParams: targetDataSource?.params },
        dataSource: targetDataSource,
      });
    }

    singleValueConfig.setThresholdColors(initThresholdColors(valueConfig?.thresholdColors));

    form.setFieldsValue(formValues);
  };

  const resetForm = (): void => {
    form.resetFields();
    setSelectedDataSource(undefined);
    setChartType('');
    setFilterBindings({});
    setDataSourceSelectorVisible(false);
    tableConfig.resetTableConfig();
    singleValueConfig.resetSingleValueConfig();
  };

  const handleFormValuesChange = (changedValues: Record<string, any>) => {
    if (chartType !== 'table') {
      return;
    }
    if ('params' in changedValues && selectedDataSource) {
      tableConfig.setParamsChangedAfterProbe(true);
    }
  };

  useEffect(() => {
    if (open) {
      void initializeItemForm(widgetItem);
    } else if (!open) {
      resetForm();
    }
  }, [open, widgetItem, form]);

  useEffect(() => {
    if (!tableConfig.displayColumnsError) {
      return;
    }

    const hasVisibleColumn = tableConfig.displayColumns
      .map((col) => ({
        ...col,
        key: (col.key || '').trim(),
      }))
      .some((col) => col.key && col.visible !== false);

    if (hasVisibleColumn) {
      tableConfig.setDisplayColumnsError('');
    }
  }, [tableConfig.displayColumns, tableConfig.displayColumnsError]);

  const handleConfirm = async () => {
    try {
      const values: FormValues = await form.validateFields();
      if (values.params && selectedDataSource?.params) {
        values.dataSourceParams = processFormParamsForSubmit(
          values.params,
          selectedDataSource.params,
        );
        delete values.params;
      }

      if (chartType === 'table') {
        tableConfig.setDisplayColumnsError('');
        const tableConfigData: TableConfig = {};

        if (tableConfig.filterFields.length > 0) {
          tableConfigData.filterFields = tableConfig.filterFields
            .filter((f) => f.key)
            .map(({ key, label, inputType }) => ({
              key,
              label,
              inputType,
            }));
        }

        const validDisplayColumns = tableConfig.displayColumns
          .map((col) => ({
            ...col,
            key: col.key.trim(),
            title: col.title?.trim() || col.key.trim(),
          }))
          .filter((col) => col.key);

        const duplicateKeySet = new Set<string>();
        const hasDuplicateKeys = validDisplayColumns.some((col) => {
          if (duplicateKeySet.has(col.key)) return true;
          duplicateKeySet.add(col.key);
          return false;
        });

        if (hasDuplicateKeys) {
          message.error(
            t('dashboard.duplicateFieldKey') || '字段 key 不能重复',
          );
          return;
        }

        const hasVisibleColumn = validDisplayColumns.some(
          (col) => col.visible !== false,
        );
        if (!hasVisibleColumn) {
          tableConfig.setDisplayColumnsError(
            t('dashboard.atLeastOneVisibleColumn') || '请至少保留一列可见',
          );
          return;
        }

        if (validDisplayColumns.length > 0) {
          tableConfigData.columns = validDisplayColumns.map((col, index) => ({
            key: col.key,
            title: col.title,
            visible: col.visible,
            order: index,
          }));
        }

        if (
          tableConfigData.filterFields?.length ||
          tableConfigData.columns?.length
        ) {
          values.tableConfig = tableConfigData;
        }
      }

      let result: WidgetConfig = { ...values } as WidgetConfig;

      if (chartType === 'single') {
        result.selectedFields = singleValueConfig.selectedFields;
        result.thresholdColors = singleValueConfig.thresholdColors;
        result.compare = !!values.compare;
        const unitValue = form.getFieldValue('unit');
        const conversionFactorValue = form.getFieldValue('conversionFactor');
        const decimalPlacesValue = form.getFieldValue('decimalPlaces');
        if (unitValue !== undefined) result.unit = unitValue;
        if (conversionFactorValue !== undefined)
          result.conversionFactor = conversionFactorValue;
        if (decimalPlacesValue !== undefined)
          result.decimalPlaces = decimalPlacesValue;
      }

      if (chartType === 'gauge') {
        result.selectedFields = singleValueConfig.selectedFields;
        result.thresholdColors = singleValueConfig.thresholdColors;
        const unitValue = form.getFieldValue('unit');
        const conversionFactorValue = form.getFieldValue('conversionFactor');
        const decimalPlacesValue = form.getFieldValue('decimalPlaces');
        const gaugeMinValue = form.getFieldValue('gaugeMin');
        const gaugeMaxValue = form.getFieldValue('gaugeMax');
        const gaugeShapeValue = form.getFieldValue('gaugeShape');
        if (unitValue !== undefined) result.unit = unitValue;
        if (conversionFactorValue !== undefined)
          result.conversionFactor = conversionFactorValue;
        if (decimalPlacesValue !== undefined)
          result.decimalPlaces = decimalPlacesValue;
        if (gaugeMinValue !== undefined) result.gaugeMin = gaugeMinValue;
        if (gaugeMaxValue !== undefined) result.gaugeMax = gaugeMaxValue;
        if (gaugeShapeValue !== undefined) result.gaugeShape = gaugeShapeValue;
      }

      if (chartType === 'topN') {
        result.topNLabelField = values.topNLabelField;
        result.topNValueField = values.topNValueField;
      }

      if (filterBindings && Object.keys(filterBindings).length > 0) {
        result = { ...result, filterBindings };
      }

      onConfirm?.(result);
    } catch (error) {
      console.error('Form validation failed:', error);
      message.error(t('common.saveFailed'));
    }
  };

  return (
    <Drawer
      title={t('dashboard.viewConfig')}
      placement="right"
      width={700}
      open={open}
      onClose={onClose}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button type="primary" onClick={handleConfirm}>
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={onClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        labelCol={{ span: 4 }}
        onValuesChange={handleFormValuesChange}
      >
        <div className="mb-6">
          <div className="font-bold text-(--color-text-1) mb-4">
            {t('dashboard.basicSettings')}
          </div>
          <Form.Item
            label={t('dashboard.widgetName')}
            name="name"
            rules={[{ required: true, message: t('dashboard.inputName') }]}
          >
            <Input placeholder={t('dashboard.inputName')} />
          </Form.Item>
          <Form.Item
            label={t('dashboard.dataSource')}
            name="dataSource"
            rules={[{ required: true, message: t('common.selectTip') }]}
            getValueProps={() => ({
              value: selectedDataSource
                ? `${selectedDataSource.name}（${selectedDataSource.rest_api}）`
                : '',
            })}
          >
            <Input
              readOnly
              placeholder={t('common.selectTip')}
              suffix={
                <SwapOutlined
                  className="cursor-pointer text-(--color-primary)"
                  onClick={() => setDataSourceSelectorVisible(true)}
                />
              }
              onClick={() => setDataSourceSelectorVisible(true)}
              className="cursor-pointer"
            />
          </Form.Item>
          <Form.Item
            label={t('dashboard.chartTypeLabel')}
            name="chartType"
            rules={[{ required: true, message: t('common.selectTip') }]}
            initialValue={getDataSourceChartTypes[0]?.value}
          >
            <Radio.Group onChange={handleChartTypeChange}>
              {getDataSourceChartTypes.map((item: ChartTypeItem) => (
                <Radio.Button key={item.value} value={item.value}>
                  {t(item.label)}
                </Radio.Button>
              ))}
            </Radio.Group>
          </Form.Item>
          <Form.Item label={t('dataSource.describe')} name="description">
            <Input.TextArea
              placeholder={t('common.inputMsg')}
              autoSize={{ minRows: 2, maxRows: 4 }}
            />
          </Form.Item>
        </div>

        {hasQueryParams && (
          <div className="mb-6">
            <div className="font-bold text-(--color-text-1) mb-4">
              {t('dashboard.queryParams')}
            </div>
            <DataSourceParamsConfig
              selectedDataSource={selectedDataSource}
              includeFilterTypes={['params', 'fixed']}
            />
          </div>
        )}

        {shouldShowUnifiedFilterSection && hasUnifiedFilterBindings && (
          <div className="mb-6">
            <div className="font-bold text-(--color-text-1) mb-4 flex items-center gap-1">
              {t('dashboard.unifiedFilterLinkage')}
              <Tooltip title={t('dashboard.unifiedFilterBindingTip')}>
                <QuestionCircleOutlined className="text-(--color-text-3) cursor-help" />
              </Tooltip>
            </div>
            <FilterBindingPanel
              definitions={previewFilterDefinitions}
              dataSourceParams={selectedDataSource.params}
              filterBindings={filterBindings}
              onChange={setFilterBindings}
            />
          </div>
        )}

        {chartType === 'table' && (
          <TableSettingsSection
            t={t}
            displayColumns={tableConfig.displayColumns}
            filterFields={tableConfig.filterFields}
            filterFieldOptions={filterFieldOptions}
            invalidConfiguredFieldKeys={invalidConfiguredFieldKeys}
            isProbingColumns={tableConfig.isProbingColumns}
            paramsChangedAfterProbe={tableConfig.paramsChangedAfterProbe}
            displayColumnsError={tableConfig.displayColumnsError}
            onAddFilterField={tableConfig.handleAddFilterField}
            onDeleteFilterField={tableConfig.handleDeleteFilterField}
            onFilterFieldChange={tableConfig.handleFilterFieldChange}
            onAddDisplayColumn={tableConfig.handleAddDisplayColumn}
            onDeleteDisplayColumn={tableConfig.handleDeleteDisplayColumn}
            onDisplayColumnChange={tableConfig.handleDisplayColumnChange}
            onDisplayColumnKeyBlur={tableConfig.handleDisplayColumnKeyBlur}
            onDisplayColumnDragEnd={tableConfig.handleDisplayColumnDragEnd}
            onReProbeColumns={tableConfig.handleReProbeColumns}
            onAddNewFilterField={() =>
              tableConfig.setFilterFields([
                ...tableConfig.filterFields,
                tableConfig.createDefaultFilterField(),
              ])
            }
            onAddNewDisplayColumn={() =>
              tableConfig.setDisplayColumns([
                ...tableConfig.displayColumns,
                tableConfig.createDefaultDisplayColumn(),
              ])
            }
          />
        )}

        {chartType === 'single' && (
          <SingleValueSettingsSection
            t={t}
            sectionTitle={t('dashboard.displaySettings')}
            selectedDataSource={selectedDataSource}
            singleValueTreeData={singleValueConfig.singleValueTreeData}
            selectedFields={singleValueConfig.selectedFields}
            loadingSingleValueData={singleValueConfig.loadingSingleValueData}
            thresholdColors={singleValueConfig.thresholdColors}
            onFetchSingleValueDataFields={
              singleValueConfig.fetchSingleValueDataFields
            }
            onSingleValueFieldChange={
              singleValueConfig.handleSingleValueFieldChange
            }
            onThresholdChange={singleValueConfig.handleThresholdChange}
            onThresholdBlur={singleValueConfig.handleThresholdBlur}
            onAddThreshold={singleValueConfig.addThreshold}
            onRemoveThreshold={singleValueConfig.removeThreshold}
            compareAvailable={singleValueConfig.compareAvailable}
          />
        )}

        {chartType === 'gauge' && (
          <GaugeSettingsSection
            t={t}
            sectionTitle={t('dashboard.gaugeSettings')}
            selectedDataSource={selectedDataSource}
            fieldOptions={gaugeFieldOptions}
            thresholdColors={singleValueConfig.thresholdColors}
            onThresholdChange={singleValueConfig.handleThresholdChange}
            onThresholdBlur={singleValueConfig.handleThresholdBlur}
            onAddThreshold={singleValueConfig.addThreshold}
            onRemoveThreshold={singleValueConfig.removeThreshold}
          />
        )}

        {chartType === 'topN' && (
          <TopNSettingsSection
            t={t}
            sectionTitle={t('dashboard.displaySettings')}
            selectedDataSource={selectedDataSource}
            topNLabelFieldOptions={topNLabelFieldOptions}
            topNValueFieldOptions={topNValueFieldOptions}
          />
        )}
      </Form>
      <ComponentSelector
        visible={dataSourceSelectorVisible}
        onCancel={() => setDataSourceSelectorVisible(false)}
        onOpenConfig={handleDataSourceChangeFromSelector}
      />
    </Drawer>
  );
};

export default ViewConfig;
