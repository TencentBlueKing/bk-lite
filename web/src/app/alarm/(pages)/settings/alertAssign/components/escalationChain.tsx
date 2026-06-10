'use client';

import React from 'react';
import { Form, Switch, Select, InputNumber, Checkbox, Button, Space } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface Option {
  label: string;
  value: string;
}

interface EscalationChainProps {
  enabled: boolean;
  personnelOptions: Option[];
  channelOptions: Option[];
}

// 当前 UI 约束最多 3 层；后端与数据模型不限层数，可后续放开。
const MAX_LAYERS = 3;

// 升级层级内字段统一竖排（label 独占一行），避免长 label 在窄标签列被截断/遮挡。
const layerItemLayout = {
  labelCol: { span: 24 },
  wrapperCol: { span: 24 },
};

const EscalationChain: React.FC<EscalationChainProps> = ({
  enabled,
  personnelOptions,
  channelOptions,
}) => {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item
        name={['escalation', 'enabled']}
        label={t('settings.assignStrategy.escalation')}
        valuePropName="checked"
        initialValue={false}
      >
        <Switch />
      </Form.Item>

      {enabled && (
        <Form.List
          name={['escalation', 'layers']}
          rules={[
            {
              validator: async (_, layers) => {
                if (!layers || layers.length < 1) {
                  return Promise.reject(
                    new Error(t('settings.assignStrategy.escalationLayerRequired'))
                  );
                }
              },
            },
          ]}
        >
          {(fields, { add, remove }, { errors }) => (
            <>
              {fields.map((field, index) => (
                <div
                  key={field.key}
                  className="border rounded p-3 mb-3 ml-[110px]"
                >
                  <Space align="baseline" className="w-full justify-between">
                    <span className="font-bold">
                      {t('settings.assignStrategy.escalationLayer')} {index + 1}
                    </span>
                    <MinusCircleOutlined onClick={() => remove(field.name)} />
                  </Space>
                  <Form.Item
                    {...field}
                    {...layerItemLayout}
                    key={`${field.key}-personnel`}
                    name={[field.name, 'personnel']}
                    label={t('settings.assignStrategy.formPersonnelSelect')}
                    rules={[
                      {
                        required: true,
                        message: t('settings.assignStrategy.escalationPersonnelTip'),
                      },
                    ]}
                  >
                    <Select mode="multiple" options={personnelOptions} />
                  </Form.Item>
                  <Form.Item
                    {...field}
                    {...layerItemLayout}
                    key={`${field.key}-wait`}
                    name={[field.name, 'wait_minutes']}
                    label={t('settings.assignStrategy.escalationWaitMinutes')}
                    initialValue={10}
                    rules={[{ required: true, type: 'number', min: 1 }]}
                  >
                    <InputNumber
                      min={1}
                      className="w-[200px]"
                      addonAfter={t('settings.assignStrategy.frequencyUnit')}
                    />
                  </Form.Item>
                  <Form.Item
                    {...field}
                    {...layerItemLayout}
                    key={`${field.key}-channels`}
                    name={[field.name, 'notify_channels']}
                    label={t('settings.assignStrategy.escalationLayerChannel')}
                  >
                    <Checkbox.Group options={channelOptions} />
                  </Form.Item>
                </div>
              ))}
              {fields.length < MAX_LAYERS && (
                <Form.Item className="ml-[110px]">
                  <Button
                    type="dashed"
                    onClick={() => add()}
                    block
                    icon={<PlusOutlined />}
                  >
                    {t('settings.assignStrategy.escalationAddLayer')}
                  </Button>
                  <Form.ErrorList errors={errors} />
                </Form.Item>
              )}
            </>
          )}
        </Form.List>
      )}
    </>
  );
};

export default EscalationChain;
