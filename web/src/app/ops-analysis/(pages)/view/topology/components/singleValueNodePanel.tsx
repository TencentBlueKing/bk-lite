/**
 * 单值节点配置面板
 * 专门处理数据驱动的 single-value 节点（数据源、参数、字段选择、阈值、compare）
 */
import React, {
  useEffect,
  useState,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useSingleValueConfig } from '@/app/ops-analysis/hooks/useSingleValueConfig';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import type {
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  NodeConfPanelProps,
  NodeConfigFormValues,
  TopologyNodeData,
} from '@/app/ops-analysis/types/topology';
import { NODE_DEFAULTS } from '../constants/nodeDefaults';
import { initThresholdColors } from '@/app/ops-analysis/utils/thresholdUtils';
import { canEnableCompare } from '@/app/ops-analysis/utils/compareQuery';
import { SingleValueSettingsSection } from '@/app/ops-analysis/components/singleValueSettingsSection';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import { useTranslation } from '@/utils/i18n';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import DataSourceSelect from '@/app/ops-analysis/components/dataSourceSelect';
import { normalizeColorFields } from '../utils/formColorUtils';
import {
  buildDefaultFilterBindings,
  getBindableFilterParams,
  getFilterDefinitionId,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import {
  Form,
  Input,
  InputNumber,
  Spin,
  Button,
  Drawer,
  ColorPicker,
  Tooltip,
} from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';

const QUERY_PARAM_FILTER_TYPES = ['params', 'fixed'];

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

type SingleValueFormValues = NodeConfigFormValues & {
  params?: Record<string, unknown>;
  compareMode?: 'percent' | 'value';
};

const SingleValueNodePanel: React.FC<NodeConfPanelProps> = ({
  readonly = false,
  editingNodeData,
  visible = false,
  title,
  builtinNamespaceId,
  filterDefinitions = [],
  onClose,
  onConfirm,
  onCancel,
}) => {
  const [form] = Form.useForm();
  const [currentDataSource, setCurrentDataSource] = useState<number | null>(null);
  const [filteredDataSources, setFilteredDataSources] = useState<DatasourceItem[]>([]);
  const initializedRef = useRef<string | null>(null);
  const [filterBindings, setFilterBindings] = useState<FilterBindings>({});

  const { getSourceDataByApiId, getDataSourceBriefList } = useDataSourceApi();
  const { t } = useTranslation();

  const {
    dataSourcesLoading,
    selectedDataSource,
    setSelectedDataSource,
    ensureDataSource,
    setDefaultParamValues,
    restoreUserParamValues,
    processFormParamsForSubmit,
  } = useDataSourceManager();

  const singleValueConfig = useSingleValueConfig({
    form,
    selectedDataSource,
    builtinNamespaceId,
    dataSourceId: currentDataSource,
    getSourceDataByApiId,
    open: visible,
  });

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
        QUERY_PARAM_FILTER_TYPES.includes(param.filterType || 'fixed'),
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
  const hasUnifiedFilterBindings = bindableFilterParams.length > 0;
  const shouldShowUnifiedFilterSection =
    previewFilterDefinitions.length > 0 && Boolean(selectedDataSource?.params);

  const initializeNewNode = useCallback(() => {
    const defaultValues: SingleValueFormValues = {
      dataSource: undefined,
      compare: false,
      compareMode: 'percent',
      params: {},
      selectedFields: [],
      name: '',
      nameFontSize: 12,
      nameColor: '#666666',
      unit: '',
      conversionFactor: 1,
      decimalPlaces: 2,
      fontSize: NODE_DEFAULTS.SINGLE_VALUE_NODE.fontSize,
      textColor: NODE_DEFAULTS.SINGLE_VALUE_NODE.textColor,
    };

    setCurrentDataSource(null);
    setSelectedDataSource(undefined);
    setFilterBindings({});
    singleValueConfig.resetSingleValueConfig();

    form.resetFields();
    form.setFieldsValue(defaultValues);
  }, [form, setSelectedDataSource, singleValueConfig]);

  const initializeEditNode = useCallback(
    async (editingNodeData: TopologyNodeData) => {
      const { styleConfig = {}, valueConfig = {} } = editingNodeData;

      const normalizeColorForForm = (value?: string) =>
        value === 'transparent' ? undefined : value;

      const formValues: SingleValueFormValues = {
        name: editingNodeData.name,
        dataSource: valueConfig.dataSource,
        compare: valueConfig.compare,
        compareMode: valueConfig.compareMode || 'percent',
        selectedFields: valueConfig.selectedFields,
        fontSize: styleConfig.fontSize,
        textColor: normalizeColorForForm(styleConfig.textColor),
        backgroundColor: normalizeColorForForm(styleConfig.backgroundColor),
        borderColor: normalizeColorForForm(styleConfig.borderColor),
        nameFontSize: styleConfig.nameFontSize,
        nameColor: styleConfig.nameColor,
        unit: editingNodeData.unit,
        unitId: valueConfig.unitId,
        valueMappings: valueConfig.valueMappings,
        conversionFactor: editingNodeData.conversionFactor,
        decimalPlaces: editingNodeData.decimalPlaces,
      };

      const dataSourceId =
        typeof valueConfig.dataSource === 'string'
          ? parseInt(valueConfig.dataSource, 10)
          : valueConfig.dataSource;
      setCurrentDataSource(
        typeof dataSourceId === 'number' && !Number.isNaN(dataSourceId)
          ? dataSourceId
          : null,
      );
      singleValueConfig.setSelectedFields(valueConfig.selectedFields || []);
      singleValueConfig.setThresholdColors(initThresholdColors(styleConfig.thresholdColors));

      if (valueConfig.dataSource) {
        const selectedSource = await ensureDataSource(valueConfig.dataSource);
        setSelectedDataSource(selectedSource);

        // 如果数据源不再支持 compare，强制关闭
        if (formValues.compare && !canEnableCompare({
          config: { chartType: 'single', dataSourceParams: selectedSource?.params },
          dataSource: selectedSource,
        })) {
          formValues.compare = false;
        }

        formValues.params = formValues.params || {};
        const params = formValues.params as Parameters<typeof setDefaultParamValues>[1];

        if (selectedSource?.params?.length) {
          setDefaultParamValues(selectedSource.params, params);

          if (valueConfig.dataSourceParams?.length) {
            restoreUserParamValues(
              valueConfig.dataSourceParams,
              params,
            );
          }

          const previewDefs = computePreviewDefinitions(
            filterDefinitions,
            selectedSource,
          );
          setFilterBindings(
            buildDefaultFilterBindings(
              valueConfig.dataSourceParams?.length
                ? valueConfig.dataSourceParams
                : selectedSource.params,
              previewDefs,
              valueConfig.filterBindings,
            ) || {},
          );
        } else {
          setFilterBindings({});
        }
      } else {
        setSelectedDataSource(undefined);
        setFilterBindings({});
      }

      form.setFieldsValue(formValues);
    },
    [
      form,
      ensureDataSource,
      setSelectedDataSource,
      setDefaultParamValues,
      restoreUserParamValues,
      singleValueConfig,
      filterDefinitions,
    ]
  );

  useEffect(() => {
    if (!visible) {
      initializedRef.current = null;
      return;
    }

    const fetchBriefList = async () => {
      try {
        const response = await getDataSourceBriefList({
          chart_type: 'single',
          page_size: -1,
        });
        setFilteredDataSources(Array.isArray(response) ? response : []);
      } catch (error) {
        console.error('Failed to fetch single-value datasource list:', error);
        setFilteredDataSources([]);
      }
    };

    void fetchBriefList();
  }, [getDataSourceBriefList, visible]);

  useEffect(() => {
    if (!visible) return;

    const initKey = editingNodeData?.id || '__new__';
    if (initializedRef.current === initKey) return;

    initializedRef.current = initKey;

    if (editingNodeData) {
      void initializeEditNode(editingNodeData);
    } else {
      initializeNewNode();
    }
  }, [visible, editingNodeData, initializeEditNode, initializeNewNode]);

  const handleDataSourceChange = useCallback(
    async (dataSourceId: number) => {
      setCurrentDataSource(dataSourceId);
      const selectedSource = await ensureDataSource(dataSourceId);
      setSelectedDataSource(selectedSource);
      singleValueConfig.setSingleValueTreeData([]);
      singleValueConfig.setSelectedFields([]);

      const currentValues = form.getFieldsValue();
      form.setFieldsValue({
        ...currentValues,
        dataSource: dataSourceId,
        compare: false,
        selectedFields: [],
      });

      if (selectedSource?.params?.length) {
        const params = (currentValues.params || {}) as Parameters<
          typeof setDefaultParamValues
        >[1];
        setDefaultParamValues(selectedSource.params, params);
        form.setFieldsValue({
          ...currentValues,
          selectedFields: [],
          params,
        });
        const previewDefs = computePreviewDefinitions(
          filterDefinitions,
          selectedSource,
        );
        setFilterBindings(
          buildDefaultFilterBindings(selectedSource.params, previewDefs) || {},
        );
      } else {
        setFilterBindings({});
      }
    },
    [
      ensureDataSource,
      setSelectedDataSource,
      form,
      setDefaultParamValues,
      singleValueConfig,
      filterDefinitions,
    ]
  );

  const handleConfirm = useCallback(async () => {
    try {
      const values = normalizeColorFields(
        (await form.validateFields()) as SingleValueFormValues,
        ['textColor', 'backgroundColor', 'borderColor', 'nameColor'],
      );

      if (values.params && selectedDataSource?.params) {
        values.dataSourceParams = processFormParamsForSubmit(
          values.params as Parameters<typeof processFormParamsForSubmit>[0],
          selectedDataSource.params,
        );
        delete values.params;
      }

      values.thresholdColors = singleValueConfig.thresholdColors;
      values.compare = !!values.compare;
      if (values.compare) {
        values.compareMode = values.compareMode || 'percent';
      }
      if (filterBindings && Object.keys(filterBindings).length > 0) {
        values.filterBindings = filterBindings;
      }

      onConfirm?.(values);
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  }, [
    form,
    selectedDataSource,
    processFormParamsForSubmit,
    onConfirm,
    singleValueConfig.thresholdColors,
    filterBindings,
  ]);

  const handleCancel = () => {
    if (onCancel) {
      onCancel();
    } else if (onClose) {
      onClose();
    }
  };

  return (
    <Drawer
      title={title || t('topology.nodeTitles.single-value')}
      placement="right"
      width={680}
      open={visible}
      onClose={onClose}
      footer={
        <div className="flex justify-end space-x-2">
          {!readonly && (
            <Button type="primary" onClick={handleConfirm}>
              {t('topology.nodeConfig.confirm')}
            </Button>
          )}
          <Button onClick={handleCancel}>
            {readonly
              ? t('topology.nodeConfig.close')
              : t('topology.nodeConfig.cancel')}
          </Button>
        </div>
      }
    >
      <Form form={form} layout="vertical">
        {/* 基础设置 */}
        <div className="mb-6">
          <div className="font-bold text-(--color-text-1) mb-4">
            {t('topology.nodeConfig.basicSettings')}
          </div>
          <Form.Item label={t('dashboard.widgetName')} name="name">
            <Input placeholder={t('common.inputMsg')} disabled={readonly} />
          </Form.Item>
          <Form.Item
            label={t('dashboard.dataSource')}
            name="dataSource"
            rules={[{ required: true, message: t('common.selectMsg') }]}
          >
            <DataSourceSelect
              loading={dataSourcesLoading}
              dataSources={filteredDataSources}
              placeholder={t('common.selectMsg')}
              style={{ width: '100%' }}
              showSearch
              className={
                readonly ? undefined : '[&_.ant-select-selector]:cursor-pointer'
              }
              onChange={(value) => {
                void handleDataSourceChange(value);
              }}
              disabled={readonly}
            />
          </Form.Item>
        </div>

        {/* 查询参数：仅私有 params 与固定参数，筛选参数走统一筛选 */}
        {hasQueryParams && (
          <div className="mb-6">
            <div className="font-bold text-(--color-text-1) mb-4">
              {t('dashboard.queryParams')}
            </div>
            <Spin size="small" spinning={dataSourcesLoading}>
              <DataSourceParamsConfig
                selectedDataSource={selectedDataSource}
                readonly={readonly || dataSourcesLoading}
                includeFilterTypes={['params', 'fixed']}
                fieldPrefix="params"
              />
            </Spin>
          </div>
        )}

        {shouldShowUnifiedFilterSection && hasUnifiedFilterBindings && (
          <div className="mb-6">
            <div className="font-bold text-(--color-text-1) mb-4 flex items-center gap-1">
              {t('dashboard.unifiedFilterLinkage')}
              <Tooltip
                title={
                  <span className="whitespace-pre-line">
                    {t('dashboard.unifiedFilterBindingTip')}
                  </span>
                }
                overlayInnerStyle={{ maxWidth: 360 }}
              >
                <QuestionCircleOutlined className="text-(--color-text-3) cursor-help" />
              </Tooltip>
            </div>
            <FilterBindingPanel
              definitions={previewFilterDefinitions}
              dataSourceParams={selectedDataSource?.params || []}
              filterBindings={filterBindings}
              onChange={setFilterBindings}
            />
          </div>
        )}

        {/* 数据配置（字段树 + unit + compare + 换算 + 阈值） */}
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
          readonly={readonly}
          compareAvailable={singleValueConfig.compareAvailable}
        />

        {/* 样式设置 */}
        <div className="mb-6">
          <div className="font-bold text-(--color-text-1) mb-4">
            {t('topology.styleSettings')}
          </div>
          <Form.Item label={t('topology.nodeConfig.fontSize')} name="fontSize">
            <InputNumber
              min={10}
              max={48}
              step={1}
              addonAfter="px"
              disabled={readonly}
              placeholder={t('common.inputMsg')}
              style={{ width: '120px' }}
            />
          </Form.Item>
          <Form.Item
            label={t('topology.nodeConfig.textColor')}
            name="textColor"
          >
            <ColorPicker
              disabled={readonly}
              size="small"
              showText
              allowClear
              format="hex"
            />
          </Form.Item>
          <Form.Item
            label={t('topology.nodeConfig.nameFontSize')}
            name="nameFontSize"
          >
            <InputNumber
              min={10}
              max={40}
              step={1}
              addonAfter="px"
              disabled={readonly}
              placeholder={t('common.inputMsg')}
              style={{ width: '120px' }}
            />
          </Form.Item>
          <Form.Item
            label={t('topology.nodeConfig.nameColor')}
            name="nameColor"
          >
            <ColorPicker
              disabled={readonly}
              size="small"
              showText
              allowClear
              format="hex"
            />
          </Form.Item>
          <Form.Item
            label={t('topology.nodeConfig.backgroundColor')}
            name="backgroundColor"
          >
            <ColorPicker
              disabled={readonly}
              size="small"
              showText
              allowClear
              format="hex"
            />
          </Form.Item>
          <Form.Item
            label={t('topology.nodeConfig.borderColor')}
            name="borderColor"
          >
            <ColorPicker
              disabled={readonly}
              size="small"
              showText
              allowClear
              format="hex"
            />
          </Form.Item>
        </div>
      </Form>
    </Drawer>
  );
};

export default SingleValueNodePanel;
