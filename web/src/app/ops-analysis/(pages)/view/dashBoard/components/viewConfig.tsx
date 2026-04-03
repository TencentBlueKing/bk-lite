import React, { useEffect, useState, useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  ViewConfigProps,
  ViewConfigItem,
  TableFilterFieldConfig,
  TableColumnConfigItem,
  TableConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  Drawer,
  Button,
  Form,
  Input,
  Radio,
  Select,
  Switch,
  Empty,
  Tooltip,
  message,
} from 'antd';
import {
  PlusCircleOutlined,
  MinusCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import {
  getChartTypeList,
  ChartTypeItem,
} from '@/app/ops-analysis/constants/common';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import DataSourceSelect from '@/app/ops-analysis/components/dataSourceSelect';
import CustomTable from '@/components/custom-table';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import type {
  DatasourceItem,
  ParamItem,
  ResponseFieldDefinition,
} from '@/app/ops-analysis/types/dataSource';

interface FormValues {
  name: string;
  description?: string;
  chartType: string;
  dataSource: string | number;
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: TableConfig;
}

type DisplayColumnRow = TableColumnConfigItem & {
  id: string;
  isDefault?: boolean;
};

interface ViewConfigPropsWithManager extends ViewConfigProps {
  dataSourceManager: ReturnType<typeof useDataSourceManager>;
}

const ViewConfig: React.FC<ViewConfigPropsWithManager> = ({
  open,
  item: widgetItem,
  onConfirm,
  onClose,
  dataSourceManager,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [chartType, setChartType] = useState<string>('');
  const [isProbingColumns, setIsProbingColumns] = useState(false);
  const [paramsChangedAfterProbe, setParamsChangedAfterProbe] = useState(false);
  const [displayColumnsError, setDisplayColumnsError] = useState('');
  const [filterFields, setFilterFields] = useState<
    (TableFilterFieldConfig & { id: string })[]
      >([]);
  const [displayColumns, setDisplayColumns] = useState<DisplayColumnRow[]>([]);
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
      .filter((item): item is ChartTypeItem => Boolean(item))
      .filter((item: ChartTypeItem) => item.value !== 'single');
  };

  const getDataSourceChartTypes = React.useMemo(() => {
    return getFilteredChartTypes(selectedDataSource);
  }, [selectedDataSource]);

  const availableFields = useMemo((): ResponseFieldDefinition[] => {
    return selectedDataSource?.field_schema || [];
  }, [selectedDataSource]);

  const filterFieldOptions = useMemo(() => {
    const columnOptions = displayColumns
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
  }, [displayColumns, availableFields]);

  const invalidConfiguredFieldKeys = useMemo(() => {
    const availableFieldKeySet = new Set([
      ...availableFields.map((field) => field.key),
      ...displayColumns
        .filter((col) => col.isDefault)
        .map((col) => (col.key || '').trim())
        .filter(Boolean),
    ]);

    if (availableFieldKeySet.size === 0) {
      return [];
    }

    const configuredKeys = [
      ...displayColumns.map((col) => (col.key || '').trim()),
      ...filterFields.map((field) => (field.key || '').trim()),
    ].filter(Boolean);

    return Array.from(
      new Set(configuredKeys.filter((key) => !availableFieldKeySet.has(key))),
    );
  }, [availableFields, displayColumns, filterFields]);

  const filterInputTypeOptions = [
    { label: t('dashboard.keyword'), value: 'keyword' },
    { label: t('dashboard.timeRange'), value: 'time_range' },
  ];

  const createDefaultFilterField = (): TableFilterFieldConfig & {
    id: string;
  } => ({
    id: `filter_${Date.now()}`,
    key: '',
    label: '',
    inputType: 'keyword',
  });

  const createDefaultDisplayColumn = (): DisplayColumnRow => ({
    id: `column_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
    key: '',
    title: '',
    visible: true,
    order: displayColumns.length,
    isDefault: false,
  });

  const isDisplayableDefaultField = (key: string): boolean => {
    const normalized = (key || '').trim();
    if (!normalized) {
      return false;
    }
    return !normalized.startsWith('_');
  };

  const buildDisplayColumnsFromSchema = (
    fields: ResponseFieldDefinition[],
  ): DisplayColumnRow[] => {
    return (fields || [])
      .filter((field) => isDisplayableDefaultField(field.key))
      .map((field, idx) => ({
        id: `column_schema_${Date.now()}_${idx}`,
        key: field.key,
        title: field.title || field.key,
        visible: true,
        order: idx,
        isDefault: true,
      }));
  };

  const extractFirstRecordFromSourceData = (
    sourceData: any,
  ): Record<string, unknown> | null => {
    const findFirstRecord = (rows: any[]): Record<string, unknown> | null => {
      for (const row of rows) {
        if (row && typeof row === 'object') {
          const rowData = row.data;

          // 表格类：data 是对象，包含 {data: [...], count, page, page_size}
          if (
            rowData &&
            typeof rowData === 'object' &&
            !Array.isArray(rowData) &&
            Array.isArray(rowData.data)
          ) {
            const firstInNested = rowData.data.find(
              (item: any) => item && typeof item === 'object',
            );
            if (firstInNested) {
              return firstInNested;
            }
            continue;
          }

          // 图表类：data 是数组
          if (Array.isArray(rowData)) {
            const firstInGroup = rowData.find(
              (item: any) => item && typeof item === 'object',
            );
            if (firstInGroup) {
              return firstInGroup;
            }
            continue;
          }

          // 格式不符合，跳过
          continue;
        }
      }
      return null;
    };

    if (Array.isArray(sourceData)) {
      return findFirstRecord(sourceData);
    }

    if (sourceData && typeof sourceData === 'object') {
      const rows = sourceData.items || sourceData.data || sourceData.list;
      if (Array.isArray(rows)) {
        return findFirstRecord(rows);
      }
    }

    return null;
  };

  const mergeDetectedFieldsWithSchema = (
    detectedFieldKeys: string[],
    schemaFields: ResponseFieldDefinition[],
  ): DisplayColumnRow[] => {
    const schemaTitleMap = new Map(
      (schemaFields || []).map((field) => [
        field.key,
        field.title || field.key,
      ]),
    );

    return detectedFieldKeys
      .filter((key) => isDisplayableDefaultField(key))
      .map((key, idx) => ({
        id: `column_detected_${Date.now()}_${idx}`,
        key,
        title: schemaTitleMap.get(key) || key,
        visible: true,
        order: idx,
        isDefault: true,
      }));
  };

  const buildProbeParams = (
    targetDataSource: DatasourceItem,
    formParams: Record<string, any>,
  ): Record<string, any> => {
    const payload: Record<string, any> = {};
    const sourceParams = targetDataSource.params || [];
    const processedParams = processFormParamsForSubmit(
      formParams,
      sourceParams,
    );
    processedParams.forEach((param) => {
      payload[param.name] = param.value;
    });
    return payload;
  };

  const probeDefaultDisplayColumns = async (
    targetDataSource: DatasourceItem,
    formParams: Record<string, any>,
  ): Promise<DisplayColumnRow[]> => {
    try {
      const payload = buildProbeParams(targetDataSource, formParams);
      const sourceData = await getSourceDataByApiId(
        targetDataSource.id,
        payload,
      );
      const firstRecord = extractFirstRecordFromSourceData(sourceData);
      if (!firstRecord) {
        return [];
      }

      const detectedKeys = Object.keys(firstRecord);
      if (detectedKeys.length === 0) {
        return [];
      }

      return mergeDetectedFieldsWithSchema(
        detectedKeys,
        targetDataSource?.field_schema || [],
      );
    } catch {
      return [];
    }
  };

  const handleAddFilterField = (index: number) => {
    const newField = createDefaultFilterField();
    const newFields = [...filterFields];
    newFields.splice(index + 1, 0, newField);
    setFilterFields(newFields);
  };

  const handleDeleteFilterField = (id: string) => {
    setFilterFields(filterFields.filter((f) => f.id !== id));
  };

  const handleFilterFieldChange = (
    id: string,
    fieldName: keyof TableFilterFieldConfig,
    value: string,
  ) => {
    setFilterFields(
      filterFields.map((f) => {
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
  };

  const handleAddDisplayColumn = (index: number) => {
    const newColumn = createDefaultDisplayColumn();
    const nextColumns = [...displayColumns];
    nextColumns.splice(index + 1, 0, newColumn);
    setDisplayColumns(nextColumns.map((col, idx) => ({ ...col, order: idx })));
  };

  const handleDeleteDisplayColumn = (id: string) => {
    const nextColumns = displayColumns.filter((col) => col.id !== id);
    setDisplayColumns(nextColumns.map((col, idx) => ({ ...col, order: idx })));
  };

  const handleDisplayColumnChange = (
    id: string,
    fieldName: keyof TableColumnConfigItem,
    value: string | boolean,
  ) => {
    setDisplayColumns(
      displayColumns.map((col) => {
        if (col.id !== id) return col;
        const nextCol = {
          ...col,
          [fieldName]: value,
        } as TableColumnConfigItem & {
          id: string;
        };
        return nextCol;
      }),
    );
  };

  const handleDisplayColumnKeyBlur = (id: string) => {
    setDisplayColumns((prev) =>
      prev.map((col) => {
        if (col.id !== id) {
          return col;
        }

        const keyValue = (col.key || '').trim();
        const titleValue = (col.title || '').trim();
        if (!keyValue || titleValue) {
          return col;
        }

        return {
          ...col,
          title: keyValue,
        };
      }),
    );
  };

  const handleDisplayColumnDragEnd = (
    targetTableData: typeof displayColumns,
  ) => {
    const nextColumns = (targetTableData || []).map((item, idx) => ({
      ...item,
      order: idx,
    }));
    setDisplayColumns(nextColumns);
  };

  const mergeProbedDefaultsWithCurrentColumns = (
    probedColumns: DisplayColumnRow[],
    currentColumns: DisplayColumnRow[],
  ): DisplayColumnRow[] => {
    const existingDefaultMap = new Map(
      currentColumns
        .filter((col) => col.isDefault)
        .map((col) => [col.key, col]),
    );

    const mergedDefaults = probedColumns.map((col, idx) => {
      const existing = existingDefaultMap.get(col.key);
      return {
        ...col,
        id: existing?.id || col.id,
        visible: existing?.visible ?? col.visible,
        order: idx,
        isDefault: true,
      };
    });

    const customColumns = currentColumns
      .filter((col) => !col.isDefault)
      .map((col, idx) => ({
        ...col,
        order: mergedDefaults.length + idx,
      }));

    return [...mergedDefaults, ...customColumns];
  };

  const handleReProbeColumns = async () => {
    if (!selectedDataSource || chartType !== 'table') {
      return;
    }

    try {
      setIsProbingColumns(true);
      const currentParams = (form.getFieldValue('params') || {}) as Record<
        string,
        any
      >;
      const probedColumns = await probeDefaultDisplayColumns(
        selectedDataSource,
        currentParams,
      );

      if (probedColumns.length > 0) {
        setDisplayColumns((prev) =>
          mergeProbedDefaultsWithCurrentColumns(probedColumns, prev),
        );
        setParamsChangedAfterProbe(false);
        message.success(t('dashboard.reProbeSuccess'));
        return;
      }

      message.warning(t('dashboard.reProbeNoFields') || '未探测到可用字段');
    } finally {
      setIsProbingColumns(false);
    }
  };

  const handleChartTypeChange = async (e: any) => {
    const newChartType = e.target.value;
    setChartType(newChartType);
    form.setFieldsValue({ chartType: newChartType });

    if (
      newChartType === 'table' &&
      displayColumns.length === 0 &&
      selectedDataSource
    ) {
      const currentParams = (form.getFieldValue('params') || {}) as Record<
        string,
        any
      >;
      const probedColumns = await probeDefaultDisplayColumns(
        selectedDataSource,
        currentParams,
      );
      if (probedColumns.length > 0) {
        setDisplayColumns(probedColumns);
      } else if (availableFields.length > 0) {
        setDisplayColumns(buildDisplayColumnsFromSchema(availableFields));
      }
    }
  };

  const filterFieldColumns = [
    {
      title: t('dashboard.filterFieldKey'),
      dataIndex: 'key',
      key: 'key',
      width: 160,
      render: (_: unknown, record: TableFilterFieldConfig & { id: string }) => (
        <Select
          value={record.key || undefined}
          placeholder={t('common.selectTip')}
          style={{ width: '100%' }}
          onChange={(val) => handleFilterFieldChange(record.id, 'key', val)}
          options={filterFieldOptions}
          showSearch
          optionFilterProp="label"
        />
      ),
    },
    {
      title: t('dashboard.filterFieldLabel'),
      dataIndex: 'label',
      key: 'label',
      width: 140,
      render: (_: unknown, record: TableFilterFieldConfig & { id: string }) => (
        <Input
          value={record.label}
          placeholder={t('dashboard.filterFieldLabel')}
          onChange={(e) =>
            handleFilterFieldChange(record.id, 'label', e.target.value)
          }
        />
      ),
    },
    {
      title: t('dashboard.filterInputType'),
      dataIndex: 'inputType',
      key: 'inputType',
      width: 120,
      render: (_: unknown, record: TableFilterFieldConfig & { id: string }) => (
        <Select
          value={record.inputType}
          options={filterInputTypeOptions}
          style={{ width: '100%' }}
          onChange={(val) =>
            handleFilterFieldChange(record.id, 'inputType', val)
          }
        />
      ),
    },
    {
      title: t('dataSource.operation'),
      key: 'action',
      width: 80,
      render: (
        _: unknown,
        record: TableFilterFieldConfig & { id: string },
        index: number,
      ) => (
        <div
          style={{ display: 'flex', gap: '4px', justifyContent: 'flex-start' }}
        >
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => handleAddFilterField(index)}
            style={{ border: 'none', padding: '4px' }}
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => handleDeleteFilterField(record.id)}
            style={{ border: 'none', padding: '4px' }}
          />
        </div>
      ),
    },
  ];

  const displayColumnTableColumns = [
    {
      title: t('dashboard.filterFieldKey'),
      dataIndex: 'key',
      key: 'key',
      width: 180,
      render: (_: unknown, record: DisplayColumnRow) => (
        <Input
          value={record.key}
          placeholder={t('common.inputMsg')}
          onChange={(e) =>
            handleDisplayColumnChange(record.id, 'key', e.target.value)
          }
          onBlur={() => handleDisplayColumnKeyBlur(record.id)}
        />
      ),
    },
    {
      title: t('dashboard.filterFieldLabel'),
      dataIndex: 'title',
      key: 'title',
      width: 180,
      render: (_: unknown, record: DisplayColumnRow) => (
        <Input
          value={record.title}
          placeholder={t('dashboard.filterFieldLabel')}
          onChange={(e) =>
            handleDisplayColumnChange(record.id, 'title', e.target.value)
          }
        />
      ),
    },
    {
      title: t('dashboard.columnVisible') || 'Visible',
      dataIndex: 'visible',
      key: 'visible',
      width: 90,
      render: (_: unknown, record: DisplayColumnRow) => (
        <Switch
          size="small"
          checked={record.visible}
          onChange={(e) => handleDisplayColumnChange(record.id, 'visible', e)}
        />
      ),
    },
    {
      title: t('dataSource.operation'),
      key: 'action',
      width: 100,
      render: (_: unknown, record: DisplayColumnRow, index: number) => (
        <div
          style={{ display: 'flex', gap: '4px', justifyContent: 'flex-start' }}
        >
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => handleAddDisplayColumn(index)}
            style={{ border: 'none', padding: '4px' }}
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => handleDeleteDisplayColumn(record.id)}
            style={{ border: 'none', padding: '4px' }}
          />
        </div>
      ),
    },
  ];

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
    if (!formValues) return;

    setChartType(formValues.chartType);

    if (valueConfig?.tableConfig?.filterFields) {
      setFilterFields(
        valueConfig.tableConfig.filterFields.map((f, idx) => ({
          ...f,
          id: `filter_${idx}_${Date.now()}`,
        })),
      );
    } else {
      setFilterFields([]);
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
      }

      if (valueConfig?.tableConfig?.columns?.length) {
        const schemaDefaultKeys = new Set(
          (targetDataSource?.field_schema || [])
            .map((field) => field.key)
            .filter((key) => isDisplayableDefaultField(key)),
        );

        const probedColumns = await probeDefaultDisplayColumns(
          targetDataSource,
          formValues.params || {},
        );
        const probeDefaultKeys = new Set(
          (probedColumns || []).map((col) => col.key),
        );

        setDisplayColumns(
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
        // 初始化时：数据源 schema 优先，探测列兜底
        const schemaFields = targetDataSource?.field_schema;
        if (schemaFields && schemaFields.length > 0) {
          setDisplayColumns(buildDisplayColumnsFromSchema(schemaFields));
        } else {
          const probedColumns = await probeDefaultDisplayColumns(
            targetDataSource,
            formValues.params || {},
          );
          setDisplayColumns(probedColumns);
        }
      }
    } else {
      setSelectedDataSource(undefined);
      if (!valueConfig?.tableConfig?.columns?.length) {
        setDisplayColumns([]);
      }
    }

    form.setFieldsValue(formValues);
  };

  const resetForm = (): void => {
    form.resetFields();
    setSelectedDataSource(undefined);
    setChartType('');
    setIsProbingColumns(false);
    setParamsChangedAfterProbe(false);
    setFilterFields([]);
    setDisplayColumns([]);
  };

  const handleFormValuesChange = (changedValues: Record<string, any>) => {
    if (chartType !== 'table') {
      return;
    }
    if ('params' in changedValues && selectedDataSource) {
      setParamsChangedAfterProbe(true);
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
    if (!displayColumnsError) {
      return;
    }

    const hasVisibleColumn = displayColumns
      .map((col) => ({
        ...col,
        key: (col.key || '').trim(),
      }))
      .some((col) => col.key && col.visible !== false);

    if (hasVisibleColumn) {
      setDisplayColumnsError('');
    }
  }, [displayColumns, displayColumnsError]);

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
        setDisplayColumnsError('');
        const tableConfig: TableConfig = {};

        if (filterFields.length > 0) {
          tableConfig.filterFields = filterFields
            .filter((f) => f.key)
            .map(({ key, label, inputType }) => ({
              key,
              label,
              inputType,
            }));
        }

        const validDisplayColumns = displayColumns
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
          setDisplayColumnsError(
            t('dashboard.atLeastOneVisibleColumn') || '请至少保留一列可见',
          );
          return;
        }

        if (validDisplayColumns.length > 0) {
          tableConfig.columns = validDisplayColumns.map((col, index) => ({
            key: col.key,
            title: col.title,
            visible: col.visible,
            order: index,
          }));
        }

        if (tableConfig.filterFields?.length || tableConfig.columns?.length) {
          values.tableConfig = tableConfig;
        }
      }

      onConfirm?.(values);
    } catch (error) {
      console.error('Form validation failed:', error);
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
            includeFilterTypes={['params', 'fixed', 'filter']}
          />
        </div>

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
          <div className="mb-6">
            <div
              className="font-bold text-(--color-text-1) mb-4"
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <span>{t('dashboard.tableSettings')}</span>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div
                style={{
                  marginBottom: '8px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span
                  style={{
                    fontWeight: 500,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span>{t('dashboard.displayColumns')}</span>
                  {invalidConfiguredFieldKeys.length > 0 && (
                    <Tooltip
                      title={(
                        t('dashboard.invalidConfiguredFieldsTip') ||
                        '部分已配置字段不在当前可用字段集合中，可能不可用：{{fields}}'
                      ).replace(
                        '{{fields}}',
                        invalidConfiguredFieldKeys.join('、'),
                      )}
                    >
                      <ExclamationCircleOutlined
                        style={{ color: '#faad14', fontSize: 14 }}
                      />
                    </Tooltip>
                  )}
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Tooltip
                    title={
                      t('dashboard.reProbeColumnsTip') ||
                      '将基于当前数据源和参数重新探测并恢复默认列，同时保留已有自定义列'
                    }
                  >
                    <Button
                      size="small"
                      onClick={handleReProbeColumns}
                      loading={isProbingColumns}
                      type={paramsChangedAfterProbe ? 'primary' : 'default'}
                    >
                      {t('dashboard.reProbeColumns') || '重新探测列'}
                    </Button>
                  </Tooltip>
                  <Button
                    type="dashed"
                    size="small"
                    icon={<PlusCircleOutlined />}
                    onClick={() =>
                      setDisplayColumns([
                        ...displayColumns,
                        createDefaultDisplayColumn(),
                      ])
                    }
                  >
                    {t('common.add')}
                  </Button>
                </div>
              </div>
              {displayColumns.length > 0 ? (
                <CustomTable
                  rowKey="id"
                  columns={displayColumnTableColumns}
                  dataSource={displayColumns}
                  pagination={false}
                  scroll={{ y: 320 }}
                  rowDraggable
                  onRowDragEnd={(targetTableData) =>
                    handleDisplayColumnDragEnd(
                      (targetTableData || []) as DisplayColumnRow[],
                    )
                  }
                />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    t('dashboard.noDisplayColumns') ||
                    t('dashboard.displayColumns')
                  }
                />
              )}
              {displayColumnsError && (
                <div
                  style={{
                    color: 'var(--ant-color-error)',
                    fontSize: 12,
                    marginTop: 8,
                  }}
                >
                  {displayColumnsError}
                </div>
              )}
            </div>

            <div>
              <div
                style={{
                  marginBottom: '8px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ fontWeight: 500 }}>
                  {t('dashboard.filterFields')}
                </span>
                <Button
                  type="dashed"
                  size="small"
                  icon={<PlusCircleOutlined />}
                  onClick={() =>
                    setFilterFields([
                      ...filterFields,
                      createDefaultFilterField(),
                    ])
                  }
                  disabled={filterFieldOptions.length === 0}
                >
                  {t('common.add')}
                </Button>
              </div>
              {filterFieldOptions.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('dashboard.noSchemaFields')}
                />
              ) : filterFields.length > 0 ? (
                <CustomTable
                  rowKey="id"
                  columns={filterFieldColumns}
                  dataSource={filterFields}
                  pagination={false}
                  scroll={{ y: 320 }}
                />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('dashboard.noFilterFields')}
                />
              )}
            </div>
          </div>
        )}
      </Form>
    </Drawer>
  );
};

export default ViewConfig;
