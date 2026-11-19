import React from 'react';
import { Form, Input, Select, Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { filterModelOption, getModelOptionText, renderModelOptionLabel, withBoundUnavailableModels } from '@/app/opspilot/utils/modelOption';
import type { IntentClassificationNodeConfigProps } from './types';

const { Option } = Select;
const { TextArea } = Input;

export const IntentClassificationNodeConfig: React.FC<IntentClassificationNodeConfigProps> = ({
  t,
  llmModels,
  loadingLlmModels,
  form,
}) => {
  const llmModelId = Form.useWatch('llmModel', form);
  const llmModelName = Form.useWatch('llmModelName', form);
  const modelChoices = withBoundUnavailableModels(
    llmModels,
    llmModelId,
    typeof llmModelName === 'string' && llmModelName ? [{ id: Number(llmModelId), name: llmModelName }] : [],
  );
  return (
    <div className="mb-4">
      <Form.Item
        name="llmModel"
        label={t('chatflow.nodeConfig.llmModel')}
        rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseSelectLlmModel') }]}
      >
        <Select
          placeholder={t('chatflow.nodeConfig.pleaseSelectLlmModel')}
          loading={loadingLlmModels}
          showSearch
          filterOption={filterModelOption}
          onChange={(modelId) => {
            const selectedModel = llmModels.find((model) => model.id === modelId);
            form.setFieldsValue({ llmModelName: selectedModel?.name || '' });
          }}
        >
          {modelChoices.map(({ model, disabled }) => {
            const unavailableMark = disabled ? t('modelOption.unavailable', '已停用') : undefined;
            return (
              <Option key={model.id} value={model.id} disabled={disabled} title={getModelOptionText(model, unavailableMark)}>
                {renderModelOptionLabel(model, unavailableMark)}
              </Option>
            );
          })}
        </Select>
      </Form.Item>
      <Form.Item name="llmModelName" className="hidden">
        <Input />
      </Form.Item>
      <Form.Item
        name="classificationRules"
        label={t('chatflow.nodeConfig.classificationRules')}
        tooltip={t('chatflow.nodeConfig.classificationRulesTooltip')}
      >
        <TextArea rows={4} placeholder={t('chatflow.nodeConfig.classificationRulesPlaceholder')} />
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
