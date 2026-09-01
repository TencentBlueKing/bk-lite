'use client';

import React, { useEffect } from 'react';
import { Form, Input, InputNumber, Select, Switch, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import type { Model, ProviderResourceType } from '@/app/opspilot/types/provider';
import {
  DEFAULT_CONTEXT_WINDOW_UNIT,
  DEFAULT_CONTEXT_WINDOW_VALUE,
  isContextWindowTokensInRange,
  tokensFromWindowInput,
  windowInputFromTokens,
  type ContextWindowUnit,
} from '@/app/opspilot/utils/contextWindow';

interface ModelItemModalValues {
  name: string;
  model: string;
  team: number[];
  is_multimodal?: boolean;
  context_window_tokens?: number;
}

interface ModelItemFormValues {
  name: string;
  model: string;
  team: number[];
  is_multimodal?: boolean;
  context_window_value?: number;
  context_window_unit?: ContextWindowUnit;
}

interface ModelItemModalProps {
  visible: boolean;
  mode: 'add' | 'edit';
  resourceType: ProviderResourceType;
  model?: Model | null;
  confirmLoading?: boolean;
  onOk: (values: ModelItemModalValues) => Promise<void>;
  onCancel: () => void;
}

const ModelItemModal: React.FC<ModelItemModalProps> = ({
  visible,
  mode,
  resourceType,
  model,
  confirmLoading = false,
  onOk,
  onCancel,
}) => {
  const [form] = Form.useForm<ModelItemFormValues>();
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const showLlmExtras = resourceType === 'llm_model';

  useEffect(() => {
    if (!visible) {
      return;
    }

    if (mode === 'edit' && model) {
      const windowInput = windowInputFromTokens(model.context_window_tokens);
      form.setFieldsValue({
        name: model.name || '',
        model: model.model || model.llm_config?.model || model.embed_config?.model || model.rerank_config?.model || model.ocr_config?.model || '',
        team: model.team || [],
        is_multimodal: model.is_multimodal ?? true,
        context_window_value: windowInput.value,
        context_window_unit: windowInput.unit,
      });
      return;
    }

    form.resetFields();
    form.setFieldsValue({
      name: '',
      model: '',
      team: selectedGroup ? [Number(selectedGroup.id)] : [],
      is_multimodal: true,
      context_window_value: DEFAULT_CONTEXT_WINDOW_VALUE,
      context_window_unit: DEFAULT_CONTEXT_WINDOW_UNIT,
    });
  }, [form, mode, model, selectedGroup, visible]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload: ModelItemModalValues = {
        name: values.name,
        model: values.model,
        team: values.team,
        is_multimodal: values.is_multimodal,
      };
      if (showLlmExtras) {
        const tokens = tokensFromWindowInput(Number(values.context_window_value), values.context_window_unit || DEFAULT_CONTEXT_WINDOW_UNIT);
        if (!isContextWindowTokensInRange(tokens)) {
          form.setFields([
            {
              name: 'context_window_value',
              errors: [t('provider.model.contextWindowRange')],
            },
          ]);
          return;
        }
        payload.context_window_tokens = tokens;
      }
      await onOk(payload);
    } catch {
      message.error(t('common.valFailed'));
    }
  };

  return (
    <OperateModal
      title={t(mode === 'add' ? 'provider.model.addTitle' : 'provider.model.editTitle')}
      visible={visible}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={confirmLoading}
      okText={t(mode === 'add' ? 'provider.model.add' : 'common.save')}
      cancelText={t('common.cancel')}
      width={520}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="model"
          label={t('provider.model.modelId')}
          rules={[{ required: true, message: t('provider.model.modelIdRequired') }]}
          className="mb-4"
        >
          <Input placeholder={t('provider.model.modelIdPlaceholder')} />
        </Form.Item>

        <Form.Item
          name="name"
          label={t('provider.model.modelName')}
          rules={[{ required: true, message: t('provider.model.modelNameRequired') }]}
          className="mb-4"
        >
          <Input placeholder={t('provider.model.modelNamePlaceholder')} />
        </Form.Item>

        <Form.Item
          name="team"
          label={t('provider.model.availableGroups')}
          rules={[{ required: true, message: t('provider.model.availableGroupsRequired') }]}
          className={showLlmExtras ? 'mb-4' : 'mb-0'}
        >
          <GroupTreeSelect
            value={form.getFieldValue('team') || []}
            onChange={(value) => form.setFieldValue('team', value)}
            placeholder={t('provider.model.availableGroupsPlaceholder')}
            multiple
          />
        </Form.Item>

        {showLlmExtras ? (
          <>
            <Form.Item
              name="is_multimodal"
              label={t('provider.model.multimodal')}
              valuePropName="checked"
              className="mb-4"
              extra={t('provider.model.multimodalHint')}
            >
              <Switch />
            </Form.Item>
            <Form.Item label={t('provider.model.contextWindow')} extra={t('provider.model.contextWindowHint')} className="mb-0" required>
              <div className="flex gap-2">
                <Form.Item
                  name="context_window_value"
                  rules={[{ required: true, message: t('provider.model.contextWindowRequired') }]}
                  className="mb-0 flex-1"
                >
                  <InputNumber className="w-full" min={1} precision={0} />
                </Form.Item>
                <Form.Item name="context_window_unit" className="mb-0 w-20">
                  <Select
                    options={[
                      { value: 'K', label: 'K' },
                      { value: 'M', label: 'M' },
                    ]}
                  />
                </Form.Item>
              </div>
            </Form.Item>
          </>
        ) : null}
      </Form>
    </OperateModal>
  );
};

export default ModelItemModal;
