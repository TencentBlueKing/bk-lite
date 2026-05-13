import React, { useEffect, useState, useMemo } from 'react';
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
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import {
  getChartTypeList,
  ChartTypeItem,
} from '@/app/ops-analysis/constants/common';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import DataSourceSelect from '@/app/ops-analysis/components/dataSourceSelect';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  getFilterDefinitionId,
  getBindableFilterParams,
  buildDefaultFilterBindings,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import type {
  DatasourceItem,
  ParamItem,
  ResponseFieldDefinition,
} from '@/app/ops-analysis/types/dataSource';
import { DEFAULT_THRESHOLD_COLORS } from '@/app/ops-analysis/constants/threshold';

import { useTableConfig } from './viewConfig/hooks/useTableConfig';
import { useSingleValueConfig } from './viewConfig/hooks/useSingleValueConfig';
import { TableSettingsSection } from './viewConfig/sections/tableSettingsSection';
import { SingleValueSettingsSection } from './viewConfig/sections/singleValueSettingsSection';
import {
  buildDisplayColumnsFromSchema,
  isDisplayableDefaultField,
} from './viewConfig/utils/columnProbing';

interface FormValues {
  name: string;
  description?: string;
  chartType: string;
  dataSource: string | number;
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: TableConfig;
  selectedFields?: string[];
  unit?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
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
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [chartType, setChartType] = useState<string>('');
  const [filterBindings, setFilterBindings] = useState<FilterBindings>({});
  const { getSourceDataByApiId } = useDataSourceApi();

  const {
    dataSources,
    selectedDataSource,
    setSelectedDataSource,
    findDataSource,
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
    t,
  });

  const singleValueConfig = useSingleValueConfig({
    form,
    selectedDataSource,
    getSourceDataByApiId,
  });

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

    const targetDataSource = findDataSource(formValues.dataSource);
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
        setFilterBindings(
          (valueConfig as ValueConfig | undefined)?.filterBindings || {},
        );
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

    if (valueConfig?.unit !== undefined) {
      formValues.unit = valueConfig.unit;
    }
    if (valueConfig?.conversionFactor !== undefined) {
      formValues.conversionFactor = valueConfig.conversionFactor;
    }
    if (valueConfig?.decimalPlaces !== undefined) {
      formValues.decimalPlaces = valueConfig.decimalPlaces;
    }

    if (
      valueConfig?.thresholdColors &&
      Array.isArray(valueConfig.thresholdColors)
    ) {
      const sortedThresholds = [...valueConfig.thresholdColors].sort(
        (a, b) => parseFloat(b.value) - parseFloat(a.value),
      );
      singleValueConfig.setThresholdColors(sortedThresholds);
    } else {
      singleValueConfig.setThresholdColors(DEFAULT_THRESHOLD_COLORS);
    }

    form.setFieldsValue(formValues);
  };

  const resetForm = (): void => {
    form.resetFields();
    setSelectedDataSource(undefined);
    setChartType('');
    setFilterBindings({});
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
    if (open && dataSources.length > 0) {
      void initializeItemForm(widgetItem);
    } else if (!open) {
      resetForm();
    }
  }, [open, widgetItem, form, dataSources]);

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
        const unitValue = form.getFieldValue('unit');
        const conversionFactorValue = form.getFieldValue('conversionFactor');
        const decimalPlacesValue = form.getFieldValue('decimalPlaces');
        if (unitValue !== undefined) result.unit = unitValue;
        if (conversionFactorValue !== undefined)
          result.conversionFactor = conversionFactorValue;
        if (decimalPlacesValue !== undefined)
          result.decimalPlaces = decimalPlacesValue;
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
          <Form.Item label={t('dataSource.describe')} name="description">
            <Input.TextArea
              placeholder={t('common.inputMsg')}
              autoSize={{ minRows: 2, maxRows: 4 }}
            />
          </Form.Item>
        </div>

        <div className="mb-6">
          <div className="font-bold text-(--color-text-1) mb-4">
            {t('dashboard.dataSource')}
          </div>
          <Form.Item
            label={t('dashboard.dataSourceType')}
            name="dataSource"
            rules={[{ required: true, message: t('common.selectTip') }]}
          >
            <DataSourceSelect
              placeholder={t('common.selectTip')}
              dataSources={dataSources}
              disabled
              onDataSourceChange={setSelectedDataSource}
            />
          </Form.Item>
        </div>

        <div className="mb-6">
          <div className="font-bold text-(--color-text-1) mb-4">
            {t('dashboard.paramSettings')}
          </div>
          <DataSourceParamsConfig
            selectedDataSource={selectedDataSource}
            includeFilterTypes={['params', 'fixed']}
          />
        </div>

        {previewFilterDefinitions.length > 0 && selectedDataSource?.params && (
          <div className="mb-6">
            <div className="font-bold text-(--color-text-1) mb-4 flex items-center gap-1">
              {t('dashboard.unifiedFilterBinding')}
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

        <div className="mb-6">
          <div className="font-bold text-(--color-text-1) mb-4">
            {t('dashboard.chartTypeLabel')}
          </div>
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
        </div>

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
          />
        )}
      </Form>
    </Drawer>
  );
};

export default ViewConfig;
