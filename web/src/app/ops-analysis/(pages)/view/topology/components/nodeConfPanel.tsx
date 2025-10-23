import React, {
  useEffect,
  useState,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { NodeConfPanelProps } from '@/app/ops-analysis/types/topology';
import { iconList } from '@/app/cmdb/utils/common';
import { NODE_DEFAULTS } from '../constants/nodeDefaults';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';
import { buildTreeData } from '../utils/dataTreeUtils';
import { useTranslation } from '@/utils/i18n';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import DataSourceSelect from '@/app/ops-analysis/components/dataSourceSelect';
import SelectIcon, {
  SelectIconRef,
} from '@/app/cmdb/(pages)/assetManage/management/list/selectIcon';
import {
  Form,
  Input,
  InputNumber,
  Upload,
  Radio,
  Spin,
  Button,
  Drawer,
  Tree,
  Select,
  ColorPicker,
} from 'antd';
import {
  UploadOutlined,
  AppstoreOutlined,
  ReloadOutlined,
  PlusCircleOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';

const NODE_TYPE_DEFAULTS = {
  icon: NODE_DEFAULTS.ICON_NODE,
  'basic-shape': NODE_DEFAULTS.BASIC_SHAPE_NODE,
  'single-value': NODE_DEFAULTS.SINGLE_VALUE_NODE,
  text: NODE_DEFAULTS.TEXT_NODE,
} as const;

const NodeConfPanel: React.FC<NodeConfPanelProps> = ({
  nodeType,
  readonly = false,
  editingNodeData,
  visible = false,
  title,
  onClose,
  onConfirm,
  onCancel,
}) => {
  const [form] = Form.useForm();
  const [logoPreview, setLogoPreview] = useState<string>('');
  const [logoType, setLogoType] = useState<'default' | 'custom'>('default');
  const [selectedIcon, setSelectedIcon] = useState<string>('cc-host');
  const [treeData, setTreeData] = useState<any[]>([]);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [loadingData, setLoadingData] = useState(false);
  const [currentDataSource, setCurrentDataSource] = useState<number | null>(
    null
  );
  const [thresholdColors, setThresholdColors] = useState<
    Array<{
      value: string;
      color: string;
    }>
  >([
    { color: '#fd666d', value: '70' },
    { color: '#EAB839', value: '30' },
    { color: '#299C46', value: '0' },
  ]);

  const selectIconRef = useRef<SelectIconRef>(null);
  const { getSourceDataByApiId } = useDataSourceApi();
  const { t } = useTranslation();

  const {
    dataSources,
    dataSourcesLoading,
    selectedDataSource,
    setSelectedDataSource,
    processFormParamsForSubmit,
    setDefaultParamValues,
    restoreUserParamValues,
  } = useDataSourceManager();

  const filteredDataSources = useMemo(() => {
    return dataSources.filter(
      (dataSource) =>
        dataSource.chart_type && dataSource.chart_type.includes('single')
    );
  }, [dataSources]);

  const nodeDefaults = useMemo(() => {
    return (
      NODE_TYPE_DEFAULTS[nodeType as keyof typeof NODE_TYPE_DEFAULTS] ||
      NODE_DEFAULTS.SINGLE_VALUE_NODE
    );
  }, [nodeType]);

  const getIconUrl = useCallback((iconKey: string) => {
    const iconItem = iconList.find((item) => item.key === iconKey);
    return iconItem
      ? `/app/assets/assetModelIcon/${iconItem.url}.svg`
      : `/app/assets/assetModelIcon/cc-default_默认.svg`;
  }, []);

  const handleThresholdChange = useCallback(
    (index: number, field: 'value' | 'color', value: string | number) => {
      setThresholdColors((prev) => {
        const newThresholds = [...prev];
        newThresholds[index] = {
          ...newThresholds[index],
          [field]: field === 'value' ? String(value) : value,
        };
        return newThresholds;
      });
    },
    []
  );

  const handleThresholdBlur = useCallback(
    (index: number, value: number | null) => {
      setThresholdColors((prev) => {
        const newThresholds = [...prev];

        if (value === null || value === undefined) {
          newThresholds[index] = { ...newThresholds[index], value: '50' };
          return newThresholds;
        }

        const numValue = Number(value);

        const isDuplicate = prev.some(
          (threshold, i) =>
            i !== index && parseFloat(threshold.value) === numValue
        );

        if (isDuplicate) {
          let adjustedValue = numValue;
          while (
            prev.some(
              (threshold, i) =>
                i !== index && parseFloat(threshold.value) === adjustedValue
            )
          ) {
            adjustedValue += 1;
          }
          newThresholds[index] = {
            ...newThresholds[index],
            value: adjustedValue.toString(),
          };
        } else {
          newThresholds[index] = {
            ...newThresholds[index],
            value: numValue.toString(),
          };
        }

        return newThresholds.sort(
          (a, b) => parseFloat(b.value) - parseFloat(a.value)
        );
      });
    },
    []
  );

  const addThreshold = useCallback((afterIndex?: number) => {
    setThresholdColors((prev) => {
      let newValue = 50;

      if (afterIndex !== undefined && afterIndex >= 0) {
        const currentValue = parseFloat(prev[afterIndex]?.value || '0');
        const nextValue =
          afterIndex + 1 < prev.length
            ? parseFloat(prev[afterIndex + 1]?.value || '0')
            : 0;

        if (currentValue - nextValue > 1) {
          newValue = Math.floor((currentValue + nextValue) / 2);
        } else {
          newValue = Math.max(currentValue - 5, nextValue + 1);
        }
      } else {
        const values = prev
          .map((t) => parseFloat(t.value))
          .filter((v) => !isNaN(v));
        const maxValue = Math.max(...values);
        newValue = Math.min(maxValue + 10, 100);
      }

      const existingValues = prev
        .map((t) => parseFloat(t.value))
        .filter((v) => !isNaN(v));
      while (existingValues.includes(newValue)) {
        newValue += 1;
      }

      const newThreshold = { color: '#fd666d', value: newValue.toString() };

      if (afterIndex !== undefined && afterIndex >= 0) {
        const newThresholds = [...prev];
        newThresholds.splice(afterIndex + 1, 0, newThreshold);
        return newThresholds.sort(
          (a, b) => parseFloat(b.value) - parseFloat(a.value)
        );
      } else {
        const newThresholds = [...prev, newThreshold];
        return newThresholds.sort(
          (a, b) => parseFloat(b.value) - parseFloat(a.value)
        );
      }
    });
  }, []);

  const removeThreshold = useCallback((index: number) => {
    setThresholdColors((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const initializeNewNode = useCallback(() => {
    const defaultValues: any = {
      logoType: 'default',
      logoIcon: 'cc-host',
      logoUrl: '',
      fontSize: nodeDefaults.fontSize,
      textColor: nodeDefaults.textColor,
      backgroundColor: nodeDefaults.backgroundColor,
      borderColor: nodeDefaults.borderColor,
      selectedFields: [],
      name: '',
      width: nodeDefaults.width,
      height: nodeDefaults.height,
    };

    if (nodeType === 'single-value') {
      defaultValues.nameFontSize = 12;
      defaultValues.nameColor = '#666666';
      defaultValues.unit = '';
      defaultValues.conversionFactor = 1;
      defaultValues.decimalPlaces = 2;
    }

    if (nodeType === 'basic-shape') {
      const basicShapeDefaults =
        nodeDefaults as typeof NODE_DEFAULTS.BASIC_SHAPE_NODE;
      defaultValues.borderWidth = basicShapeDefaults.borderWidth;
      defaultValues.lineType = basicShapeDefaults.lineType;
      defaultValues.shapeType = basicShapeDefaults.shapeType;
      defaultValues.renderEffect = 'glass';
    }

    if (nodeType === 'icon') {
      const iconDefaults = nodeDefaults as typeof NODE_DEFAULTS.ICON_NODE;
      defaultValues.fontSize = iconDefaults.fontSize;
      defaultValues.textColor = iconDefaults.textColor;
      defaultValues.iconPadding = 4;
      defaultValues.textDirection = 'bottom';
    }

    if (nodeType === 'text') {
      const textDefaults = nodeDefaults as typeof NODE_DEFAULTS.TEXT_NODE;
      defaultValues.fontSize = textDefaults.fontSize;
      defaultValues.textColor = textDefaults.textColor;
      defaultValues.fontWeight = textDefaults.fontWeight;
    }

    setSelectedIcon('cc-host');
    setLogoType('default');
    setLogoPreview('');
    setCurrentDataSource(null);
    setSelectedDataSource(undefined);
    setTreeData([]);
    setSelectedFields([]);

    form.setFieldsValue(defaultValues);
  }, [form, setSelectedDataSource, nodeType, nodeDefaults]);

  const initializeEditNode = useCallback(
    (editingNodeData: any) => {
      const { styleConfig = {}, valueConfig = {} } = editingNodeData;

      const formValues: any = {
        name: editingNodeData.name,
        logoType: editingNodeData.logoType,
        logoIcon:
          editingNodeData.logoType === 'default'
            ? editingNodeData.logoIcon
            : undefined,
        logoUrl:
          editingNodeData.logoType === 'custom'
            ? editingNodeData.logoUrl
            : undefined,
        dataSource: valueConfig.dataSource,
        selectedFields: valueConfig.selectedFields,
        width: styleConfig.width,
        height: styleConfig.height,
        fontSize: styleConfig.fontSize,
        fontWeight: styleConfig.fontWeight,
        textColor: styleConfig.textColor,
        backgroundColor: styleConfig.backgroundColor,
        borderColor: styleConfig.borderColor,
        borderWidth: styleConfig.borderWidth,
        renderEffect: styleConfig.renderEffect || 'glass',
        iconPadding: styleConfig.iconPadding,
        lineType: styleConfig.lineType,
        shapeType: styleConfig.shapeType,
        nameFontSize: styleConfig.nameFontSize,
        nameColor: styleConfig.nameColor,
        textDirection: styleConfig.textDirection,
        unit: editingNodeData.unit,
        conversionFactor: editingNodeData.conversionFactor,
        decimalPlaces: editingNodeData.decimalPlaces,
      };

      setSelectedIcon(editingNodeData.logoIcon || 'cc-host');
      setLogoType(editingNodeData.logoType || 'default');
      setCurrentDataSource(valueConfig.dataSource || null);
      setSelectedFields(valueConfig.selectedFields || []);

      // 初始化阈值颜色配置
      if (
        styleConfig.thresholdColors &&
        Array.isArray(styleConfig.thresholdColors)
      ) {
        const sortedThresholds = [...styleConfig.thresholdColors].sort(
          (a, b) => parseFloat(b.value) - parseFloat(a.value)
        );
        setThresholdColors(sortedThresholds);
      } else {
        setThresholdColors([
          { color: '#fd666d', value: '70' },
          { color: '#EAB839', value: '30' },
          { color: '#299C46', value: '0' },
        ]);
      }

      if (editingNodeData.logoUrl) {
        setLogoPreview(editingNodeData.logoUrl);
      }

      if (valueConfig.dataSource && filteredDataSources.length > 0) {
        const selectedSource = filteredDataSources.find(
          (ds) => ds.id === valueConfig.dataSource
        );
        setSelectedDataSource(selectedSource);

        formValues.params = formValues.params || {};

        if (selectedSource?.params?.length) {
          setDefaultParamValues(selectedSource.params, formValues.params);

          if (valueConfig.dataSourceParams?.length) {
            restoreUserParamValues(
              valueConfig.dataSourceParams,
              formValues.params
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
      filteredDataSources,
      setSelectedDataSource,
      setDefaultParamValues,
      restoreUserParamValues,
      nodeType,
    ]
  );

  useEffect(() => {
    if (dataSources.length > 0 || !dataSourcesLoading) {
      if (editingNodeData) {
        initializeEditNode(editingNodeData);
      } else {
        initializeNewNode();
      }
    }
  }, [visible, dataSourcesLoading, editingNodeData]);

  const handleLogoUpload = useCallback(
    (file: any) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        setLogoPreview(e.target?.result as string);
        form.setFieldsValue({ logoUrl: e.target?.result });
      };
      reader.readAsDataURL(file);
      return false;
    },
    [form]
  );

  const handleLogoTypeChange = useCallback(
    (e: any) => {
      const type = e.target.value;
      setLogoType(type);

      if (type === 'default') {
        setLogoPreview('');
        form.setFieldsValue({ logoUrl: undefined });
      } else {
        setSelectedIcon('');
        form.setFieldsValue({ logoIcon: undefined });
      }
    },
    [form]
  );

  const handleSelectIcon = useCallback(() => {
    selectIconRef.current?.showModal({
      title: t('topology.nodeConfig.selectIcon'),
      defaultIcon: selectedIcon || 'server',
    });
  }, [selectedIcon, t]);

  const handleIconSelect = useCallback(
    (iconKey: string) => {
      setSelectedIcon(iconKey);
      form.setFieldsValue({ logoIcon: iconKey });
    },
    [form]
  );

  const handleDataSourceChange = useCallback(
    (dataSourceId: number) => {
      setCurrentDataSource(dataSourceId);
      const selectedSource = filteredDataSources.find(
        (ds) => ds.id === dataSourceId
      );
      setSelectedDataSource(selectedSource);
      setTreeData([]);
      setSelectedFields([]);

      const currentValues = form.getFieldsValue();
      form.setFieldsValue({
        ...currentValues,
        selectedFields: [],
      });

      if (selectedSource?.params?.length) {
        const params = currentValues.params || {};
        setDefaultParamValues(selectedSource.params, params);
        form.setFieldsValue({
          ...currentValues,
          selectedFields: [],
          params: params,
        });
      }
    },
    [filteredDataSources, setSelectedDataSource, form, setDefaultParamValues]
  );

  const fetchDataFields = useCallback(async () => {
    if (!currentDataSource) return;

    setLoadingData(true);
    try {
      const formValues = form.getFieldsValue();
      const userParams = formValues?.params || {};
      const requestParams = processDataSourceParams({
        sourceParams: selectedDataSource?.params,
        userParams: userParams,
      });

      const data: any = await getSourceDataByApiId(
        currentDataSource,
        requestParams
      );
      const tree = buildTreeData(data);
      setTreeData(tree);
    } catch (error) {
      console.error('Failed to fetch data fields:', error);
    } finally {
      setLoadingData(false);
    }
  }, [
    currentDataSource,
    form,
    selectedDataSource?.params,
    getSourceDataByApiId,
  ]);

  const handleFieldChange = useCallback(
    (checkedKeys: any) => {
      const keys = Array.isArray(checkedKeys)
        ? checkedKeys
        : checkedKeys.checked;

      const findNode = (nodes: any[], targetKey: string): any => {
        for (const node of nodes) {
          if (node.key === targetKey) {
            return node;
          }
          if (node.children) {
            const found = findNode(node.children, targetKey);
            if (found) return found;
          }
        }
        return null;
      };

      const leafKeys = keys.filter((key: string) => {
        const node = findNode(treeData, key);
        return node && node.isLeaf;
      });

      const newSelectedFields =
        leafKeys.length > 0 ? [leafKeys[leafKeys.length - 1]] : [];
      setSelectedFields(newSelectedFields);
      form.setFieldsValue({ selectedFields: newSelectedFields });
    },
    [form, treeData]
  );

  const renderColorPicker = useCallback(
    () => (
      <ColorPicker
        disabled={readonly}
        size="small"
        showText
        allowClear
        format="hex"
      />
    ),
    [readonly]
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

      ['textColor', 'backgroundColor', 'borderColor', 'nameColor'].forEach(
        (key) => {
          if (values[key]) {
            values[key] = processColorValue(values[key]);
          }
        }
      );

      if (values.params && selectedDataSource?.params) {
        values.dataSourceParams = processFormParamsForSubmit(
          values.params,
          selectedDataSource.params
        );
        delete values.params;
      }

      // 添加阈值颜色配置
      if (nodeType === 'single-value') {
        values.thresholdColors = thresholdColors;
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
    processColorValue,
  ]);

  const handleCancel = () => {
    if (onCancel) {
      onCancel();
    } else if (onClose) {
      onClose();
    }
  };

  const renderLogoSelector = useMemo(() => {
    if (nodeType !== 'icon') return null;

    return (
      <>
        <Form.Item
          label={t('topology.nodeConfig.logoType')}
          name="logoType"
          initialValue="default"
        >
          <Radio.Group onChange={handleLogoTypeChange} disabled={readonly}>
            <Radio value="default">{t('topology.nodeConfig.default')}</Radio>
            <Radio value="custom">{t('topology.nodeConfig.custom')}</Radio>
          </Radio.Group>
        </Form.Item>

        <Form.Item
          label=" "
          colon={false}
          name={logoType === 'default' ? 'logoIcon' : 'logoUrl'}
        >
          {logoType === 'default' ? (
            <div className="flex items-center space-x-3">
              <div
                onClick={handleSelectIcon}
                className="w-20 h-20 border-2 border-dashed border-[#d9d9d9] hover:border-[#40a9ff] cursor-pointer flex flex-col items-center justify-center rounded-lg transition-colors duration-200 bg-[#fafafa] hover:bg-[#f0f0f0]"
              >
                {selectedIcon ? (
                  <img
                    src={getIconUrl(selectedIcon)}
                    alt={t('topology.nodeConfig.selectedIcon')}
                    className="w-12 h-12 object-cover"
                  />
                ) : (
                  <>
                    <AppstoreOutlined className="text-xl text-[#8c8c8c] mb-1" />
                    <span className="text-xs text-[#8c8c8c]">
                      {t('topology.nodeConfig.selectIcon')}
                    </span>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center space-x-3">
              <Upload
                accept="image/*"
                showUploadList={false}
                beforeUpload={handleLogoUpload}
                disabled={readonly}
              >
                <div className="w-20 h-20 border-2 border-dashed border-[#d9d9d9] hover:border-[#40a9ff] cursor-pointer flex flex-col items-center justify-center rounded-lg transition-colors duration-200 bg-[#fafafa] hover:bg-[#f0f0f0]">
                  {logoPreview ? (
                    <img
                      src={logoPreview}
                      alt={t('topology.nodeConfig.uploadedImage')}
                      className="w-12 h-12 object-cover rounded-lg"
                    />
                  ) : (
                    <>
                      <UploadOutlined className="text-xl text-[#8c8c8c] mb-1" />
                      <span className="text-xs text-[#8c8c8c]">
                        {t('topology.nodeConfig.uploadImage')}
                      </span>
                    </>
                  )}
                </div>
              </Upload>
            </div>
          )}
        </Form.Item>
      </>
    );
  }, [
    nodeType,
    logoType,
    selectedIcon,
    logoPreview,
    readonly,
    handleLogoTypeChange,
    handleSelectIcon,
    handleLogoUpload,
    getIconUrl,
  ]);

  const renderDataSourceConfig = useMemo(() => {
    if (nodeType !== 'single-value') return null;

    return (
      <>
        <div className="mb-6">
          <div className="font-bold text-[var(--color-text-1)] mb-4">
            {t('topology.nodeConfig.dataSource')}
          </div>
          <Form.Item
            label={t('dashboard.dataSourceType')}
            name="dataSource"
            rules={[{ required: true, message: t('common.selectMsg') }]}
          >
            <DataSourceSelect
              loading={dataSourcesLoading}
              dataSources={filteredDataSources}
              placeholder={t('common.selectMsg')}
              style={{ width: '100%' }}
              onChange={handleDataSourceChange}
              disabled={readonly}
            />
          </Form.Item>
        </div>
        {selectedDataSource?.params && selectedDataSource.params.length > 0 && (
          <div className="mb-6">
            <div className="font-bold text-[var(--color-text-1)] mb-4">
              {t('dashboard.paramSettings')}
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
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="font-bold text-[var(--color-text-1)]">
              {t('topology.nodeConfig.dataSettings')}
            </div>
            <Button
              type="text"
              icon={<ReloadOutlined />}
              onClick={fetchDataFields}
              loading={loadingData}
              disabled={!currentDataSource || readonly || dataSourcesLoading}
              size="small"
              title={t('topology.nodeConfig.refreshDataFields')}
            />
          </div>

          <Form.Item
            name="selectedFields"
            rules={[
              {
                required: true,
                validator: (_, value) => {
                  if (!value || value.length === 0) {
                    return Promise.reject(
                      new Error(t('topology.nodeConfig.selectAtLeastOneField'))
                    );
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <div>
              {treeData.length > 0 ? (
                <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                  <div className="text-sm text-gray-600 mb-3">
                    {t('topology.nodeConfig.selectDataFields')}
                  </div>
                  <Tree
                    checkable
                    checkStrictly
                    defaultExpandAll
                    checkedKeys={selectedFields}
                    onCheck={handleFieldChange}
                    treeData={treeData}
                    height={300}
                    className="bg-white border border-gray-200 rounded p-2"
                  />
                </div>
              ) : currentDataSource ? (
                <div className="text-center py-4 text-gray-500">
                  {loadingData ? (
                    <div className="flex items-center justify-center">
                      <Spin size="small" className="mr-2" />
                      <span>{t('topology.nodeConfig.fetchingDataFields')}</span>
                    </div>
                  ) : (
                    <span>
                      {t('topology.nodeConfig.clickRefreshToGetFields')}
                    </span>
                  )}
                </div>
              ) : (
                <div className="text-center py-4 text-gray-500">
                  {t('topology.nodeConfig.selectDataSourceFirst')}
                </div>
              )}
            </div>
          </Form.Item>
        </div>
      </>
    );
  }, [
    nodeType,
    dataSourcesLoading,
    dataSources,
    selectedDataSource,
    currentDataSource,
    loadingData,
    treeData,
    selectedFields,
    readonly,
    handleDataSourceChange,
    fetchDataFields,
    handleFieldChange,
    t,
  ]);

  const renderStyleConfig = useMemo(() => {
    return (
      <div className="mb-6">
        <div className="font-bold text-[var(--color-text-1)] mb-4">
          {t('topology.styleSettings')}
        </div>

        {nodeType === 'single-value' && (
          <>
            <Form.Item
              label={t('topology.nodeConfig.fontSize')}
              name="fontSize"
            >
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

            {/* 阈值配色 */}
            <Form.Item label={t('topology.nodeConfig.thresholdColors')}>
              <div className="space-y-3">
                {thresholdColors.map((threshold, index) => {
                  const isBaseThreshold = index === thresholdColors.length - 1;

                  return (
                    <div
                      key={index}
                      className="flex items-center gap-2 p-2 border border-gray-200 rounded-md bg-gray-50"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-600 whitespace-nowrap">
                          {t('topology.nodeConfig.thresholdWhenValueGte')}
                        </span>
                        <InputNumber
                          value={parseFloat(threshold.value)}
                          onChange={(value) =>
                            handleThresholdChange(index, 'value', value || 0)
                          }
                          onBlur={(e) => {
                            if (!readonly && !isBaseThreshold) {
                              const value = parseFloat(e.target.value);
                              handleThresholdBlur(
                                index,
                                isNaN(value) ? 0 : value
                              );
                            }
                          }}
                          placeholder={t('common.inputMsg')}
                          disabled={readonly || isBaseThreshold}
                          style={{ width: '100px' }}
                          size="small"
                          min={0}
                        />
                        <span className="text-sm text-gray-600">
                          {t('topology.nodeConfig.thresholdShow')}
                        </span>
                      </div>
                      <ColorPicker
                        value={threshold.color}
                        onChange={(color) =>
                          handleThresholdChange(
                            index,
                            'color',
                            color.toHexString()
                          )
                        }
                        disabled={readonly}
                        size="small"
                        showText
                      />
                      <div className="flex items-center gap-3 pl-4">
                        {!readonly && (
                          <span
                            onClick={() => addThreshold(index)}
                            className="cursor-pointer text-gray-400 hover:text-gray-600 transition-colors duration-200"
                            style={{ fontSize: '16px' }}
                            title={t('topology.nodeConfig.addThresholdBelow')}
                          >
                            <PlusCircleOutlined />
                          </span>
                        )}
                        {!readonly && (
                          <span
                            onClick={
                              isBaseThreshold
                                ? undefined
                                : () => removeThreshold(index)
                            }
                            className={`transition-colors duration-200 ${
                              isBaseThreshold
                                ? 'text-gray-200 cursor-not-allowed'
                                : 'cursor-pointer text-gray-400 hover:text-gray-600'
                            }`}
                            style={{ fontSize: '16px' }}
                            title={
                              isBaseThreshold
                                ? t(
                                  'topology.nodeConfig.baseThresholdNotRemovable'
                                )
                                : t('topology.nodeConfig.removeThreshold')
                            }
                          >
                            <MinusCircleOutlined />
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
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
              {renderColorPicker()}
            </Form.Item>
          </>
        )}

        {['icon', 'basic-shape'].includes(nodeType) && (
          <>
            <Form.Item label={t('topology.nodeConfig.width')} name="width">
              <InputNumber
                min={20}
                max={2000}
                step={1}
                addonAfter="px"
                disabled={readonly}
                placeholder={t('common.inputMsg')}
                style={{ width: '120px' }}
              />
            </Form.Item>

            <Form.Item label={t('topology.nodeConfig.height')} name="height">
              <InputNumber
                min={20}
                max={nodeType === 'basic-shape' ? 500 : 300}
                step={1}
                addonAfter="px"
                disabled={readonly}
                placeholder={t('common.inputMsg')}
                style={{ width: '120px' }}
              />
            </Form.Item>
          </>
        )}

        {nodeType === 'icon' && (
          <>
            <Form.Item
              label={t('topology.nodeConfig.textPosition')}
              name="textDirection"
              initialValue="bottom"
            >
              <Select
                placeholder={t('topology.nodeConfig.selectTextPosition')}
                disabled={readonly}
              >
                <Select.Option value="top">
                  {t('topology.nodeConfig.textPositionTop')}
                </Select.Option>
                <Select.Option value="bottom">
                  {t('topology.nodeConfig.textPositionBottom')}
                </Select.Option>
                <Select.Option value="left">
                  {t('topology.nodeConfig.textPositionLeft')}
                </Select.Option>
                <Select.Option value="right">
                  {t('topology.nodeConfig.textPositionRight')}
                </Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.fontSize')}
              name="fontSize"
            >
              <InputNumber
                min={8}
                max={40}
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
              {renderColorPicker()}
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.backgroundColor')}
              name="backgroundColor"
            >
              {renderColorPicker()}
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.borderColor')}
              name="borderColor"
            >
              {renderColorPicker()}
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.iconPadding')}
              name="iconPadding"
            >
              <InputNumber
                min={0}
                max={80}
                step={1}
                addonAfter="px"
                disabled={readonly}
                placeholder={t('common.inputMsg')}
                style={{ width: '120px' }}
              />
            </Form.Item>
          </>
        )}

        {nodeType === 'basic-shape' && (
          <>
            <Form.Item
              label={t('topology.nodeConfig.renderEffect')}
              name="renderEffect"
            >
              <Radio.Group disabled={readonly}>
                <Radio value="normal">
                  {t('topology.nodeConfig.renderEffectNormal')}
                </Radio>
                <Radio value="glass">
                  {t('topology.nodeConfig.renderEffectGlass')}
                </Radio>
              </Radio.Group>
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.backgroundColor')}
              name="backgroundColor"
            >
              {renderColorPicker()}
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.borderColor')}
              name="borderColor"
            >
              {renderColorPicker()}
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.borderWidth')}
              name="borderWidth"
            >
              <InputNumber
                min={0}
                max={10}
                step={1}
                addonAfter="px"
                disabled={readonly}
                placeholder={t('common.inputMsg')}
                style={{ width: '120px' }}
              />
            </Form.Item>

            <Form.Item label={t('topology.lineType')} name="lineType">
              <Select placeholder={t('common.selectMsg')} disabled={readonly}>
                <Select.Option value="solid">
                  {t('topology.nodeConfig.solidLine')}
                </Select.Option>
                <Select.Option value="dashed">
                  {t('topology.nodeConfig.dashedLine')}
                </Select.Option>
                <Select.Option value="dotted">
                  {t('topology.nodeConfig.dottedLine')}
                </Select.Option>
              </Select>
            </Form.Item>
          </>
        )}

        {nodeType === 'text' && (
          <>
            <Form.Item
              label={t('topology.nodeConfig.textColor')}
              name="textColor"
            >
              {renderColorPicker()}
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.fontSize')}
              name="fontSize"
            >
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
              label={t('topology.nodeConfig.fontWeight')}
              name="fontWeight"
              initialValue="400"
            >
              <Select placeholder={t('common.selectMsg')} disabled={readonly}>
                <Select.Option value="500">400</Select.Option>
                <Select.Option value="500">500</Select.Option>
                <Select.Option value="600">600</Select.Option>
                <Select.Option value="700">700</Select.Option>
                <Select.Option value="800">800</Select.Option>
              </Select>
            </Form.Item>
          </>
        )}
      </div>
    );
  }, [nodeType, readonly, form, t]);

  const renderBasicSettings = useMemo(() => {
    return (
      <>
        <div className="font-bold text-[var(--color-text-1)] mb-4">
          {t('topology.nodeConfig.basicSettings')}
        </div>

        {nodeType === 'icon' && renderLogoSelector}

        <Form.Item label={t('topology.nodeConfig.name')} name="name">
          {nodeType === 'text' ? (
            <Input.TextArea
              placeholder={t('common.inputMsg')}
              disabled={readonly}
              rows={2}
              style={{ resize: 'vertical' }}
            />
          ) : (
            <Input placeholder={t('common.inputMsg')} disabled={readonly} />
          )}
        </Form.Item>

        {nodeType === 'single-value' && (
          <>
            <Form.Item label={t('topology.nodeConfig.unit')} name="unit">
              <Input
                placeholder={t('common.inputMsg')}
                disabled={readonly}
                style={{ width: '200px' }}
              />
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.conversionFactor')}
              name="conversionFactor"
            >
              <InputNumber
                min={0}
                max={100000}
                step={1}
                placeholder={t('common.inputMsg')}
                disabled={readonly}
                style={{ width: '120px' }}
              />
            </Form.Item>

            <Form.Item
              label={t('topology.nodeConfig.decimalPlaces')}
              name="decimalPlaces"
            >
              <InputNumber
                min={0}
                max={10}
                step={1}
                placeholder={t('common.inputMsg')}
                disabled={readonly}
                style={{ width: '120px' }}
              />
            </Form.Item>
          </>
        )}

        {nodeType === 'basic-shape' && (
          <Form.Item
            label={t('topology.nodeConfig.shapeType')}
            name="shapeType"
            rules={[{ required: true, message: t('common.selectMsg') }]}
          >
            <Select placeholder={t('common.selectMsg')} disabled={readonly}>
              <Select.Option value="rectangle">
                {t('topology.nodeConfig.rectangle')}
              </Select.Option>
              <Select.Option value="circle">
                {t('topology.nodeConfig.circle')}
              </Select.Option>
            </Select>
          </Form.Item>
        )}
      </>
    );
  }, [nodeType, readonly, renderLogoSelector, t]);

  return (
    <Drawer
      title={
        title ||
        t(`topology.nodeTitles.${nodeType}`) ||
        t('topology.nodeTitles.chart')
      }
      placement="right"
      width={600}
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
        {renderBasicSettings}
        {renderDataSourceConfig}
        {renderStyleConfig}
      </Form>

      <SelectIcon ref={selectIconRef} onSelect={handleIconSelect} />
    </Drawer>
  );
};

export default NodeConfPanel;
