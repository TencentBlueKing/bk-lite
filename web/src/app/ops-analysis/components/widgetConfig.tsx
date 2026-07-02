import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import {
  ViewConfigProps,
  ViewConfigItem,
  TableConfig,
  UnifiedFilterDefinition,
  FilterBindings,
  ValueConfig,
  FilterValue,
  WidgetConfig,
  DashboardActionConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  Drawer,
  Button,
  Form,
  Input,
  Radio,
  Select,
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
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import {
  filterNetworkTopologyModelOptions,
  getNetworkTopologyModelIds,
} from '@/app/ops-analysis/utils/networkTopologyModels';
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
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { initThresholdColors } from '@/app/ops-analysis/utils/thresholdUtils';
import ComponentSelector from './widgetSelector';
import type { NetworkStatusTopologyConfig } from '@/app/ops-analysis/types/sceneWidget';

import { useTableConfig } from './widgetConfig/hooks/useTableConfig';
import { TableSettingsSection } from './widgetConfig/sections/tableSettingsSection';
import { TopNSettingsSection } from './widgetConfig/sections/topNSettingsSection';
import { GaugeSettingsSection } from './widgetConfig/sections/gaugeSettingsSection';
import {
  buildDisplayColumnsFromSchema,
  isDisplayableDefaultField,
} from './widgetConfig/utils/columnProbing';
import {
  buildDisplayColumnFieldOptions,
  resolveDatasourceChartTypes,
  shouldShowTableFilterFields,
} from './widgetConfig/utils/tableSettingsBehavior';

interface FormValues {
  name: string;
  description?: string;
  chartType: string;
  sceneWidgetType?: 'networkStatusTopology';
  networkStatusTopology?: NetworkStatusTopologyConfig;
  chartThemeMode?: OpsChartThemeMode;
  dataSource?: string | number;
  compare?: boolean;
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: TableConfig;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  unitId?: string;
  valueMappings?: ValueConfig['valueMappings'];
  conversionFactor?: number;
  decimalPlaces?: number;
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  actions?: DashboardActionConfig[];
}

interface ViewConfigPropsWithManager extends ViewConfigProps {
  dataSourceManager: ReturnType<typeof useDataSourceManager>;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
}

const NETWORK_INSTANCE_PAGE_SIZE = 100;
const SELECT_SCROLL_LOAD_OFFSET = 24;

interface SelectOption {
  label: string;
  value: string;
}

const mergeSelectOptions = (
  previous: SelectOption[],
  next: SelectOption[],
): SelectOption[] => {
  const optionMap = new Map(previous.map((item) => [item.value, item]));
  next.forEach((item) => optionMap.set(item.value, item));
  return Array.from(optionMap.values());
};

const ViewConfig: React.FC<ViewConfigPropsWithManager> = ({
  open,
  item: widgetItem,
  onConfirm,
  onClose,
  dataSourceManager,
  filterDefinitions = [],
  unifiedFilterValues = {},
  builtinNamespaceId,
  showChartThemeMode = false,
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [form] = Form.useForm();
  const handleClose = () => guardClose(form.isFieldsTouched(), onClose);
  const [chartType, setChartType] = useState<string>('');
  const [filterBindings, setFilterBindings] = useState<FilterBindings>({});
  const [actions, setActions] = useState<DashboardActionConfig[]>([]);
  const [dataSourceSelectorVisible, setDataSourceSelectorVisible] = useState(false);
  const { getSourceDataByApiId } = useDataSourceApi();
  const { getModelList, getModelAssociations } = useModelApi();
  const { searchInstances } = useInstanceApi();
  const [networkModelOptions, setNetworkModelOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [networkInstanceOptions, setNetworkInstanceOptions] = useState<SelectOption[]>([]);
  const [networkModelsLoading, setNetworkModelsLoading] = useState(false);
  const [networkInstancesLoading, setNetworkInstancesLoading] = useState(false);
  const [networkInstancePage, setNetworkInstancePage] = useState(1);
  const [networkInstanceTotal, setNetworkInstanceTotal] = useState(0);
  const [networkInstanceKeyword, setNetworkInstanceKeyword] = useState('');
  const networkInstanceRequestIdRef = useRef(0);
  const networkInstanceSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sceneModelId = Form.useWatch(['networkStatusTopology', 'modelId'], form);

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
    return resolveDatasourceChartTypes({
      chartTypes: dataSource.chart_type,
      chartTypeDefinitions: getChartTypeList(),
    });
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
  const effectiveNamespaceId = useMemo(() => {
    if (builtinNamespaceId !== undefined) {
      return builtinNamespaceId;
    }

    return selectedDataSource?.namespaces?.[0];
  }, [builtinNamespaceId, selectedDataSource?.namespaces]);

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
    builtinNamespaceId: effectiveNamespaceId,
    t,
  });
  const isTableLikeChartType =
    chartType === 'table' || chartType === 'eventTable';
  const isNetworkStatusTopology =
    chartType === 'networkStatusTopology' ||
    form.getFieldValue('sceneWidgetType') === 'networkStatusTopology';

  const singleValueConfig = useSingleValueConfig({
    form,
    selectedDataSource,
    getSourceDataByApiId,
    builtinNamespaceId: effectiveNamespaceId,
    open,
  });

  /** 用户通过弹窗选择了新的数据源，重置所有依赖配置 */
  const handleDataSourceChangeFromSelector = useCallback(
    async (item: DatasourceItem) => {
      setDataSourceSelectorVisible(false);

      // 重置依赖字段
      setChartType('');
      setFilterBindings({});
      setActions([]);
      tableConfig.resetTableConfig();
      singleValueConfig.resetSingleValueConfig();

      // 加载完整数据源（brief 模式不含 params）
      const fullItem = (await ensureDataSource(item.id)) || item;

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
        const previewDefs = computePreviewDefinitions(
          filterDefinitions,
          fullItem,
        );
        setFilterBindings(
          buildDefaultFilterBindings(fullItem.params, previewDefs),
        );
      }

      // 如果默认图表类型是 table-like，尝试探测列
      if (defaultChartType === 'table' || defaultChartType === 'eventTable') {
        const schemaFields = fullItem.field_schema;
        if (schemaFields && schemaFields.length > 0) {
          tableConfig.setDetectedDisplayColumns(
            buildDisplayColumnsFromSchema(schemaFields),
          );
        } else {
          const probedColumns = await tableConfig.probeDefaultDisplayColumns(
            fullItem,
            params,
          );
          tableConfig.setDetectedDisplayColumns(probedColumns);
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

  const displayColumnOptions = useMemo(
    () =>
      buildDisplayColumnFieldOptions({
        availableFields,
        displayColumns: tableConfig.displayColumns,
        detectedColumns: tableConfig.detectedDisplayColumns,
      }),
    [
      availableFields,
      tableConfig.displayColumns,
      tableConfig.detectedDisplayColumns,
    ],
  );

  const showTableFilterFields = useMemo(
    () => shouldShowTableFilterFields(chartType),
    [chartType],
  );

  const filterFieldOptions = useMemo(() => {
    if (!showTableFilterFields) {
      return [];
    }

    return displayColumnOptions;
  }, [displayColumnOptions, showTableFilterFields]);

  const invalidConfiguredFieldKeys = useMemo(() => {
    const availableFieldKeySet = new Set([
      ...availableFields.map((field) => field.key),
      ...tableConfig.detectedDisplayColumns
        .map((col) => (col.key || '').trim())
        .filter(Boolean),
    ]);

    if (availableFieldKeySet.size === 0) {
      return [];
    }

    const configuredKeys = [
      ...tableConfig.displayColumns.map((col) => (col.key || '').trim()),
      ...(showTableFilterFields
        ? tableConfig.filterFields.map((field) => (field.key || '').trim())
        : []),
    ]
      .filter(Boolean)
      .filter((key) => {
        const column = tableConfig.displayColumns.find(
          (col) => (col.key || '').trim() === key,
        );
        return column?.columnType !== 'actions';
      });

    return Array.from(
      new Set(configuredKeys.filter((key) => !availableFieldKeySet.has(key))),
    );
  }, [
    availableFields,
    tableConfig.displayColumns,
    tableConfig.filterFields,
    showTableFilterFields,
  ]);

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
    const isSceneWidget =
      valueConfig?.sceneWidgetType === 'networkStatusTopology' ||
      valueConfig?.chartType === 'networkStatusTopology';
    const formValues: FormValues = {
      name: widgetItem?.name || '',
      description: widgetItem.description || '',
      chartType: valueConfig?.chartType || '',
      sceneWidgetType: valueConfig?.sceneWidgetType,
      networkStatusTopology: valueConfig?.networkStatusTopology,
      chartThemeMode: showChartThemeMode
        ? valueConfig?.chartThemeMode || 'default'
        : undefined,
      dataSource: valueConfig?.dataSource || '',
      dataSourceParams: valueConfig?.dataSourceParams || [],
      params: {},
      tableConfig: valueConfig?.tableConfig,
      actions: valueConfig?.actions || [],
    };
    setChartType(formValues.chartType);
    setActions(valueConfig?.actions || []);

    if (isSceneWidget) {
      const networkStatusTopology = valueConfig?.networkStatusTopology || {
        modelId: '',
        instId: '',
        depth: 2,
      };
      setSelectedDataSource(undefined);
      setFilterBindings({});
      tableConfig.resetTableConfig();
      singleValueConfig.resetSingleValueConfig();
      form.setFieldsValue({
        ...formValues,
        chartType: 'networkStatusTopology',
        sceneWidgetType: 'networkStatusTopology',
        dataSource: undefined,
        networkStatusTopology,
      });
      return;
    }

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

        tableConfig.setDetectedDisplayColumns(
          (targetDataSource?.field_schema || []).length > 0
            ? buildDisplayColumnsFromSchema(
              targetDataSource?.field_schema || [],
            )
            : probedColumns,
        );

        const fieldTitleMap = new Map<string, string>();
        (targetDataSource?.field_schema || []).forEach((field) => {
          if (field.key) {
            fieldTitleMap.set(field.key, field.title || field.key);
          }
        });
        probedColumns.forEach((column) => {
          if (column.key && !fieldTitleMap.has(column.key)) {
            fieldTitleMap.set(column.key, column.title || column.key);
          }
        });

        tableConfig.setDisplayColumns(
          valueConfig.tableConfig.columns.map((c, idx) => ({
            ...c,
            id: `column_${idx}_${Date.now()}`,
            title:
              !c.title || c.title === c.key
                ? fieldTitleMap.get(c.key) || c.title || c.key
                : c.title,
            isDefault:
              schemaDefaultKeys.has(c.key) || probeDefaultKeys.has(c.key),
          })),
        );
      }

      if (
        !valueConfig?.tableConfig?.columns?.length &&
        (formValues.chartType === 'table' ||
          formValues.chartType === 'eventTable')
      ) {
        const schemaFields = targetDataSource?.field_schema;
        if (schemaFields && schemaFields.length > 0) {
          tableConfig.setDetectedDisplayColumns(
            buildDisplayColumnsFromSchema(schemaFields),
          );
        } else {
          const probedColumns = await tableConfig.probeDefaultDisplayColumns(
            targetDataSource,
            formValues.params || {},
          );
          tableConfig.setDetectedDisplayColumns(probedColumns);
        }
      }
    } else {
      setSelectedDataSource(undefined);
      if (!valueConfig?.tableConfig?.columns?.length) {
        tableConfig.setDisplayColumns([]);
      }
      tableConfig.setDetectedDisplayColumns([]);
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
    if ((valueConfig as ValueConfig | undefined)?.unitId !== undefined) {
      formValues.unitId = (valueConfig as ValueConfig).unitId;
    }
    if ((valueConfig as ValueConfig | undefined)?.valueMappings !== undefined) {
      formValues.valueMappings = (valueConfig as ValueConfig).valueMappings;
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
    setActions([]);
    setDataSourceSelectorVisible(false);
    setNetworkInstanceOptions([]);
    tableConfig.resetTableConfig();
    singleValueConfig.resetSingleValueConfig();
  };

  useEffect(() => {
    if (!open || !isNetworkStatusTopology || networkModelOptions.length > 0) {
      return;
    }

    let cancelled = false;
    const fetchModels = async () => {
      try {
        setNetworkModelsLoading(true);
        const [models, associations] = await Promise.all([
          getModelList(),
          getModelAssociations('interface'),
        ]);
        if (cancelled) return;
        setNetworkModelOptions(
          filterNetworkTopologyModelOptions(
            Array.isArray(models) ? models : [],
            getNetworkTopologyModelIds(
              Array.isArray(associations) ? associations : [],
            ),
          ),
        );
      } catch (error) {
        console.error('获取模型列表失败:', error);
        if (!cancelled) setNetworkModelOptions([]);
      } finally {
        if (!cancelled) setNetworkModelsLoading(false);
      }
    };

    void fetchModels();
    return () => {
      cancelled = true;
    };
    // API hooks return fresh function references; this load is driven by panel/component state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNetworkStatusTopology, networkModelOptions.length, open]);

  const fetchNetworkInstances = async ({
    page,
    keyword,
    append,
  }: {
    page: number;
    keyword: string;
    append: boolean;
  }) => {
    if (!sceneModelId) return;

    const requestId = networkInstanceRequestIdRef.current + 1;
    networkInstanceRequestIdRef.current = requestId;
    setNetworkInstancesLoading(true);

    try {
      const trimmedKeyword = keyword.trim();
      const instanceRes = await searchInstances({
        model_id: sceneModelId,
        query_list: trimmedKeyword
          ? [{ field: 'inst_name', type: 'str*', value: trimmedKeyword }]
          : [],
        page,
        page_size: NETWORK_INSTANCE_PAGE_SIZE,
        order: '',
        role: '',
        case_sensitive: false,
      });

      if (requestId !== networkInstanceRequestIdRef.current) return;

      const nextOptions = (instanceRes?.insts || []).map((instance: any) => {
        const instanceId = instance._id || instance.id;
        return {
          label: String(instance.inst_name || instance.name || instanceId),
          value: String(instanceId),
        };
      });
      setNetworkInstanceOptions((previous) =>
        append ? mergeSelectOptions(previous, nextOptions) : nextOptions,
      );
      setNetworkInstancePage(page);
      setNetworkInstanceTotal(Number(instanceRes?.count) || nextOptions.length);
    } catch (error) {
      console.error('获取网络拓扑实例失败:', error);
      if (requestId === networkInstanceRequestIdRef.current) {
        setNetworkInstanceOptions((previous) => (append ? previous : []));
        setNetworkInstanceTotal((previous) => (append ? previous : 0));
      }
    } finally {
      if (requestId === networkInstanceRequestIdRef.current) {
        setNetworkInstancesLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!open || !isNetworkStatusTopology || !sceneModelId) {
      setNetworkInstanceOptions([]);
      setNetworkInstancePage(1);
      setNetworkInstanceTotal(0);
      setNetworkInstanceKeyword('');
      return;
    }

    setNetworkInstanceOptions([]);
    setNetworkInstancePage(1);
    setNetworkInstanceTotal(0);
    setNetworkInstanceKeyword('');
    void fetchNetworkInstances({ page: 1, keyword: '', append: false });
    // API hooks return fresh function references; this load is driven by model/panel state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isNetworkStatusTopology,
    open,
    sceneModelId,
  ]);

  useEffect(() => {
    return () => {
      if (networkInstanceSearchTimerRef.current) {
        clearTimeout(networkInstanceSearchTimerRef.current);
      }
    };
  }, []);

  const handleNetworkInstanceSearch = (keyword: string) => {
    setNetworkInstanceKeyword(keyword);
    if (networkInstanceSearchTimerRef.current) {
      clearTimeout(networkInstanceSearchTimerRef.current);
    }
    networkInstanceSearchTimerRef.current = setTimeout(() => {
      setNetworkInstanceOptions([]);
      setNetworkInstancePage(1);
      setNetworkInstanceTotal(0);
      void fetchNetworkInstances({ page: 1, keyword, append: false });
    }, 300);
  };

  const handleNetworkInstancePopupScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const hasMore = networkInstanceOptions.length < networkInstanceTotal;
    const isNearBottom =
      target.scrollTop + target.offsetHeight >=
      target.scrollHeight - SELECT_SCROLL_LOAD_OFFSET;

    if (!hasMore || networkInstancesLoading || !isNearBottom) {
      return;
    }

    void fetchNetworkInstances({
      page: networkInstancePage + 1,
      keyword: networkInstanceKeyword,
      append: true,
    });
  };

  const handleFormValuesChange = (changedValues: Record<string, any>) => {
    if (!isTableLikeChartType) {
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
      if (values.sceneWidgetType === 'networkStatusTopology') {
        const topologyConfig = values.networkStatusTopology;
        onConfirm?.({
          name: values.name,
          description: values.description,
          chartType: 'networkStatusTopology',
          sceneWidgetType: 'networkStatusTopology',
          networkStatusTopology: {
            modelId: topologyConfig?.modelId || '',
            instId: topologyConfig?.instId || '',
            depth: topologyConfig?.depth || 2,
          },
        });
        return;
      }

      if (selectedDataSource?.params?.length) {
        const formParams = values.params || form.getFieldValue('params') || {};
        values.dataSourceParams = processFormParamsForSubmit(
          formParams,
          selectedDataSource.params,
        );
        delete values.params;
      }

      if (isTableLikeChartType) {
        tableConfig.setDisplayColumnsError('');
        const tableConfigData: TableConfig = {};

        if (showTableFilterFields && tableConfig.filterFields.length > 0) {
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
            columnType: col.columnType,
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
      if (!showChartThemeMode) {
        delete result.chartThemeMode;
      } else if (result.chartThemeMode === 'default') {
        delete result.chartThemeMode;
      }

      if (chartType === 'table') {
        const displayColumnKeys = new Set(
          tableConfig.displayColumns
            .map((col) => (col.key || '').trim())
            .filter(Boolean),
        );
        const validActions = actions.filter((action) =>
          displayColumnKeys.has(action.columnKey),
        );
        if (validActions.length > 0) {
          result.actions = validActions;
        }
      }

      if (chartType === 'single') {
        result.selectedFields = singleValueConfig.selectedFields;
        result.thresholdColors = singleValueConfig.thresholdColors;
        result.compare = !!values.compare;
        const unitValue = form.getFieldValue('unit');
        const conversionFactorValue = form.getFieldValue('conversionFactor');
        const decimalPlacesValue = form.getFieldValue('decimalPlaces');
        if (unitValue !== undefined) result.unit = unitValue;
        result.unitId = form.getFieldValue('unitId') || undefined;
        result.valueMappings = form.getFieldValue('valueMappings') || undefined;
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
        result.unitId = form.getFieldValue('unitId') || undefined;
        result.valueMappings = form.getFieldValue('valueMappings') || undefined;
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
      maskClosable={false}
      onClose={handleClose}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button type="primary" onClick={handleConfirm}>
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={handleClose}>
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
          <Form.Item name="sceneWidgetType" hidden>
            <Input />
          </Form.Item>
          {isNetworkStatusTopology ? (
            <>
              <Form.Item
                label={t('dashboard.networkTopoModel')}
                name={['networkStatusTopology', 'modelId']}
                rules={[{ required: true, message: t('dashboard.selectModel') }]}
                tooltip={t('dashboard.networkTopoModelHelp')}
              >
                <Select
                  showSearch
                  loading={networkModelsLoading}
                  placeholder={t('dashboard.selectModel')}
                  options={networkModelOptions}
                  optionFilterProp="label"
                  notFoundContent={
                    networkModelsLoading
                      ? undefined
                      : t('dashboard.networkTopoNoSupportedModel')
                  }
                  onChange={() => {
                    form.setFieldValue(['networkStatusTopology', 'instId'], undefined);
                    setNetworkInstanceOptions([]);
                    setNetworkInstancePage(1);
                    setNetworkInstanceTotal(0);
                    setNetworkInstanceKeyword('');
                  }}
                />
              </Form.Item>
              <Form.Item
                label={t('dashboard.networkTopoInstance')}
                name={['networkStatusTopology', 'instId']}
                rules={[{ required: true, message: t('dashboard.selectInstance') }]}
                tooltip={t('dashboard.networkTopoInstanceHelp')}
              >
                <Select
                  showSearch
                  loading={networkInstancesLoading}
                  placeholder={t('dashboard.selectInstance')}
                  options={networkInstanceOptions}
                  filterOption={false}
                  disabled={!sceneModelId}
                  notFoundContent={
                    networkInstancesLoading ? t('common.loading') : t('dashboard.noData')
                  }
                  onSearch={handleNetworkInstanceSearch}
                  onPopupScroll={handleNetworkInstancePopupScroll}
                />
              </Form.Item>
              <Form.Item
                label={t('dashboard.expandDepth')}
                name={['networkStatusTopology', 'depth']}
                initialValue={2}
              >
                <Select
                  options={[
                    { label: '1', value: 1 },
                    { label: '2', value: 2 },
                    { label: '3', value: 3 },
                    { label: '4', value: 4 },
                  ]}
                />
              </Form.Item>
            </>
          ) : (
            <>
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
            </>
          )}
          {showChartThemeMode && !isNetworkStatusTopology && (
            <Form.Item
              label={t('dashboard.chartThemeMode')}
              name="chartThemeMode"
              initialValue="default"
            >
              <Select
                options={[
                  {
                    label: t('dashboard.chartThemeModeDefault'),
                    value: 'default',
                  },
                  {
                    label: t('dashboard.chartThemeModeScreenDark'),
                    value: 'screen-dark',
                  },
                  {
                    label: t('dashboard.chartThemeModeScreenLight'),
                    value: 'screen-light',
                  },
                ]}
              />
            </Form.Item>
          )}
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

        {isTableLikeChartType && (
          <TableSettingsSection
            t={t}
            displayColumns={tableConfig.displayColumns}
            displayColumnOptions={displayColumnOptions}
            actions={actions}
            filterFields={tableConfig.filterFields}
            filterFieldOptions={filterFieldOptions}
            showFilterFields={showTableFilterFields}
            invalidConfiguredFieldKeys={invalidConfiguredFieldKeys}
            isProbingColumns={tableConfig.isProbingColumns}
            paramsChangedAfterProbe={tableConfig.paramsChangedAfterProbe}
            displayColumnsError={tableConfig.displayColumnsError}
            onAddFilterField={tableConfig.handleAddFilterField}
            onDeleteFilterField={tableConfig.handleDeleteFilterField}
            onFilterFieldChange={tableConfig.handleFilterFieldChange}
            onAddDisplayColumn={tableConfig.handleAddDisplayColumn}
            onDeleteDisplayColumn={(id) => {
              const deletingColumn = tableConfig.displayColumns.find(
                (column) => column.id === id,
              );
              tableConfig.handleDeleteDisplayColumn(id);
              if (deletingColumn?.columnType === 'actions') {
                setActions((prev) =>
                  prev.filter(
                    (action) =>
                      action.columnKey !== deletingColumn.key,
                  ),
                );
              }
            }}
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
            onAddNewDisplayColumn={(columnType = 'data') =>
              tableConfig.setDisplayColumns([
                ...tableConfig.displayColumns,
                columnType === 'actions'
                  ? tableConfig.createDefaultOperationColumn()
                  : tableConfig.createDefaultDisplayColumn(),
              ])
            }
            onActionsChange={setActions}
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
