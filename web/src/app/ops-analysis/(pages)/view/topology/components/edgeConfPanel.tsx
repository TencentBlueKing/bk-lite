import React, { useEffect } from 'react';
import { useTranslation } from '@/utils/i18n';
import { COLORS } from '../constants/nodeDefaults';
import type {
  EdgeConfigPanelProps,
  EdgeData,
  InterfaceConfig,
} from '@/app/ops-analysis/types/topology';
import { normalizeColorPickerValue } from '../utils/formColorUtils';
import {
  Drawer,
  Form,
  Select,
  Input,
  Button,
  Space,
  Typography,
  Radio,
  ColorPicker,
  InputNumber,
  Switch,
} from 'antd';

interface EdgeConfigFormValues {
  lineType: EdgeData['lineType'];
  lineName?: string;
  lineColor?: unknown;
  lineWidth?: number;
  lineStyle?: NonNullable<EdgeData['styleConfig']>['lineStyle'];
  enableAnimation?: boolean;
  sourceInterfaceType?: InterfaceConfig['type'];
  sourceInterfaceValue?: string;
  targetInterfaceType?: InterfaceConfig['type'];
  targetInterfaceValue?: string;
}

const EdgeConfigPanel: React.FC<EdgeConfigPanelProps> = ({
  visible,
  readonly = false,
  edgeData,
  onClose,
  onConfirm,
}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const interfacesList: Array<{ label: string; value: string }> = [];

  useEffect(() => {
    if (edgeData) {
      const initialValues = {
        lineType: edgeData.lineType || 'common_line',
        lineName: edgeData.lineName || '',
        lineColor: edgeData.styleConfig?.lineColor || COLORS.EDGE.DEFAULT,
        lineWidth: edgeData.styleConfig?.lineWidth || 1,
        lineStyle: edgeData.styleConfig?.lineStyle || 'line',
        enableAnimation: edgeData.styleConfig?.enableAnimation || false,
        sourceInterfaceType: edgeData.sourceInterface?.type || 'existing',
        sourceInterfaceValue: edgeData.sourceInterface?.value || '',
        targetInterfaceType: edgeData.targetInterface?.type || 'existing',
        targetInterfaceValue: edgeData.targetInterface?.value || '',
      };
      form.setFieldsValue(initialValues);
    }
  }, [edgeData, form]);

  const handleFinish = (values: EdgeConfigFormValues) => {
    if (onConfirm && edgeData) {
      const result: EdgeData = {
        ...edgeData,
        lineType: values.lineType,
        lineName: values.lineName,
        styleConfig: {
          lineColor: normalizeColorPickerValue(values.lineColor) || COLORS.EDGE.DEFAULT,
          lineWidth: values.lineWidth || 1,
          lineStyle: values.lineStyle || 'line',
          enableAnimation: values.enableAnimation || false,
        },
        sourceInterface: {
          type: values.sourceInterfaceType || 'existing',
          value: values.sourceInterfaceValue || '',
        },
        targetInterface: {
          type: values.targetInterfaceType || 'existing',
          value: values.targetInterfaceValue || '',
        },
      };
      onConfirm(result);
    }
    onClose();
  };

  // 线条类型变化
  const handleLineTypeChange = (lineType: string) => {
    if (lineType === 'network_line') {
      form.setFieldValue('lineName', '');
    }
  };

  const canEnableAnimation = (arrowDirection: string, lineStyle: string) => {
    return (
      arrowDirection === 'single' &&
      (lineStyle === 'point' || lineStyle === 'dotted')
    );
  };

  // 渲染接口配置组件
  const renderInterfaceConfig = (
    nodeType: 'source' | 'target',
    nodeName: string
  ) => {
    const isSource = nodeType === 'source';
    const interfaceTypeField = isSource
      ? 'sourceInterfaceType'
      : 'targetInterfaceType';
    const interfaceValueField = isSource
      ? 'sourceInterfaceValue'
      : 'targetInterfaceValue';
    const nodeLabel = isSource ? t('topology.node1') : t('topology.node2');

    return (
      <div>
        <Typography.Text
          strong
          className="mb-2 block text-sm text-[var(--color-text-3)]"
        >
          {nodeLabel}
        </Typography.Text>
        <div className="mt-1.5 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-4">
          <Form.Item
            label={`${t('topology.nodeName')}：`}
            className="mb-2!"
          >
            <Typography.Text strong>{nodeName}</Typography.Text>
          </Form.Item>

          <div className="mt-4">
            <Form.Item
              name={interfaceTypeField}
              label={`${t('topology.interface')}：`}
              className="mb-2!"
            >
              <Radio.Group disabled={readonly}>
                <Radio value="existing">
                  {t('topology.existingInterface')}
                </Radio>
                <Radio value="custom">{t('topology.customInterface')}</Radio>
              </Radio.Group>
            </Form.Item>

            <Form.Item
              noStyle
              shouldUpdate={(prevValues, currentValues) =>
                prevValues[interfaceTypeField] !==
                currentValues[interfaceTypeField]
              }
            >
              {({ getFieldValue }) => {
                const interfaceType = getFieldValue(interfaceTypeField);
                return interfaceType === 'existing' ? (
                  <Form.Item
                    name={interfaceValueField}
                    rules={[{ required: true, message: t('common.selectTip') }]}
                    className="mb-2.5!"
                  >
                    <Select
                      placeholder={t('common.selectTip')}
                      options={interfacesList}
                      disabled={readonly}
                    />
                  </Form.Item>
                ) : (
                  <Form.Item
                    name={interfaceValueField}
                    rules={[{ required: true, message: t('common.inputMsg') }]}
                    className="mb-2.5!"
                  >
                    <Input
                      placeholder={t('common.inputMsg')}
                      disabled={readonly}
                    />
                  </Form.Item>
                );
              }}
            </Form.Item>
          </div>
        </div>
      </div>
    );
  };

  // 渲染线条名称配置
  const renderLineNameConfig = () => (
    <Form.Item
      noStyle
      shouldUpdate={(prevValues, currentValues) =>
        prevValues.lineType !== currentValues.lineType
      }
    >
      {({ getFieldValue }) => {
        const lineType = getFieldValue('lineType');
        return lineType === 'common_line' ? (
          <Form.Item label={t('topology.lineName')} name="lineName">
            <Input placeholder={t('common.inputMsg')} disabled={readonly} />
          </Form.Item>
        ) : null;
      }}
    </Form.Item>
  );

  // 渲染网络线配置
  const renderNetworkLineConfig = () => (
    <Form.Item
      noStyle
      shouldUpdate={(prevValues, currentValues) =>
        prevValues.lineType !== currentValues.lineType
      }
    >
      {({ getFieldValue }) => {
        const lineType = getFieldValue('lineType');
        return lineType === 'network_line' && edgeData ? (
          <div className="mt-6">
            <Space direction="vertical" size="middle" className="w-full">
              {renderInterfaceConfig('source', edgeData.sourceNode.name)}
              {renderInterfaceConfig('target', edgeData.targetNode.name)}
            </Space>
          </div>
        ) : null;
      }}
    </Form.Item>
  );

  if (!edgeData) return null;

  return (
    <Drawer
      title={readonly ? t('topology.edgeView') : t('topology.edgeSetting')}
      placement="right"
      width={600}
      open={visible}
      onClose={onClose}
      getContainer={() => document.body}
      zIndex={1200}
      bodyStyle={{ padding: 0 }}
      footer={
        <div className="px-6 py-4 text-right">
          <Space>
            <Button onClick={onClose}>
              {readonly ? t('common.close') : t('common.cancel')}
            </Button>
            {!readonly && (
              <Button type="primary" onClick={() => form.submit()}>
                {t('common.confirm')}
              </Button>
            )}
          </Space>
        </div>
      }
    >
      <div className="p-6">
        <Form
          form={form}
          layout="vertical"
          onFinish={handleFinish}
          initialValues={{
            lineType: edgeData?.lineType || 'common_line',
            lineName: edgeData?.lineName || '',
            lineColor: edgeData?.styleConfig?.lineColor || COLORS.EDGE.DEFAULT,
            lineWidth: edgeData?.styleConfig?.lineWidth || 1,
            lineStyle: edgeData?.styleConfig?.lineStyle || 'line',
            enableAnimation: edgeData?.styleConfig?.enableAnimation || false,
            sourceInterfaceType: edgeData?.sourceInterface?.type || 'existing',
            sourceInterfaceValue: edgeData?.sourceInterface?.value || '',
            targetInterfaceType: edgeData?.targetInterface?.type || 'existing',
            targetInterfaceValue: edgeData?.targetInterface?.value || '',
          }}
        >
          <div className="font-bold text-[var(--color-text-1)] mb-4">
            {t('topology.nodeConfig.basicSettings')}
          </div>
          {/* 线条类型选择 */}
          <Form.Item
            label={t('topology.lineType')}
            name="lineType"
            rules={[{ required: true, message: t('common.selectTip') }]}
          >
            <Select
              placeholder={t('common.selectTip')}
              onChange={handleLineTypeChange}
              disabled={readonly}
            >
              <Select.Option value="common_line">
                {t('topology.commonLine')}
              </Select.Option>
              <Select.Option value="network_line">
                {t('topology.networkLine')}
              </Select.Option>
            </Select>
          </Form.Item>

          {/* 线条名称配置 */}
          {renderLineNameConfig()}

          <div className="mb-6">
            <div className="font-bold text-[var(--color-text-1)] mb-4">
              {t('topology.styleSettings')}
            </div>

            <Form.Item
              label={t('topology.edgeConfig.lineColor')}
              name="lineColor"
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
              label={t('topology.edgeConfig.lineWidth')}
              name="lineWidth"
            >
              <InputNumber
                min={1}
                max={8}
                step={1}
                addonAfter="px"
                disabled={readonly}
                placeholder={t('common.inputMsg')}
                className="w-[120px]"
              />
            </Form.Item>

            <Form.Item
              label={t('topology.edgeConfig.lineStyle')}
              name="lineStyle"
            >
              <Select
                placeholder={t('common.selectTip')}
                disabled={readonly}
                onChange={(value) => {
                  const arrowDirection = edgeData?.arrowDirection || 'single';
                  if (!canEnableAnimation(arrowDirection, value)) {
                    form.setFieldValue('enableAnimation', false);
                  }
                }}
              >
                <Select.Option value="line">
                  {t('topology.edgeConfig.lineStyleSolid')}
                </Select.Option>
                <Select.Option value="dotted">
                  {t('topology.edgeConfig.lineStyleDotted')}
                </Select.Option>
                <Select.Option value="point">
                  {t('topology.edgeConfig.lineStylePoint')}
                </Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              noStyle
              shouldUpdate={(prevValues, currentValues) =>
                prevValues.lineStyle !== currentValues.lineStyle
              }
            >
              {({ getFieldValue }) => {
                const lineStyle = getFieldValue('lineStyle');
                const arrowDirection = edgeData?.arrowDirection || 'single';
                const animationEnabled = canEnableAnimation(
                  arrowDirection,
                  lineStyle
                );

                return (
                  <Form.Item
                    label={t('topology.edgeConfig.enableAnimation')}
                    name="enableAnimation"
                  >
                    <Switch disabled={readonly || !animationEnabled} />
                    {!animationEnabled && (
                      <div className="mt-1 text-xs text-[var(--color-text-2)]">
                        {t('topology.edgeConfig.animationTip')}
                      </div>
                    )}
                  </Form.Item>
                );
              }}
            </Form.Item>
          </div>

          {/* 网络线配置 */}
          {renderNetworkLineConfig()}
        </Form>
      </div>
    </Drawer>
  );
};

export default EdgeConfigPanel;
