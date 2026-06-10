'use client';

import React from 'react';
import { Form, Switch, Radio, Select, InputNumber, Checkbox, Button, Space } from 'antd';
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
        label={t('settings.assignStrategy.escalationEnable')}
        valuePropName="checked"
        initialValue={false}
      >
        <Switch />
      </Form.Item>

      {enabled && (
        <>
          <Form.Item
            name={['escalation', 'mode']}
            label={t('settings.assignStrategy.escalationMode')}
            initialValue="append"
            rules={[{ required: true }]}
          >
            <Radio.Group>
              <Radio value="append">
                {t('settings.assignStrategy.escalationModeAppend')}
              </Radio>
              <Radio value="replace">
                {t('settings.assignStrategy.escalationModeReplace')}
              </Radio>
            </Radio.Group>
          </Form.Item>

          <Form.List
            name={['escalation', 'layers']}
            rules={[
              {
                validator: async (_, layers) => {
                  if (!layers || layers.length < 1) {
                    return Promise.reject(
                      new Error(
                        t('settings.assignStrategy.escalationLayerRequired')
                      )
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
                      key={`${field.key}-personnel`}
                      name={[field.name, 'personnel']}
                      label={t('settings.assignStrategy.formPersonnelSelect')}
                      rules={[{ required: true, message: t('settings.assignStrategy.escalationPersonnelTip') }]}
                    >
                      <Select mode="multiple" options={personnelOptions} />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      key={`${field.key}-wait`}
                      name={[field.name, 'wait_minutes']}
                      label={t('settings.assignStrategy.escalationWaitMinutes')}
                      initialValue={10}
                      rules={[{ required: true, type: 'number', min: 1 }]}
                    >
                      <InputNumber min={1} addonAfter={t('settings.assignStrategy.frequencyUnit')} />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      key={`${field.key}-channels`}
                      name={[field.name, 'notify_channels']}
                      label={t('settings.assignStrategy.escalationLayerChannel')}
                    >
                      <Checkbox.Group options={channelOptions} />
                    </Form.Item>
                  </div>
                ))}
                <Form.Item className="ml-[110px]">
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    {t('settings.assignStrategy.escalationAddLayer')}
                  </Button>
                  <Form.ErrorList errors={errors} />
                </Form.Item>
              </>
            )}
          </Form.List>
        </>
      )}
    </>
  );
};

export default EscalationChain;
