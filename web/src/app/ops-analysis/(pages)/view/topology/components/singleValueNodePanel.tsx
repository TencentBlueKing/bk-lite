/**
 * 单值节点配置面板
 * 专门处理数据驱动的 single-value 节点（数据源、参数、字段选择、阈值、compare）
 */
import React, {
  useEffect,
  useState,
  useRef,
  useCallback,
} from 'react';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useSingleValueConfig } from '@/app/ops-analysis/hooks/useSingleValueConfig';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { NodeConfPanelProps } from '@/app/ops-analysis/types/topology';
import { NODE_DEFAULTS } from '../constants/nodeDefaults';
import { initThresholdColors } from '@/app/ops-analysis/utils/thresholdUtils';
import { canEnableCompare } from '@/app/ops-analysis/utils/compareQuery';
import { SingleValueSettingsSection } from '@/app/ops-analysis/components/singleValueSettingsSection';
import { useTranslation } from '@/utils/i18n';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import DataSourceSelect from '@/app/ops-analysis/components/dataSourceSelect';
import {
  Form,
  Input,
  InputNumber,
  Spin,
  Button,
  Drawer,
  ColorPicker,
} from 'antd';

const SingleValueNodePanel: React.FC<NodeConfPanelProps> = ({
  readonly = false,
  editingNodeData,
  visible = false,
  title,
  builtinNamespaceId,
  onClose,
  onConfirm,
  onCancel,
}) => {
  const [form] = Form.useForm();
  const [currentDataSource, setCurrentDataSource] = useState<number | null>(null);
  const [filteredDataSources, setFilteredDataSources] = useState<DatasourceItem[]>([]);
  const initializedRef = useRef<string | null>(null);

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

  const initializeNewNode = useCallback(() => {
    const defaultValues: any = {
      dataSource: undefined,
      compare: false,
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
    singleValueConfig.resetSingleValueConfig();

    form.resetFields();
    form.setFieldsValue(defaultValues);
  }, [form, setSelectedDataSource, singleValueConfig]);

  const initializeEditNode = useCallback(
    async (editingNodeData: any) => {
      const { styleConfig = {}, valueConfig = {} } = editingNodeData;

      const normalizeColorForForm = (value?: string) =>
        value === 'transparent' ? undefined : value;

      const formValues: any = {
        name: editingNodeData.name,
        dataSource: valueConfig.dataSource,
        compare: valueConfig.compare,
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

      setCurrentDataSource(valueConfig.dataSource || null);
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

        if (selectedSource?.params?.length) {
          setDefaultParamValues(selectedSource.params, formValues.params);

          if (valueConfig.dataSourceParams?.length) {
            restoreUserParamValues(
              valueConfig.dataSourceParams,
              formValues.params,
            );
          }
        }
      } else {
        setSelectedDataSource(undefined);
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
        const params = currentValues.params || {};
        setDefaultParamValues(selectedSource.params, params);
        form.setFieldsValue({
          ...currentValues,
          selectedFields: [],
          params,
        });
      }
    },
    [ensureDataSource, setSelectedDataSource, form, setDefaultParamValues, singleValueConfig]
  );

  const processColorValue = useCallback((colorValue: any) => {
    if (!colorValue) return undefined;
    if (typeof colorValue === 'string') return colorValue;
    if (colorValue.toHexString) return colorValue.toHexString();
    if (colorValue.toRgbString) return colorValue.toRgbString();
    return colorValue;
  }, []);

  const handleConfirm = useCallback(async () => {
    try {
      const values = await form.validateFields();

      ['textColor', 'backgroundColor', 'borderColor', 'nameColor'].forEach((key) => {
        if (values[key]) {
          values[key] = processColorValue(values[key]);
        }
      });

      if (values.params && selectedDataSource?.params) {
        values.dataSourceParams = processFormParamsForSubmit(
          values.params,
          selectedDataSource.params,
        );
        delete values.params;
      }

      values.thresholdColors = singleValueConfig.thresholdColors;
      values.compare = !!values.compare;

      onConfirm?.(values);
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  }, [
    form,
    selectedDataSource,
    processFormParamsForSubmit,
    onConfirm,
    processColorValue,
    singleValueConfig.thresholdColors,
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
      <Form form={form} labelCol={{ span: 5 }} layout="horizontal">
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

        {/* 参数 */}
        {selectedDataSource?.params && selectedDataSource.params.length > 0 && (
          <div className="mb-6">
            <div className="font-bold text-(--color-text-1) mb-4">
              {t('dashboard.queryParams')}
            </div>
            <Spin size="small" spinning={dataSourcesLoading}>
              <DataSourceParamsConfig
                selectedDataSource={selectedDataSource}
                readonly={readonly || dataSourcesLoading}
                includeFilterTypes={['params', 'fixed', 'filter']}
                fieldPrefix="params"
              />
            </Spin>
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
