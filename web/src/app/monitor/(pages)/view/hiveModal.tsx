'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useRef,
} from 'react';
import { ModalRef, TableDataItem, MetricItem } from '@/app/monitor/types';
import { NodeThresholdColor } from '@/app/monitor/types/view';
import OperateModal from '@/components/operate-modal';
import { Button, Form, Select, InputNumber, ColorPicker, theme } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { AggregationColor } from 'antd/es/color-picker/color';
import { PlusOutlined, MinusOutlined } from '@ant-design/icons';
import type { ColorPickerProps } from 'antd';
import { cloneDeep } from 'lodash';
import { isStringArray } from '@/app/monitor/utils/common';
import { generate, green, presetPalettes, red } from '@ant-design/colors';
const { Option } = Select;

interface HiveModalProps {
  [key: string]: any;
}
type Presets = Required<ColorPickerProps>['presets'][number];

const genPresets = (presets = presetPalettes) => {
  return Object.entries(presets).map<Presets>(([label, colors]) => ({
    label,
    colors,
    key: label,
  }));
};

const HiveModal = forwardRef<ModalRef, HiveModalProps>(({ onConfirm }, ref) => {
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const { token } = theme.useToken();
  const presets = genPresets({
    primary: generate(token.colorPrimary),
    red,
    green,
  });
  const [title, setTitle] = useState<string>('');
  const [visible, setVisible] = useState<boolean>(false);
  const [hiveConfig, setHiveConfig] = useState<any>(null);
  const [selected, setSelected] = useState<string | null>();
  const [colorList, setColorList] = useState<NodeThresholdColor[]>([]);
  useImperativeHandle(ref, () => ({
    showModal: ({ title, form, query, color }) => {
      // 开启弹窗的交互
      setVisible(true);
      setTitle(title);
      setSelected(query);
      setHiveConfig(form);
      setColorList(color);
    },
  }));

  const handleSubmit = () => {
    formRef.current?.validateFields().then(() => {
      const list = colorList.sort((a, b) => b.value - a.value);
      onConfirm(selected, list);
      setVisible(false);
    });
  };

  const handleCancel = () => {
    setVisible(false);
  };

  const handleSelectedChange = (id: string) => {
    setSelected(id);
    const tagetMerticItem = hiveConfig.find(
      (item: MetricItem) => item.name === id
    );
    if (isStringArray(tagetMerticItem?.unit || '')) {
      const colors = JSON.parse(tagetMerticItem.unit).map(
        (item: TableDataItem) => ({
          value: item.id || 0,
          color: item.color || '#10e433',
        })
      );
      setColorList(colors);
      return;
    }
    setColorList([
      {
        value: 1,
        color: '#10e433',
      },
    ]);
  };

  const onChange = (value: number, index: number) => {
    const list = cloneDeep(colorList);
    list[index].value = value;
    setColorList(list);
  };

  const handleEnumColorChange = (value: AggregationColor, index: number) => {
    const list = cloneDeep(colorList);
    list[index].color = value.toHexString();
    setColorList(list);
  };

  const addInputNumber = (item: NodeThresholdColor, index: number) => {
    const _colorList = cloneDeep(colorList);
    _colorList.splice(index, 0, item);
    setColorList(_colorList);
  };

  const delInputNumber = (index: number) => {
    const _colorList = cloneDeep(colorList);
    _colorList.splice(index, 1);
    setColorList(_colorList);
  };

  // 自定义验证枚举列表
  const validateColorList = async () => {
    if (
      colorList.some((item) => {
        return Object.values(item).some((tex) => {
          return tex !== 0 && !tex;
        });
      })
    ) {
      return Promise.reject(new Error(t('common.inputRequired')));
    }
    return Promise.resolve();
  };

  const validateSelectedList = async () => {
    if (!selected) {
      return Promise.reject(new Error(t('monitor.events.conditionValidate')));
    }
    return Promise.resolve();
  };

  return (
    <>
      <OperateModal
        visible={visible}
        title={title}
        width={500}
        onCancel={handleCancel}
        footer={
          <div>
            <Button className="mr-[10px]" type="primary" onClick={handleSubmit}>
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Form
          ref={formRef}
          name="basic"
          wrapperCol={{ span: 24 }}
          style={{ maxWidth: 500 }}
          layout="vertical"
          initialValues={{ remember: true }}
          autoComplete="off"
        >
          <Form.Item<any>
            label={t('monitor.views.displayIndicators')}
            name="selected"
            rules={[{ required: true, validator: validateSelectedList }]}
          >
            <Select
              className="w-[160px]"
              defaultValue={selected}
              showSearch
              value={selected}
              placeholder={t('common.selectMsg')}
              onChange={handleSelectedChange}
            >
              {hiveConfig?.map((item: MetricItem, index: number) => (
                <Option key={index} value={item.name}>
                  {item.display_name}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item<any>
            label={t('monitor.events.thresholdColor')}
            name="colorSelect"
            rules={[{ required: true, validator: validateColorList }]}
          >
            <div className="flex justify-center flex-col">
              {(colorList || []).map((item, index) => {
                return (
                  <div
                    className="flex justify-start items-center mb-2"
                    key={index}
                  >
                    <ColorPicker
                      className="ml-2 mr-2 h-4"
                      size="small"
                      value={item.color}
                      presets={presets}
                      placement="bottom"
                      onChange={(value) => {
                        handleEnumColorChange(value, index);
                      }}
                    />
                    <InputNumber
                      value={item.value}
                      className="w-[60%] mr-2"
                      min={0}
                      max={100}
                      onChange={(value) => onChange(value as number, index)}
                    />
                    <Button
                      className="mr-2"
                      icon={<PlusOutlined />}
                      onClick={() => addInputNumber(item, index)}
                    />
                    {!!index && (
                      <Button
                        icon={<MinusOutlined />}
                        onClick={() => delInputNumber(index)}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
});

HiveModal.displayName = 'HiveModal';
export default HiveModal;
