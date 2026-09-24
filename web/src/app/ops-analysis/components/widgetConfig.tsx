/**
 * 组件配置抽屉协调器：只负责打开/关闭、回填、预览、保存。
 * 图表类型表单在 widgetConfig/sections；回填/重置/预览签名在 widgetConfigFormState。
 */
import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { markFormPristine } from '@/utils/formPristine';
import {
  ViewConfigProps,
  ViewConfigItem,
  UnifiedFilterDefinition,
  FilterBindings,
  FilterValue,
  DashboardActionConfig,
  WidgetConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  Drawer,
  Button,
  Form,
  Input,
  Select,
  message,
} from 'antd';
import { EyeOutlined } from '@ant-design/icons';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useSingleValueConfig } from '@/app/ops-analysis/hooks/useSingleValueConfig';
import {
  getChartTypeList,
  ChartTypeItem,
} from '@/app/ops-analysis/constants/common';
import { SingleValueSettingsSection } from '@/app/ops-analysis/components/singleValueSettingsSection';
import { ParamInputConfigEditor } from '@/app/ops-analysis/components/paramInputConfigEditor';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  getBindableFilterParams,
  buildDefaultFilterBindings,
  processDataSourceParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import { getDateRangeTimezone } from '@/app/ops-analysis/utils/dateRange';
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
import { ConfigSectionTitle } from './widgetConfig/configTitles';
import { useTableConfig } from './widgetConfig/hooks/useTableConfig';
import { TableSettingsSection } from './widgetConfig/sections/tableSettingsSection';
import { TopNSettingsSection } from './widgetConfig/sections/topNSettingsSection';
import { NodeGraphSettingsSection } from './widgetConfig/sections/nodeGraphSettingsSection';
import { GaugeSettingsSection } from './widgetConfig/sections/gaugeSettingsSection';
import { RadarSettingsSection } from './widgetConfig/sections/radarSettingsSection';
import { CardListSettingsSection } from './widgetConfig/sections/cardListSettingsSection';
import { WidgetConfigBasicFields } from './widgetConfig/sections/widgetConfigBasicFields';
import { WidgetDatasourceChartTypeFields } from './widgetConfig/sections/widgetDatasourceChartTypeFields';
import { NetworkStatusTopologyDataFields } from './widgetConfig/sections/networkStatusTopologyDataFields';
import { resolveCardListSettingsRemountKey } from './widgetConfig/utils/cardListSettingsRemountKey';
import {
  buildDisplayColumnsFromSchema,
  isDisplayableDefaultField,
} from './widgetConfig/utils/columnProbing';
import { buildRoleFieldOptions, dropRoleValueMissingFrom } from './widgetConfig/utils/chartFieldOptions';
import { ChartRoleFieldsSection, buildChartRoleFields, chartRoleValuePaths } from './widgetConfig/sections/chartRoleFieldsSection';
import {
  buildDisplayColumnFieldOptions,
  resolveDatasourceChartTypes,
  shouldShowTableFilterFields,
} from './widgetConfig/utils/tableSettingsBehavior';
import {
  buildWidgetDraftConfig,
  buildWidgetSubmitConfig,
  type WidgetConfigFormValues,
} from './widgetConfig/utils/submitConfig';
import {
  NETWORK_STATUS_TOPOLOGY,
  applyOpenedValueConfigToFormValues,
  buildDataFetchSignature,
  buildDatasourceSwitchResetValues,
  buildOpenedSceneWidgetTopology,
  buildOpenedWidgetFormValues,
  buildSceneWidgetSelectorResetValues,
  computePreviewDefinitions,
  getSceneWidgetSelectionType,
  getWidgetChartTypeFlags,
  isSceneWidgetSelection,
  mergeNetworkStatusTopologyDraft,
  resolveOpenedSceneWidgetType,
} from './widgetConfig/utils/widgetConfigFormState';
import WidgetConfigPreview from './widgetConfig/widgetConfigPreview';
import { useNetworkStatusTopologyConfig } from './widgetConfig/hooks/useNetworkStatusTopologyConfig';
import { RelatedTopologyAssetField } from './widgetConfig/sections/relatedTopologyAssetField';
import { Application3DWallFields } from './widgetConfig/sections/application3DWallFields';
import { Room3DRoomField } from './widgetConfig/sections/room3DRoomField';
import { Room3DRackTopFields } from './widgetConfig/sections/room3DRackTopFields';
import { getDefaultScreenWidgetAppearance } from '@/app/ops-analysis/(pages)/view/screen/utils/layoutUtils';
import { isSceneWidgetType } from '@/app/ops-analysis/types/sceneWidgetCapability';
import { ensurePrometheusQueryRequired } from '@/app/ops-analysis/utils/dataSourceParamContract';
import {
  coerceValueForMultiple,
  isMultipleSelectInputConfig,
  migrateParamItemsFromStringList,
  normalizeDatasourceItemParams,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';

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
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewSnapshotConfig, setPreviewSnapshotConfig] = useState<WidgetConfig | null>(null);
  const [previewSnapshotDataSource, setPreviewSnapshotDataSource] = useState<
    DatasourceItem | undefined
  >(undefined);
  const [previewSnapshotFilterDefinitions, setPreviewSnapshotFilterDefinitions] =
    useState<UnifiedFilterDefinition[]>([]);
  const [previewSnapshotNamespaceId, setPreviewSnapshotNamespaceId] = useState<
    number | undefined
  >(undefined);
  const [previewDataFetchSignature, setPreviewDataFetchSignature] = useState<string | null>(null);
  const [previewReloadVersion, setPreviewReloadVersion] = useState(0);
  const [previewRawData, setPreviewRawData] = useState<unknown>(null);
  const [suppliedPreviewRawData, setSuppliedPreviewRawData] = useState<unknown>(undefined);
  const [suppliedPreviewVersion, setSuppliedPreviewVersion] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [loadingRoleFields, setLoadingRoleFields] = useState(false);
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
  const {
    isTableLike: isTableLikeChartType,
    isNetworkStatusTopology,
    isRelatedTopology,
    isRoom3D,
    isApplication3D,
    isSceneWidget,
    showValueFormat,
  } = getWidgetChartTypeFlags(
    chartType,
    form.getFieldValue('sceneWidgetType'),
  );
  const networkTopologyConfig = useNetworkStatusTopologyConfig({
    open,
    enabled: isNetworkStatusTopology,
    form,
  });
  const networkTopoNodeLimit = Form.useWatch(
    ['networkStatusTopology', 'nodeLimit'],
    form,
  );
  const watchedFormValues = Form.useWatch([], form);

  const singleValueConfig = useSingleValueConfig({
    form,
    selectedDataSource: canonicalSelectedDataSource,
    getSourceDataByApiId,
    builtinNamespaceId: effectiveNamespaceId,
    open,
    previewRawData,
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
        const sceneWidgetType =
          getSceneWidgetSelectionType(item) || NETWORK_STATUS_TOPOLOGY;
        setChartType(sceneWidgetType);
        setSelectedDataSource(undefined);
        setFilterBindings({});
        setActions([]);
        setWidgetParamOverrides([]);
        tableConfig.resetTableConfig();
        singleValueConfig.resetSingleValueConfig();
        setPreviewRawData(null);
        setLoadingRoleFields(false);

        form.setFieldsValue(
          buildSceneWidgetSelectorResetValues(sceneWidgetType, surface),
        );
        return;
      }

      // 重置依赖字段
      setChartType('');
      setFilterBindings({});
      setActions([]);
      setWidgetParamOverrides([]);
      tableConfig.resetTableConfig();
      singleValueConfig.resetSingleValueConfig();
      setPreviewRawData(null);
      setLoadingRoleFields(false);

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

      form.setFieldsValue(
        buildDatasourceSwitchResetValues({
          dataSourceId: fullItem.id,
          chartType: defaultChartType,
          params,
          surface,
        }),
      );

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

  const roleFieldOptions = useMemo(
    () => buildRoleFieldOptions(availableFields, previewRawData),
    [availableFields, previewRawData],
  );
  const radarIndicators = Form.useWatch(['radar', 'indicators'], form);
  const chartRoleFields = useMemo(
    () => buildChartRoleFields(
      chartType,
      t,
      !(Array.isArray(radarIndicators) ? radarIndicators : []).some(
        (item) => String(item?.key || '').trim(),
      ),
    ),
    [chartType, radarIndicators, t],
  );

  useEffect(() => {
    if (previewRawData == null) {
      return;
    }
    if (chartType === 'single' || chartType === 'gauge') {
      const leaves: string[] = [];
      const walk = (nodes: Array<{ key?: string; children?: typeof nodes }>) => {
        nodes.forEach((node) => {
          if (node.children?.length) {
            walk(node.children);
            return;
          }
          if (node.key) {
            leaves.push(String(node.key));
          }
        });
      };
      walk(singleValueConfig.singleValueTreeData || []);
      if (leaves.length === 0) {
        return;
      }
      const schemaKeys = (selectedDataSource?.field_schema || [])
        .map((field) => String(field.key || '').trim())
        .filter(Boolean);
      const leafSet = new Set([...leaves, ...schemaKeys]);
      const current = form.getFieldValue('selectedFields');
      if (!Array.isArray(current)) {
        return;
      }
      const next = current.filter(
        (key): key is string => typeof key === 'string' && leafSet.has(key),
      );
      if (next.length !== current.length) {
        form.setFieldValue('selectedFields', next);
        singleValueConfig.setSelectedFields(next);
      }
      return;
    }
    const allowed = new Set(roleFieldOptions.map((option) => option.value));
    chartRoleValuePaths(chartType).forEach((path) => {
      const current = form.getFieldValue(path);
      if (typeof current !== 'string') {
        return;
      }
      const next = dropRoleValueMissingFrom(current, allowed);
      if (next !== current.trim()) {
        form.setFieldValue(path, next);
      }
    });
  }, [
    chartType,
    form,
    previewRawData,
    selectedDataSource,
    singleValueConfig.selectedFields,
    singleValueConfig.setSelectedFields,
    singleValueConfig.singleValueTreeData,
    roleFieldOptions,
  ]);

  const fetchRoleFields = useCallback(async () => {
    const resolvedId = canonicalSelectedDataSource?.id;
    if (!resolvedId || !canonicalSelectedDataSource) return;

    setLoadingRoleFields(true);
    try {
      const formValues = form.getFieldsValue();
      const userParams = formValues?.params || {};
      const requestParams = processDataSourceParams({
        sourceParams: canonicalSelectedDataSource.params,
        userParams,
        resolutionContext: {
          referenceNow: Date.now(),
          timezone: getDateRangeTimezone(),
        },
        t,
      });

      if (
        effectiveNamespaceId !== undefined &&
        Array.isArray(canonicalSelectedDataSource.namespaces) &&
        canonicalSelectedDataSource.namespaces.length > 0
      ) {
        requestParams.namespace_id = effectiveNamespaceId;
      }

      const { data } = await getSourceDataByApiId(resolvedId, requestParams);
      setPreviewRawData(data);
      if (previewOpen) {
        setSuppliedPreviewRawData(data);
        setSuppliedPreviewVersion((version) => version + 1);
      }
    } catch (error) {
      console.error('Failed to fetch data fields:', error);
      message.error(t('dashboard.fetchDataFieldsFailed'));
    } finally {
      setLoadingRoleFields(false);
    }
  }, [
    canonicalSelectedDataSource,
    effectiveNamespaceId,
    form,
    getSourceDataByApiId,
    previewOpen,
    t,
  ]);

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
    if (newChartType === 'nodeGraph' && !form.getFieldValue('nodeGraphIdentityMode')) {
      form.setFieldValue('nodeGraphIdentityMode', 'ip');
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
    const sceneWidgetType = resolveOpenedSceneWidgetType(valueConfig);
    const isOpenedSceneWidget = Boolean(sceneWidgetType);
    const formValues = buildOpenedWidgetFormValues(widgetItem, {
      showChartThemeMode,
      surface,
    });
    setChartType(formValues.chartType);
    setActions(valueConfig?.actions || []);

    if (isOpenedSceneWidget) {
      setSelectedDataSource(undefined);
      setFilterBindings({});
      tableConfig.resetTableConfig();
      singleValueConfig.resetSingleValueConfig();
      form.setFieldsValue({
        ...formValues,
        chartType: sceneWidgetType,
        sceneWidgetType,
        dataSource: undefined,
        networkStatusTopology: buildOpenedSceneWidgetTopology(valueConfig),
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
            valueConfig?.filterBindings,
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
    } else {
      singleValueConfig.setSelectedFields([]);
    }
    applyOpenedValueConfigToFormValues(formValues, valueConfig, targetDataSource);

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
    setPreviewOpen(false);
    setPreviewSnapshotConfig(null);
    setPreviewSnapshotDataSource(undefined);
    setPreviewSnapshotFilterDefinitions([]);
    setPreviewSnapshotNamespaceId(undefined);
    setPreviewDataFetchSignature(null);
    setPreviewReloadVersion(0);
    setPreviewRawData(null);
    setPreviewLoading(false);
    setLoadingRoleFields(false);
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

  const hydrateWidgetFormValues = useCallback(
    (
      values: WidgetConfigFormValues,
      options?: { persistReconcile?: boolean },
    ): WidgetConfigFormValues => {
      const persistReconcile = options?.persistReconcile !== false;
      const next: WidgetConfigFormValues = { ...values };

      if (
        !isSceneWidgetType(next.sceneWidgetType) &&
        effectiveDataSource?.params?.length
      ) {
        const formParams = next.params || form.getFieldValue('params') || {};
        const reconciledFormParams = { ...formParams };
        effectiveDataSource.params.forEach((param) => {
          const optionsForParam = resolvedParamOptionsRef.current.get(param.name);
          if (!optionsForParam?.length) return;
          reconciledFormParams[param.name] = reconcileComponentParamValue(
            reconciledFormParams[param.name],
            optionsForParam,
          );
        });
        if (
          persistReconcile &&
          Object.keys(reconciledFormParams).some(
            (name) => reconciledFormParams[name] !== formParams[name],
          )
        ) {
          form.setFieldValue('params', reconciledFormParams);
        }
        const processed = processFormParamsForSubmit(
          reconciledFormParams,
          effectiveDataSource.params,
        );
        next.dataSourceParams = processed.map((param) => {
          const override = widgetParamOverrides.find((o) => o.name === param.name);
          return override?.inputConfig !== undefined
            ? { ...param, inputConfig: override.inputConfig }
            : param;
        });
        delete next.params;
      }

      if (
        next.sceneWidgetType === 'networkStatusTopology' ||
        chartType === 'networkStatusTopology'
      ) {
        const existingTopology = widgetItem?.valueConfig?.networkStatusTopology;
        const formTopology = next.networkStatusTopology;
        next.networkStatusTopology = mergeNetworkStatusTopologyDraft(
          formTopology,
          existingTopology,
        );
      }

      return next;
    },
    [
      chartType,
      effectiveDataSource,
      form,
      processFormParamsForSubmit,
      widgetItem?.valueConfig?.networkStatusTopology,
      widgetParamOverrides,
    ],
  );

  const buildCurrentDraftConfig = useCallback((persistReconcile = false): WidgetConfig | undefined => {
    const values = hydrateWidgetFormValues(
      form.getFieldsValue(true) as WidgetConfigFormValues,
      { persistReconcile },
    );
    return buildWidgetDraftConfig({
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
  }, [
    actions,
    chartType,
    filterBindings,
    form,
    hydrateWidgetFormValues,
    showChartThemeMode,
    showTableFilterFields,
    singleValueConfig.selectedFields,
    singleValueConfig.thresholdColors,
    tableConfig.displayColumns,
    tableConfig.filterFields,
  ]);

  const liveDraft = useMemo(() => {
    return buildCurrentDraftConfig();
  }, [
    actions,
    buildCurrentDraftConfig,
    chartType,
    filterBindings,
    selectedDataSource,
    singleValueConfig.selectedFields,
    singleValueConfig.thresholdColors,
    tableConfig.displayColumns,
    tableConfig.filterFields,
    watchedFormValues,
    widgetParamOverrides,
  ]);

  const liveDataFetchSignature = useMemo(() => {
    return buildDataFetchSignature(liveDraft);
  }, [liveDraft]);

  const widgetPreviewId = `config-preview:${
    (widgetItem && 'i' in widgetItem && widgetItem.i) ||
    (widgetItem && 'id' in widgetItem && (widgetItem as { id?: string }).id) ||
    'new'
  }`;

  const hasDataFetchChanged =
    previewDataFetchSignature !== null &&
    liveDataFetchSignature !== previewDataFetchSignature;
  const previewStale = hasDataFetchChanged;
  const effectivePreviewConfig = hasDataFetchChanged
    ? previewSnapshotConfig
    : liveDraft || previewSnapshotConfig;
  // 取数签名变了时，配置、数据源、筛选定义必须一起冻住。
  // 只冻 config 会让渲染器用旧参数打新数据源（或反过来），触发「未声明参数」。
  const previewRequestDataSource = hasDataFetchChanged
    ? previewSnapshotDataSource
    : effectiveDataSource;
  const previewRequestFilterDefinitions = hasDataFetchChanged
    ? previewSnapshotFilterDefinitions
    : previewFilterDefinitions;
  const previewRequestNamespaceId = hasDataFetchChanged
    ? previewSnapshotNamespaceId
    : effectiveNamespaceId;

  const formDrawerWidth = isNetworkStatusTopology ? 760 : 680;
  const previewPaneWidth = 480;
  const drawerWidth = previewOpen
    ? formDrawerWidth + previewPaneWidth
    : formDrawerWidth;

  const handlePreview = useCallback(() => {
    if (!isSceneWidget && !effectiveDataSource) {
      message.warning(t('dashboard.configPreviewNeedDataSource'));
      return;
    }
    const draft = buildCurrentDraftConfig(true);
    if (!draft) {
      message.warning(t('dashboard.configPreviewNeedDataSource'));
      return;
    }
    setPreviewLoading(true);
    setPreviewSnapshotConfig(draft);
    setPreviewSnapshotDataSource(effectiveDataSource);
    setPreviewSnapshotFilterDefinitions(previewFilterDefinitions);
    setPreviewSnapshotNamespaceId(effectiveNamespaceId);
    setPreviewDataFetchSignature(buildDataFetchSignature(draft));
    setPreviewReloadVersion((version) => version + 1);
    setPreviewOpen(true);
  }, [
    buildCurrentDraftConfig,
    effectiveDataSource,
    effectiveNamespaceId,
    isSceneWidget,
    previewFilterDefinitions,
    t,
  ]);

  const handleConfirm = async () => {
    try {
      const values: WidgetConfigFormValues = hydrateWidgetFormValues(
        await form.validateFields(),
      );

      if (isTableLikeChartType) {
        tableConfig.setDisplayColumnsError('');
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
        if (submitResult.error === 'chartRoleFieldsRequired') {
          message.error(t('dashboard.chartRoleFieldsRequired'));
          return;
        }
        if (submitResult.error === 'chartRoleFieldPairRequired') {
          message.error(t('dashboard.chartRoleFieldPairRequired'));
          return;
        }
        if (submitResult.error === 'relatedTopologyModelIdRequired') {
          message.error(t('dashboard.relatedTopologyModelIdRequired'));
          return;
        }
        if (submitResult.error === 'relatedTopologyInstUuidRequired') {
          message.error(t('dashboard.relatedTopologyInstUuidRequired'));
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
      width={drawerWidth}
      open={open}
      maskClosable={false}
      onClose={handleClose}
      styles={{
        body: {
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          padding: 0,
        },
        footer: {
          padding: '12px 24px',
          borderTop: '1px solid var(--color-border-1)',
        },
      }}
      footer={
        <div className="flex items-center justify-between">
          <div>
            <Button
              data-testid="widget-config-preview-button"
              icon={<EyeOutlined />}
              onClick={() => {
                if (previewOpen) {
                  setPreviewOpen(false);
                } else {
                  handlePreview();
                }
              }}
            >
              {previewOpen
                ? t('dashboard.configPreviewCollapse', '收起预览')
                : t('common.preview', '预览')}
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={handleClose}>
              {t('common.cancel')}
            </Button>
            <Button type="primary" onClick={handleConfirm}>
              {t('common.confirm')}
            </Button>
          </div>
        </div>
      }
    >
      <div className="flex min-h-0 flex-1">
        {previewOpen ? (
          <aside
            className="flex h-full min-h-0 w-[480px] shrink-0 flex-col overflow-hidden border-r border-(--color-border-1) bg-(--color-fill-1)/20 p-4"
            data-testid="widget-config-preview-aside"
          >
            <WidgetConfigPreview
              widgetId={widgetPreviewId}
              previewed
              stale={previewStale}
              config={effectivePreviewConfig}
              dataSource={previewRequestDataSource}
              unifiedFilterValues={unifiedFilterValues}
              filterDefinitions={previewRequestFilterDefinitions}
              builtinNamespaceId={previewRequestNamespaceId}
              surface={surface}
              reloadVersion={previewReloadVersion}
              rawData={previewRawData}
              suppliedRawData={suppliedPreviewRawData}
              suppliedRawDataVersion={suppliedPreviewVersion}
              loading={previewLoading}
              onRawData={(data) => {
                setPreviewRawData(data);
                setPreviewLoading(false);
              }}
              liveName={watchedFormValues?.name}
              liveDescription={watchedFormValues?.description}
              onRefresh={handlePreview}
            />
          </aside>
        ) : null}
        <div className="min-w-0 flex-1 overflow-y-auto p-6 bg-(--color-bg)">
      <Form
        form={form}
        layout="vertical"
        initialValues={{ compare: false, compareMode: 'percent' }}
        onValuesChange={handleFormValuesChange}
        className="space-y-8"
      >
        <WidgetConfigBasicFields
          t={t}
          chartType={chartType}
          showChartThemeMode={showChartThemeMode}
          isNetworkStatusTopology={isNetworkStatusTopology}
          surface={surface}
        />

        <Form.Item name="sceneWidgetType" hidden>
          <Input />
        </Form.Item>

        {isApplication3D ? <Application3DWallFields /> : null}

        {isNetworkStatusTopology ? (
          <NetworkStatusTopologyDataFields
            t={t}
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
        ) : isRelatedTopology ? (
          <section>
            <ConfigSectionTitle>
              {t('dashboard.dataConfigSection', '数据配置')}
            </ConfigSectionTitle>
            <RelatedTopologyAssetField open={open} enabled={isRelatedTopology} />
          </section>
        ) : isRoom3D ? (
          <>
            <section>
              <ConfigSectionTitle>
                {t('dashboard.dataConfigSection', '数据配置')}
              </ConfigSectionTitle>
              <Room3DRoomField open={open} enabled={isRoom3D} />
            </section>
            <section>
              <ConfigSectionTitle>
                {t('dashboard.room3DRackTopSection')}
              </ConfigSectionTitle>
              <Room3DRackTopFields />
            </section>
          </>
        ) : isSceneWidget ? null : (
          <WidgetDatasourceChartTypeFields
            t={t}
            selectedDataSource={selectedDataSource}
            effectiveDataSource={effectiveDataSource}
            hasQueryParams={hasQueryParams}
            shouldShowUnifiedFilterSection={shouldShowUnifiedFilterSection}
            hasUnifiedFilterBindings={hasUnifiedFilterBindings}
            previewFilterDefinitions={previewFilterDefinitions}
            filterBindings={filterBindings}
            chartType={chartType}
            chartTypes={getDataSourceChartTypes}
            onFilterBindingsChange={setFilterBindings}
            onChartTypeChange={handleChartTypeChange}
            onOpenDataSourceSelector={() => setDataSourceSelectorVisible(true)}
            onEditInputConfig={handleEditInputConfig}
            onParamOptionsResolved={(param, options) =>
              reconcileParamWithOptions(param.name, options)
            }
          >
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
                sectionTitle=""
                selectedDataSource={selectedDataSource}
                singleValueTreeData={singleValueConfig.singleValueTreeData}
                selectedFields={singleValueConfig.selectedFields}
                loadingSingleValueData={loadingRoleFields}
                thresholdColors={singleValueConfig.thresholdColors}
                onFetchSingleValueDataFields={fetchRoleFields}
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
                sectionTitle=""
                selectedDataSource={selectedDataSource}
                singleValueTreeData={singleValueConfig.singleValueTreeData}
                selectedFields={singleValueConfig.selectedFields}
                loadingSingleValueData={loadingRoleFields}
                thresholdColors={singleValueConfig.thresholdColors}
                onFetchSingleValueDataFields={fetchRoleFields}
                onSingleValueFieldChange={
                  singleValueConfig.handleSingleValueFieldChange
                }
                onThresholdChange={singleValueConfig.handleThresholdChange}
                onThresholdBlur={singleValueConfig.handleThresholdBlur}
                onAddThreshold={singleValueConfig.addThreshold}
                onRemoveThreshold={singleValueConfig.removeThreshold}
              />
            )}

            {chartType === 'nodeGraph' && (
              <NodeGraphSettingsSection
                t={t}
                sectionTitle=""
                selectedDataSource={selectedDataSource}
                fieldOptions={roleFieldOptions}
                valueFieldOptions={roleFieldOptions}
                loadingFields={loadingRoleFields}
                onRefreshFields={fetchRoleFields}
              />
            )}

            {chartRoleFields.length > 0 && (
              <ChartRoleFieldsSection
                t={t}
                selectedDataSource={selectedDataSource}
                options={roleFieldOptions}
                roles={chartRoleFields}
                loadingFields={loadingRoleFields}
                onRefreshFields={fetchRoleFields}
              />
            )}

            {showValueFormat && (
              <div className="space-y-4">
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
                sectionTitle=""
                selectedDataSource={selectedDataSource}
                topNLabelFieldOptions={roleFieldOptions}
                topNValueFieldOptions={roleFieldOptions}
                loadingFields={loadingRoleFields}
                onRefreshFields={fetchRoleFields}
              />
            )}

            {chartType === 'cardList' && (
              <CardListSettingsSection
                key={resolveCardListSettingsRemountKey(widgetItem)}
                t={t}
                availableFields={availableFields}
                previewRawData={previewRawData}
                loadingFields={loadingRoleFields}
                onRefreshFields={fetchRoleFields}
              />
            )}
          </WidgetDatasourceChartTypeFields>
        )}

      </Form>
        </div>
      </div>
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
