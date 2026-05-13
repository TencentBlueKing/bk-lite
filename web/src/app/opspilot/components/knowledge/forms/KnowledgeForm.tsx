'use client';

import React, { useEffect } from 'react';
import { Form, Input, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import GroupTreeSelect from '@/components/group-tree-select';
import { getModelOptionText, renderModelOptionLabel } from '@/app/opspilot/utils/modelOption';

const { Option } = Select;

interface KnowledgeFormProps {
  form: any;
  modelOptions?: any[];
  initialValues?: any;
  isTraining?: boolean;
  visible: boolean;
}

const KnowledgeForm: React.FC<KnowledgeFormProps> = ({ form, modelOptions, initialValues, isTraining, visible }) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();

  useEffect(() => {
    if (!visible) return;
    if (initialValues) {
      form.setFieldsValue(initialValues);
    } else {
      form.resetFields();
      if (modelOptions && modelOptions.length > 0) {
        const enabledOption = modelOptions.find((o: any) => o.enabled);
        form.setFieldsValue({ embed_model: enabledOption?.id ?? modelOptions[0].id });
      }
    }
  }, [initialValues, visible, modelOptions]);

  return (
    <Form form={form} layout="vertical" name="knowledge_form">
      <Form.Item
        name="name"
        label={t('knowledge.form.name')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('knowledge.form.name')}!` }]}
      >
        <Input placeholder={`${t('common.inputMsg')}${t('knowledge.form.name')}`} />
      </Form.Item>
      {modelOptions && (
        <Form.Item
          name="embed_model"
          label={t('knowledge.form.embedModel')}
          tooltip={t('knowledge.form.embedModelTip')}
          rules={[{ required: true, message: `${t('common.selectMsg')}${t('knowledge.form.embedModel')}!` }]}
        >
          <Select placeholder={`${t('common.selectMsg')}${t('knowledge.form.embedModel')}`} disabled={isTraining}>
            {modelOptions.map((model: any) => (
              <Option key={model.id} value={model.id} disabled={!model.enabled} title={getModelOptionText(model)}>
                {renderModelOptionLabel(model)}
              </Option>
            ))}
          </Select>
        </Form.Item>
      )}
      <Form.Item
        name="team"
        label={t('knowledge.form.group')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('knowledge.form.group')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('knowledge.form.group')}`} />
      </Form.Item>
      <Form.Item
        name="introduction"
        label={t('knowledge.form.introduction')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('knowledge.form.introduction')}!` }]}
      >
        <Input.TextArea rows={4} placeholder={`${t('common.inputMsg')}${t('knowledge.form.introduction')}`} />
      </Form.Item>
    </Form>
  );
};

export default KnowledgeForm;
