/**
 * 形状节点配置面板
 * 处理纯视觉节点：icon / basic-shape / text（不包含数据源逻辑）
 */
import React, {
  useEffect,
  useState,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { NodeConfPanelProps } from '@/app/ops-analysis/types/topology';
import { iconList } from '@/app/cmdb/utils/common';
import { NODE_DEFAULTS } from '../constants/nodeDefaults';
import { useTranslation } from '@/utils/i18n';
import SelectIcon, {
  SelectIconRef,
} from '@/app/cmdb/(pages)/assetManage/management/list/selectIcon';
import {
  Form,
  Input,
  InputNumber,
  Upload,
  Radio,
  Button,
  Drawer,
  Select,
  ColorPicker,
} from 'antd';
import {
  UploadOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';

const NODE_TYPE_DEFAULTS = {
  icon: NODE_DEFAULTS.ICON_NODE,
  'basic-shape': NODE_DEFAULTS.BASIC_SHAPE_NODE,
  text: NODE_DEFAULTS.TEXT_NODE,
} as const;

const ShapeNodePanel: React.FC<NodeConfPanelProps> = ({
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
  const initializedRef = useRef<string | null>(null);

  const selectIconRef = useRef<SelectIconRef>(null);
  const { t } = useTranslation();

  const nodeDefaults = useMemo(() => {
    return (
      NODE_TYPE_DEFAULTS[nodeType as keyof typeof NODE_TYPE_DEFAULTS] ||
      NODE_DEFAULTS.ICON_NODE
    );
  }, [nodeType]);

  const getIconUrl = useCallback((iconKey: string) => {
    const iconItem = iconList.find((item) => item.key === iconKey);
    return iconItem
      ? `/assets/icons/${iconItem.url}.svg`
      : `/assets/icons/cc-default_默认.svg`;
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
      name: '',
      width: nodeDefaults.width,
      height: nodeDefaults.height,
    };

    if (nodeType === 'basic-shape') {
      const basicShapeDefaults =
        nodeDefaults as typeof NODE_DEFAULTS.BASIC_SHAPE_NODE;
      defaultValues.borderWidth = basicShapeDefaults.borderWidth;
      defaultValues.lineType = basicShapeDefaults.lineType;
      defaultValues.shapeType = basicShapeDefaults.shapeType;
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

    form.resetFields();
    form.setFieldsValue(defaultValues);
  }, [form, nodeType, nodeDefaults]);

  const initializeEditNode = useCallback(
    (editingNodeData: any) => {
      const { styleConfig = {} } = editingNodeData;

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
        width: styleConfig.width,
        height: styleConfig.height,
        fontSize: styleConfig.fontSize,
        fontWeight: styleConfig.fontWeight,
        textColor: styleConfig.textColor,
        backgroundColor: styleConfig.backgroundColor,
        borderColor: styleConfig.borderColor,
        borderWidth: styleConfig.borderWidth,
        iconPadding: styleConfig.iconPadding,
        lineType: styleConfig.lineType,
        shapeType: styleConfig.shapeType,
        textDirection: styleConfig.textDirection,
      };

      setSelectedIcon(editingNodeData.logoIcon || 'cc-host');
      setLogoType(editingNodeData.logoType || 'default');

      if (editingNodeData.logoUrl) {
        setLogoPreview(editingNodeData.logoUrl);
      }

      form.setFieldsValue(formValues);
    },
    [form, nodeType]
  );

  useEffect(() => {
    if (!visible) {
      initializedRef.current = null;
      return;
    }

    const initKey = editingNodeData?.id || '__new__';
    if (initializedRef.current === initKey) {
      return;
    }

    initializedRef.current = initKey;

    if (editingNodeData) {
      initializeEditNode(editingNodeData);
    } else {
      initializeNewNode();
    }
  }, [visible, editingNodeData, initializeEditNode, initializeNewNode]);

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

      ['textColor', 'backgroundColor', 'borderColor'].forEach((key) => {
        if (values[key]) {
          values[key] = processColorValue(values[key]);
        }
      });

      onConfirm?.(values);
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  }, [form, onConfirm, processColorValue]);

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
    t,
  ]);

  const renderStyleConfig = useMemo(() => {
    return (
      <div className="mb-6">
        <div className="font-bold text-[var(--color-text-1)] mb-4">
          {t('topology.styleSettings')}
        </div>

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
                <Select.Option value="400">400</Select.Option>
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
  }, [nodeType, readonly, renderColorPicker, t]);

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
        {renderStyleConfig}
      </Form>

      <SelectIcon ref={selectIconRef} onSelect={handleIconSelect} />
    </Drawer>
  );
};

export default ShapeNodePanel;
