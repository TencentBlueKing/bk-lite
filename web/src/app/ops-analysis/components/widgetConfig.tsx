import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { markFormPristine } from '@/utils/formPristine';
import {
  ViewConfigProps,
  ViewConfigItem,
  UnifiedFilterDefinition,
  FilterBindings,
  ValueConfig,
  FilterValue,
  DashboardActionConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  Drawer,
  Button,
  Form,
  Input,
  Radio,
  Select,
  Segmented,
  Tooltip,
  Checkbox,
  InputNumber,
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
import { ParamInputConfigEditor } from '@/app/ops-analysis/components/paramInputConfigEditor';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  getFilterDefinitionId,
  getBindableFilterParams,
  buildDefaultFilterBindings,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import { canEnableCompare } from '@/app/ops-analysis/utils/compareQuery';
import {
  clearComponentParamSwitch,
  findComponentSwitchParams,
  reconcileComponentParamValue,
  supportsComponentSwitch,
} from '@/app/ops-analysis/utils/componentParamSwitch';
import type {
  DatasourceItem,
  InputControlConfig,
  InputOption,
  ParamItem,
  ResponseFieldDefinition,
} from '@/app/ops-analysis/types/dataSource';
import { initThresholdColors } from '@/app/ops-analysis/utils/thresholdUtils';
import { ValueFormatConfigSection } from '@/app/ops-analysis/components/ops-analysis-config-sections';
import { ThresholdColorConfigSection } from '@/app/ops-analysis/components/thresholdColorConfigSection';
import { ValueMappingsConfigSection } from '@/app/ops-analysis/components/valueMappingsConfigSection';
import ComponentSelector from './widgetSelector';

import { useTableConfig } from './widgetConfig/hooks/useTableConfig';
import { TableSettingsSection } from './widgetConfig/sections/tableSettingsSection';
import { TopNSettingsSection } from './widgetConfig/sections/topNSettingsSection';
import { GaugeSettingsSection } from './widgetConfig/sections/gaugeSettingsSection';
import { RadarSettingsSection } from './widgetConfig/sections/radarSettingsSection';
import { CardListSettingsSection } from './widgetConfig/sections/cardListSettingsSection';
import { ThresholdColorListField } from './widgetConfig/sections/thresholdColorListField';
import { resolveCardListSettingsRemountKey } from './widgetConfig/utils/cardListSettingsRemountKey';
import {
  buildDisplayColumnsFromSchema,
  isDisplayableDefaultField,
} from './widgetConfig/utils/columnProbing';
import {
  buildDisplayColumnFieldOptions,
  resolveDatasourceChartTypes,
  shouldShowTableFilterFields,
} from './widgetConfig/utils/tableSettingsBehavior';
import {
  buildWidgetSubmitConfig,
  type WidgetConfigFormValues,
} from './widgetConfig/utils/submitConfig';
import { useNetworkStatusTopologyConfig } from './widgetConfig/hooks/useNetworkStatusTopologyConfig';
import { NetworkStatusTopologyDeviceList } from './widgetConfig/sections/networkStatusTopologyDeviceList';
import {
  canConfigureScreenWidgetFrame,
  getDefaultScreenWidgetAppearance,
  resolveScreenWidgetAppearance,
} from '@/app/ops-analysis/(pages)/view/screen/utils/layoutUtils';
import { ensurePrometheusQueryRequired } from '@/app/ops-analysis/utils/dataSourceParamContract';
import {
  coerceValueForMultiple,
  isMultipleSelectInputConfig,
  migrateParamItemsFromStringList,
  normalizeDatasourceItemParams,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';
import {
  NETWORK_STATUS_TOPOLOGY_MAX_NODE_LIMIT,
  networkStatusTopologySelectionExceedsLimit,
} from '@/app/ops-analysis/utils/networkStatusTopologyLayout';

interface ViewConfigPropsWithManager extends ViewConfigProps {
  dataSourceManager: ReturnType<typeof useDataSourceManager>;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
}

const NETWORK_STATUS_TOPOLOGY = 'networkStatusTopology';
const VALUE_FORMAT_CHART_TYPES = new Set(['line', 'bar', 'pie', 'multiValue']);

interface SelectorLike {
  id?: unknown;
  chartType?: unknown;
  sceneWidgetType?: unknown;
}

const isSceneWidgetSelection = (item?: SelectorLike | null): boolean => {
  if (!item) return false;

  return (
    item.sceneWidgetType === NETWORK_STATUS_TOPOLOGY ||
    item.chartType === NETWORK_STATUS_TOPOLOGY ||
    item.id === `scene:${NETWORK_STATUS_TOPOLOGY}`
  );
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
  surface = 'dashboard',
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [form] = Form.useForm();
  const handleClose = () => guardClose(form.isFieldsTouched(), onClose);
  const [chartType, setChartType] = useState<string>('');
  const [filterBindings, setFilterBindings] = useState<FilterBindings>({});
  const [actions, setActions] = useState<DashboardActionConfig[]>([]);
  const [dataSourceSelectorVisible, setDataSourceSelectorVisible] = useState(false);
  const [editingInputConfigParam, setEditingInputConfigParam] = useState<ParamItem | null>(null);
  const [widgetParamOverrides, setWidgetParamOverrides] = useState<ParamItem[]>([]);
  const { getSourceDataByApiId } = useDataSourceApi();
  const configRequestIdRef = useRef(0);
  const resolvedParamOptionsRef = useRef(new Map<string, InputOption[]>());

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
  ): ChartTypeItem[] =>
    resolveDatasourceChartTypes({
      chartTypes: dataSource?.chart_type || [],
      chartTypeDefinitions: getChartTypeList(),
      surface,
    });

  const getDataSourceChartTypes = useMemo(() => {
    return getFilteredChartTypes(selectedDataSource);
  }, [selectedDataSource, surface]);

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

  const canonicalSelectedDataSource = useMemo(
    () => (
      selectedDataSource
        ? normalizeDatasourceItemParams(selectedDataSource)
        : undefined
    ),
    [selectedDataSource],
  );

  const previewFilterDefinitions = useMemo(
    () => computePreviewDefinitions(filterDefinitions, canonicalSelectedDataSource),
    [canonicalSelectedDataSource, filterDefinitions],
  );

  const queryConfigParams = useMemo(
    () =>
      (Array.isArray(canonicalSelectedDataSource?.params)
        ? canonicalSelectedDataSource.params
        : []
      ).filter((param: ParamItem) =>
        ['params', 'fixed'].includes(param.filterType || 'fixed'),
      ),
    [canonicalSelectedDataSource?.params],
  );

  const bindableFilterParams = useMemo(
    () =>
      Array.isArray(canonicalSelectedDataSource?.params)
        ? getBindableFilterParams(canonicalSelectedDataSource.params)
        : [],
    [canonicalSelectedDataSource?.params],
  );

  const hasQueryParams = queryConfigParams.length > 0;
  const shouldShowUnifiedFilterSection =
    previewFilterDefinitions.length > 0 && Boolean(canonicalSelectedDataSource?.params);
  const hasUnifiedFilterBindings = bindableFilterParams.length > 0;
  const effectiveNamespaceId = useMemo(() => {
    if (builtinNamespaceId !== undefined) {
      return builtinNamespaceId;
    }

    return canonicalSelectedDataSource?.namespaces?.[0];
  }, [builtinNamespaceId, canonicalSelectedDataSource?.namespaces]);

  const tableConfig = useTableConfig({
    form,
    chartType,
    selectedDataSource: canonicalSelectedDataSource,
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
  const networkTopologyConfig = useNetworkStatusTopologyConfig({
    open,
    enabled: isNetworkStatusTopology,
    form,
  });
  const networkTopoNodeLimit = Form.useWatch(
    ['networkStatusTopology', 'nodeLimit'],
    form,
  );

  const singleValueConfig = useSingleValueConfig({
    form,
    selectedDataSource: canonicalSelectedDataSource,
    getSourceDataByApiId,
    builtinNamespaceId: effectiveNamespaceId,
    open,
  });

  const nextConfigRequestId = useCallback(() => {
    configRequestIdRef.current += 1;
    return configRequestIdRef.current;
  }, []);

  const isCurrentConfigRequest = useCallback(
    (requestId: number) => requestId === configRequestIdRef.current,
    [],
  );

  /** 用户通过弹窗选择了新的数据源，重置所有依赖配置 */
  const handleDataSourceChangeFromSelector = useCallback(
    async (item: DatasourceItem) => {
      const requestId = nextConfigRequestId();
      resolvedParamOptionsRef.current.clear();
      setDataSourceSelectorVisible(false);

      if (isSceneWidgetSelection(item)) {
        setChartType(NETWORK_STATUS_TOPOLOGY);
        setSelectedDataSource(undefined);
        setFilterBindings({});
        setActions([]);
        setWidgetParamOverrides([]);
        tableConfig.resetTableConfig();
        singleValueConfig.resetSingleValueConfig();

        form.setFieldsValue({
          chartType: NETWORK_STATUS_TOPOLOGY,
          sceneWidgetType: NETWORK_STATUS_TOPOLOGY,
          appearance:
            surface === 'screen'
              ? getDefaultScreenWidgetAppearance(NETWORK_STATUS_TOPOLOGY)
              : undefined,
          dataSource: undefined,
          networkStatusTopology: {
            instUuids: [],
            nodeLimit: 100,
            linkTrafficDisplays: ['inbound', 'outbound'],
          },
          params: {},
          dataSourceParams: [],
          selectedFields: [],
          topNLabelField: undefined,
          topNValueField: undefined,
          unit: undefined,
          unitId: undefined,
          valueMappings: undefined,
          conversionFactor: undefined,
          decimalPlaces: undefined,
          gaugeMin: 0,
          gaugeMax: 100,
          gaugeShape: 'semicircle',
          eventTimeline: {
            sortOrder: 'desc',
          },
          radar: {
            min: 0,
            max: 100,
            indicators: [],
          },
          cardList: {
            leading: { type: 'none' },
            layout: 'list',
          },
          compare: false,
          compareMode: 'percent',
          tableConfig: undefined,
          actions: [],
        });
        return;
      }

      // 重置依赖字段
      setChartType('');
      setFilterBindings({});
      setActions([]);
      setWidgetParamOverrides([]);
      tableConfig.resetTableConfig();
      singleValueConfig.resetSingleValueConfig();

      // 加载完整数据源（brief 模式不含 params）
      const fullItem = normalizeDatasourceItemParams(
        ((await ensureDataSource(item.id)) || item) as DatasourceItem,
      );
      if (!isCurrentConfigRequest(requestId)) {
        return;
      }

      // 设置新数据源
      setSelectedDataSource(fullItem);
      const newChartTypes = getFilteredChartTypes(fullItem);
      const defaultChartType = newChartTypes[0]?.value || '';

      setChartType(defaultChartType);
      if (defaultChartType === 'multiValue') {
        singleValueConfig.setThresholdColors(initThresholdColors([]));
      }

      // 重置 form 中的依赖字段
      const params: Record<string, any> = {};
      if (fullItem.params?.length) {
        setDefaultParamValues(fullItem.params, params);
      }

      form.setFieldsValue({
        dataSource: fullItem.id,
        chartType: defaultChartType,
        appearance:
          surface === 'screen'
            ? getDefaultScreenWidgetAppearance(defaultChartType)
            : undefined,
        sceneWidgetType: undefined,
        networkStatusTopology: undefined,
        params,
        selectedFields: [],
        topNLabelField: undefined,
        topNValueField: undefined,
        unit: undefined,
        unitId: undefined,
        valueMappings: undefined,
        conversionFactor: undefined,
        decimalPlaces: undefined,
        gaugeMin: 0,
        gaugeMax: 100,
        gaugeShape: 'semicircle',
        eventTimeline: {
          sortOrder: 'desc',
        },
        radar: {
          min: 0,
          max: 100,
          indicators: [],
        },
        cardList: {
          leading: { type: 'none' },
          layout: 'list',
        },
        compare: false,
        compareMode: 'percent',
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
          if (!isCurrentConfigRequest(requestId)) {
            return;
          }
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
      nextConfigRequestId,
      isCurrentConfigRequest,
      surface,
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
    form.setFieldValue('chartType', newChartType);
    if (newChartType === 'eventTimeline' && !form.getFieldValue('eventTimeline')) {
      form.setFieldValue('eventTimeline', { sortOrder: 'desc' });
    }
    if (newChartType === 'radar' && !form.getFieldValue('radar')) {
      form.setFieldValue('radar', { min: 0, max: 100, indicators: [] });
    }
    if (newChartType === 'cardList' && !form.getFieldValue('cardList')) {
      form.setFieldValue('cardList', {
        leading: { type: 'none' },
        layout: 'list',
      });
    }
    if (newChartType === 'multiValue') {
      singleValueConfig.setThresholdColors(initThresholdColors([]));
    } else if (newChartType === 'single' || newChartType === 'gauge') {
      singleValueConfig.setThresholdColors((prev) =>
        prev.length > 0 ? prev : initThresholdColors(undefined),
      );
    }
    if (surface === 'screen') {
      form.setFieldValue(
        'appearance',
        getDefaultScreenWidgetAppearance(newChartType),
      );
    }
    if (!supportsComponentSwitch(newChartType)) {
      setWidgetParamOverrides((previous) =>
        previous.map(clearComponentParamSwitch),
      );
    }
    await tableConfig.handleChartTypeChange(newChartType);
  };

  const initializeItemForm = async (
    widgetItem: ViewConfigItem,
    requestId: number,
  ): Promise<void> => {
    resolvedParamOptionsRef.current.clear();
    if (!isCurrentConfigRequest(requestId)) {
      return;
    }

    const { valueConfig } = widgetItem;
    const isSceneWidget =
      valueConfig?.sceneWidgetType === 'networkStatusTopology' ||
      valueConfig?.chartType === 'networkStatusTopology';
    const formValues: WidgetConfigFormValues = {
      name: widgetItem?.name || '',
      description: widgetItem.description || '',
      chartType: valueConfig?.chartType || '',
      sceneWidgetType: valueConfig?.sceneWidgetType,
      networkStatusTopology: valueConfig?.networkStatusTopology,
      chartThemeMode: showChartThemeMode
        ? valueConfig?.chartThemeMode || 'default'
        : undefined,
      appearance:
        surface === 'screen'
          ? resolveScreenWidgetAppearance(
            valueConfig?.chartType,
            valueConfig?.appearance,
          )
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
        instUuids: [],
        nodeLimit: 100,
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
        networkStatusTopology: {
          ...networkStatusTopology,
          linkTrafficDisplays: Array.isArray(networkStatusTopology.linkTrafficDisplays)
            ? networkStatusTopology.linkTrafficDisplays
            : ['inbound', 'outbound'],
        },
      });
      // setFieldsValue 在 rc-field-form 2.x 会标记 touched，初始化后清掉以免误报未保存
      markFormPristine(form);
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

    const loadedDataSource = await ensureDataSource(formValues.dataSource);
    const targetDataSource = loadedDataSource
      ? normalizeDatasourceItemParams(loadedDataSource)
      : undefined;
    if (!isCurrentConfigRequest(requestId)) {
      return;
    }

    if (targetDataSource) {
      setSelectedDataSource(targetDataSource);
      // 从 widget 已有的 dataSourceParams 恢复组件级 inputConfig 覆盖。
      const widgetOverrides = migrateParamItemsFromStringList(
        valueConfig?.dataSourceParams || [],
      ).params
        .filter((p) => p.inputConfig !== undefined)
        .map((p) => ({ ...p, options: undefined }));
      setWidgetParamOverrides(widgetOverrides);
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
        if (!isCurrentConfigRequest(requestId)) {
          return;
        }
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
          if (!isCurrentConfigRequest(requestId)) {
            return;
          }
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

    if ((valueConfig as ValueConfig | undefined)?.descriptionField !== undefined) {
      formValues.descriptionField = (valueConfig as ValueConfig).descriptionField;
    } else {
      formValues.descriptionField = undefined;
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
    if (valueConfig?.eventTimeline !== undefined) {
      formValues.eventTimeline = valueConfig.eventTimeline;
    }
    if (valueConfig?.radar !== undefined) {
      formValues.radar = valueConfig.radar;
    }
    if (valueConfig?.cardList !== undefined) {
      formValues.cardList = {
        ...valueConfig.cardList,
        leading: valueConfig.cardList.leading || { type: 'none' },
        layout: valueConfig.cardList.layout || 'list',
      };
    } else {
      formValues.cardList = {
        leading: { type: 'none' },
        layout: 'list',
      };
    }
    if (valueConfig?.compare !== undefined) {
      formValues.compare = valueConfig.compare && canEnableCompare({
        config: { chartType: 'single', dataSourceParams: targetDataSource?.params },
        dataSource: targetDataSource,
      });
    }
    formValues.compareMode = valueConfig?.compareMode || 'percent';

    singleValueConfig.setThresholdColors(
      formValues.chartType === 'multiValue'
        ? initThresholdColors(valueConfig?.thresholdColors ?? [])
        : initThresholdColors(valueConfig?.thresholdColors),
    );

    // Nested cardList fields are registered individually; reset first so omitted
    // optional slots from the previous edit target cannot survive setFieldsValue merge.
    form.resetFields(['cardList']);
    form.setFieldsValue(formValues);
    // setFieldsValue 在 rc-field-form 2.x 会标记 touched，初始化后清掉以免误报未保存
    markFormPristine(form);
  };

  const resetForm = (): void => {
    form.resetFields();
    setSelectedDataSource(undefined);
    setChartType('');
    setFilterBindings({});
    setActions([]);
    setDataSourceSelectorVisible(false);
    setEditingInputConfigParam(null);
    setWidgetParamOverrides([]);
    networkTopologyConfig.resetInstanceOptions();
    tableConfig.resetTableConfig();
    singleValueConfig.resetSingleValueConfig();
  };

  const handleEditInputConfig = (param: ParamItem) => {
    const override = widgetParamOverrides.find((o) => o.name === param.name);
    setEditingInputConfigParam(override ?? param);
  };

  const reconcileParamWithOptions = useCallback(
    (paramName: string, options: InputOption[]) => {
      if (options.length === 0) return;
      resolvedParamOptionsRef.current.set(paramName, options);
      const currentParams = form.getFieldValue('params') || {};
      const nextValue = reconcileComponentParamValue(currentParams[paramName], options);
      if (nextValue !== currentParams[paramName]) {
        form.setFieldValue(['params', paramName], nextValue);
      }
    },
    [form],
  );

  const handleInputConfigConfirm = (
    newConfig: InputControlConfig,
    resolvedOptions?: InputOption[],
  ) => {
    if (!editingInputConfigParam) return;
    const editingParamName = editingInputConfigParam.name;
    setWidgetParamOverrides((prev) => {
      const existing = prev.find((o) => o.name === editingInputConfigParam.name);
      const baseParam = {
        ...editingInputConfigParam,
        options: undefined,
      };
      if (existing) {
        return prev.map((o) =>
          o.name === editingInputConfigParam.name
            ? { ...baseParam, inputConfig: newConfig }
            : o,
        );
      }
      return [...prev, { ...baseParam, inputConfig: newConfig }];
    });
    const currentParams = form.getFieldValue('params') || {};
    const coerced = coerceValueForMultiple(
      currentParams[editingParamName],
      isMultipleSelectInputConfig(newConfig),
    );
    if (coerced !== currentParams[editingParamName]) {
      form.setFieldValue(['params', editingParamName], coerced);
    }
    if (resolvedOptions?.length) {
      reconcileParamWithOptions(editingParamName, resolvedOptions);
    } else {
      resolvedParamOptionsRef.current.delete(editingParamName);
    }
    setEditingInputConfigParam(null);
  };

  // 把组件级 inputConfig 覆盖合并到 selectedDataSource，供参数表渲染。
  const effectiveDataSource = useMemo(() => {
    if (!selectedDataSource) return undefined;
    const sourceParams =
      canonicalSelectedDataSource.source_type === 'prometheus'
        ? ensurePrometheusQueryRequired(canonicalSelectedDataSource.params)
        : canonicalSelectedDataSource.params;

    if (widgetParamOverrides.length === 0) {
      return sourceParams === selectedDataSource.params
        ? canonicalSelectedDataSource
        : { ...canonicalSelectedDataSource, params: sourceParams };
    }
    return {
      ...canonicalSelectedDataSource,
      params: sourceParams.map((p) => {
        const override = widgetParamOverrides.find((o) => o.name === p.name);
        return override?.inputConfig !== undefined
          ? { ...p, inputConfig: override.inputConfig }
          : p;
      }),
    };
  }, [canonicalSelectedDataSource, widgetParamOverrides]);

  const componentSwitchOwner = useMemo(() => {
    const owner = findComponentSwitchParams(effectiveDataSource?.params)[0];
    return owner
      ? { name: owner.name, label: owner.alias_name || owner.name }
      : undefined;
  }, [effectiveDataSource]);

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
      if (!widgetItem) {
        return;
      }
      const requestId = nextConfigRequestId();
      void initializeItemForm(widgetItem, requestId);
    } else if (!open) {
      nextConfigRequestId();
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
      const values: WidgetConfigFormValues = await form.validateFields();

      if (
        values.sceneWidgetType !== 'networkStatusTopology' &&
        effectiveDataSource?.params?.length
      ) {
        const formParams = values.params || form.getFieldValue('params') || {};
        const reconciledFormParams = { ...formParams };
        effectiveDataSource?.params.forEach((param) => {
          const options = resolvedParamOptionsRef.current.get(param.name);
          if (!options?.length) return;
          reconciledFormParams[param.name] = reconcileComponentParamValue(
            reconciledFormParams[param.name],
            options,
          );
        });
        if (Object.keys(reconciledFormParams).some(
          (name) => reconciledFormParams[name] !== formParams[name],
        )) {
          form.setFieldValue('params', reconciledFormParams);
        }
        const processed = processFormParamsForSubmit(
          reconciledFormParams,
          effectiveDataSource.params,
        );
        // 合并组件级 inputConfig 覆盖
        values.dataSourceParams = processed.map((param) => {
          const override = widgetParamOverrides.find((o) => o.name === param.name);
          return override?.inputConfig !== undefined
            ? { ...param, inputConfig: override.inputConfig }
            : param;
        });
        delete values.params;
      }

      if (isTableLikeChartType) {
        tableConfig.setDisplayColumnsError('');
      }

      if (
        values.sceneWidgetType === 'networkStatusTopology' ||
        chartType === 'networkStatusTopology'
      ) {
        const existingTopology = widgetItem?.valueConfig?.networkStatusTopology;
        const formTopology = values.networkStatusTopology;
        values.networkStatusTopology = {
          instUuids: formTopology?.instUuids || existingTopology?.instUuids || [],
          nodeLimit: formTopology?.nodeLimit ?? existingTopology?.nodeLimit ?? 100,
          linkTrafficDisplays:
            formTopology?.linkTrafficDisplays ?? existingTopology?.linkTrafficDisplays,
          inboundTrafficThresholds:
            formTopology?.inboundTrafficThresholds ??
            existingTopology?.inboundTrafficThresholds,
          outboundTrafficThresholds:
            formTopology?.outboundTrafficThresholds ??
            existingTopology?.outboundTrafficThresholds,
          layoutMode: formTopology?.layoutMode ?? existingTopology?.layoutMode,
          layoutByMode:
            formTopology?.layoutByMode ?? existingTopology?.layoutByMode,
          nodePositions:
            formTopology?.nodePositions ?? existingTopology?.nodePositions,
          linkVertices:
            formTopology?.linkVertices ?? existingTopology?.linkVertices,
        };
      }

      const submitResult = buildWidgetSubmitConfig({
        values,
        chartType,
        showChartThemeMode,
        showTableFilterFields,
        selectedFields: singleValueConfig.selectedFields,
        thresholdColors: singleValueConfig.thresholdColors,
        filterBindings,
        displayColumns: tableConfig.displayColumns,
        filterFields: tableConfig.filterFields,
        actions,
      });

      if (submitResult.error) {
        if (submitResult.error === 'duplicateFieldKey') {
          message.error(
            t('dashboard.duplicateFieldKey') || '字段 key 不能重复',
          );
          return;
        }
        if (submitResult.error === 'atLeastOneVisibleColumn') {
          tableConfig.setDisplayColumnsError(
            t('dashboard.atLeastOneVisibleColumn') || '请至少保留一列可见',
          );
          return;
        }
        if (submitResult.error === 'multipleComponentSwitchParams') {
          message.error(t('dashboard.multipleComponentSwitchParams'));
          return;
        }
        if (submitResult.error === 'cardListTitleRequired') {
          message.error(t('dashboard.cardListTitleRequired'));
          return;
        }
        if (submitResult.error === 'cardListLeadingFieldRequired') {
          message.error(t('dashboard.cardListLeadingFieldRequired'));
          return;
        }
      }

      if (submitResult.config) {
        onConfirm?.(submitResult.config);
      }
    } catch (error) {
      console.error('Form validation failed:', error);
      message.error(t('common.saveFailed'));
    }
  };

  return (
    <Drawer
      title={t('dashboard.viewConfig')}
      placement="right"
      width={isNetworkStatusTopology ? 760 : 700}
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
        layout="vertical"
        initialValues={{ compare: false, compareMode: 'percent' }}
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
                label={t('dashboard.networkTopoDevices')}
                name={['networkStatusTopology', 'instUuids']}
                dependencies={[['networkStatusTopology', 'nodeLimit']]}
                rules={[
                  { required: true, message: t('dashboard.networkTopoSelectDevicesRequired') },
                  {
                    validator: async (_, value) => {
                      if (
                        networkStatusTopologySelectionExceedsLimit(
                          value,
                          form.getFieldValue(['networkStatusTopology', 'nodeLimit']),
                        )
                      ) {
                        throw new Error(t('dashboard.networkTopoSelectionExceedsLimit'));
                      }
                    },
                  },
                ]}
                tooltip={t('dashboard.networkTopoDevicesHelp')}
              >
                <NetworkStatusTopologyDeviceList
                  nodeLimit={networkTopoNodeLimit}
                  listedOptions={networkTopologyConfig.instanceOptions}
                  instanceTotal={networkTopologyConfig.instanceTotal}
                  instancePage={networkTopologyConfig.instancePage}
                  instancePageSize={networkTopologyConfig.instancePageSize}
                  instanceKeyword={networkTopologyConfig.instanceKeyword}
                  instancesLoading={networkTopologyConfig.instancesLoading}
                  modelsLoading={networkTopologyConfig.modelsLoading}
                  modelFilter={networkTopologyConfig.modelFilter}
                  modelOptions={networkTopologyConfig.modelOptions}
                  onModelFilterChange={networkTopologyConfig.handleModelFilterChange}
                  onSearch={networkTopologyConfig.handleInstanceSearch}
                  onPageChange={networkTopologyConfig.handleInstancePageChange}
                />
              </Form.Item>
              <Form.Item
                label={t('dashboard.networkTopoNodeLimit')}
                name={['networkStatusTopology', 'nodeLimit']}
                initialValue={100}
                tooltip={t('dashboard.networkTopoNodeLimitHelp')}
              >
                <InputNumber
                  min={1}
                  max={NETWORK_STATUS_TOPOLOGY_MAX_NODE_LIMIT}
                  precision={0}
                  className="w-full"
                />
              </Form.Item>
              <Form.Item
                label={t('dashboard.networkTopoLinkTraffic')}
                name={['networkStatusTopology', 'linkTrafficDisplays']}
                initialValue={['inbound', 'outbound']}
              >
                <Checkbox.Group
                  options={[
                    {
                      label: t('dashboard.networkTopoLinkTrafficInbound'),
                      value: 'inbound',
                    },
                    {
                      label: t('dashboard.networkTopoLinkTrafficOutbound'),
                      value: 'outbound',
                    },
                  ]}
                />
              </Form.Item>
              <Form.Item
                name={['networkStatusTopology', 'inboundTrafficThresholds']}
                noStyle
              >
                <ThresholdColorListField
                  t={t}
                  label={t('dashboard.networkTopoLinkTrafficInboundThresholds')}
                  extra={t('dashboard.networkTopoTrafficThresholdHint')}
                />
              </Form.Item>
              <Form.Item
                name={['networkStatusTopology', 'outboundTrafficThresholds']}
                noStyle
              >
                <ThresholdColorListField
                  t={t}
                  label={t('dashboard.networkTopoLinkTrafficOutboundThresholds')}
                  extra={t('dashboard.networkTopoTrafficThresholdHint')}
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
                    ? `${selectedDataSource.name}${
                        selectedDataSource.rest_api
                          ? `（${selectedDataSource.rest_api}）`
                          : ''
                      }`
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
          {surface === 'screen' && canConfigureScreenWidgetFrame(chartType) && (
            <Form.Item
              label={t('opsAnalysis.screen.widgetAppearance')}
              name={['appearance', 'frame']}
              initialValue="panel"
            >
              <Segmented
                block
                className="w-60 max-w-full"
                options={[
                  {
                    label: t('opsAnalysis.screen.widgetFramePanel'),
                    value: 'panel',
                  },
                  {
                    label: t('opsAnalysis.screen.widgetFrameBare'),
                    value: 'bare',
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
              selectedDataSource={effectiveDataSource}
              includeFilterTypes={['params', 'fixed']}
              onEditInputConfig={handleEditInputConfig}
              onParamOptionsResolved={(param, options) =>
                reconcileParamWithOptions(param.name, options)
              }
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
            showColumnCellStyle={chartType === 'table'}
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
            onDisplayColumnStyleChange={
              tableConfig.handleDisplayColumnStyleChange
            }
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
            showDescriptionField
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

        {VALUE_FORMAT_CHART_TYPES.has(chartType) && (
          <div className="mb-6">
            <div className="font-medium mb-4">{t('dashboard.displaySettings')}</div>
            <ValueFormatConfigSection t={t} />
            {chartType === 'multiValue' && (
              <>
                <ThresholdColorConfigSection
                  t={t}
                  thresholdColors={singleValueConfig.thresholdColors}
                  onThresholdChange={singleValueConfig.handleThresholdChange}
                  onThresholdBlur={singleValueConfig.handleThresholdBlur}
                  onAddThreshold={singleValueConfig.addThreshold}
                  onRemoveThreshold={singleValueConfig.removeThreshold}
                  allowEmpty
                />
                <Form.Item
                  label={t('topology.nodeConfig.valueMappings')}
                  name="valueMappings"
                >
                  <ValueMappingsConfigSection t={t} />
                </Form.Item>
              </>
            )}
          </div>
        )}

        {chartType === 'eventTimeline' && (
          <div className="mb-6">
            <div className="font-medium mb-4">{t('dashboard.eventTimelineSettings')}</div>
            <Form.Item
              label={t('dashboard.eventTimelineSortOrder')}
              name={['eventTimeline', 'sortOrder']}
              initialValue="desc"
            >
              <Select
                options={[
                  { label: t('dashboard.eventTimelineSortDesc'), value: 'desc' },
                  { label: t('dashboard.eventTimelineSortAsc'), value: 'asc' },
                ]}
              />
            </Form.Item>
          </div>
        )}

        {chartType === 'radar' && (
          <RadarSettingsSection
            t={t}
            availableFields={availableFields}
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

        {chartType === 'cardList' && (
          <CardListSettingsSection
            key={resolveCardListSettingsRemountKey(widgetItem)}
            t={t}
            availableFields={availableFields}
          />
        )}

      </Form>
      <ComponentSelector
        visible={dataSourceSelectorVisible}
        onCancel={() => setDataSourceSelectorVisible(false)}
        onOpenConfig={handleDataSourceChangeFromSelector}
        surface={surface}
      />
      <ParamInputConfigEditor
        key={editingInputConfigParam?.name ?? 'closed'}
        open={editingInputConfigParam !== null}
        value={editingInputConfigParam?.inputConfig}
        onConfirm={handleInputConfigConfirm}
        onCancel={() => setEditingInputConfigParam(null)}
        excludeSourceIds={selectedDataSource ? [selectedDataSource.id] : []}
        componentSwitchEnabled={supportsComponentSwitch(chartType)}
        componentSwitchOwner={componentSwitchOwner}
        editingParamName={editingInputConfigParam?.name}
      />
    </Drawer>
  );
};

export default ViewConfig;
