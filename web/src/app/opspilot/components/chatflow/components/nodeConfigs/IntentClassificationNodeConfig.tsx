import React from 'react';
import { Form, Input, Select, Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import type { IntentClassificationNodeConfigProps } from './types';

const { Option } = Select;
const { TextArea } = Input;

export const IntentClassificationNodeConfig: React.FC<IntentClassificationNodeConfigProps> = ({
  t,
  skills,
  loadingSkills,
}) => {
  return (
    <div className="mb-4">
      <Form.Item
        name="agent"
        label={t('chatflow.nodeConfig.selectAgent')}
        rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseSelectAgent') }]}
      >
        <Select
          placeholder={t('chatflow.nodeConfig.pleaseSelectAgent')}
          loading={loadingSkills}
          showSearch
          filterOption={(input, option) => option?.label?.toString().toLowerCase().includes(input.toLowerCase()) ?? false}
        >
          {skills.map((s) => (
            <Option key={s.id} value={s.id} label={s.name}>{s.name}</Option>
          ))}
        </Select>
      </Form.Item>

      <Form.List name="intents">
        {(fields, { add, remove }) => (
          <>
            <div className="mb-3 flex items-center justify-between pb-2">
              <label className="text-sm font-medium text-[var(--color-text-2)]">{t('chatflow.nodeConfig.intentClassification')}</label>
              <Button
                type="dashed"
                onClick={() => add({ name: '' })}
                size="small"
                icon={<PlusOutlined />}
              >
                {t('chatflow.nodeConfig.addIntent')}
              </Button>
            </div>
            {fields.map((field, index) => (
              <div key={field.key} className="group mb-3 relative">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-semibold shadow-md">
                    {index + 1}
                  </div>
                  <span className="text-xs text-[var(--color-text-3)] font-medium">
                    {t('chatflow.nodeConfig.classification')} {index + 1}
                  </span>
                </div>
                <div className="relative">
                  <Form.Item
                    name={[field.name, 'name']}
                    rules={[{ required: true, message: t('chatflow.nodeConfig.intentNameRequired') }]}
                    className="mb-0"
                  >
                    <TextArea
                      rows={3}
                      placeholder={t('chatflow.nodeConfig.intentTopicPlaceholder')}
                    />
                  </Form.Item>
                  <Button
                    type="text"
                    danger
                    size="small"
                    icon={<Icon type="shanchu" className="text-base" />}
                    onClick={() => remove(field.name)}
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity z-10"
                    title={t('chatflow.nodeConfig.removeIntent')}
                  />
                </div>
              </div>
            ))}
          </>
        )}
      </Form.List>
    </div>
  );
};
