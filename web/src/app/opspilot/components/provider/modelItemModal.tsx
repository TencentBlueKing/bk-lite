'use client';

import React, { useEffect } from 'react';
import { Form, Input, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import type { Model } from '@/app/opspilot/types/provider';

interface ModelItemModalValues {
  name: string;
  model: string;
  team: number[];
}

interface ModelItemModalProps {
  visible: boolean;
  mode: 'add' | 'edit';
  model?: Model | null;
  confirmLoading?: boolean;
  onOk: (values: ModelItemModalValues) => Promise<void>;
  onCancel: () => void;
}

const ModelItemModal: React.FC<ModelItemModalProps> = ({
  visible,
  mode,
  model,
  confirmLoading = false,
  onOk,
  onCancel,
}) => {
  const [form] = Form.useForm<ModelItemModalValues>();
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();

  useEffect(() => {
    if (!visible) {
      return;
    }

    if (mode === 'edit' && model) {
      form.setFieldsValue({
        name: model.name || '',
        model: model.model || model.llm_config?.model || model.embed_config?.model || model.rerank_config?.model || model.ocr_config?.model || '',
        team: model.team || [],
      });
      return;
    }

    form.resetFields();
    form.setFieldsValue({
      name: '',
      model: '',
      team: selectedGroup ? [Number(selectedGroup.id)] : [],
    });
  }, [form, mode, model, selectedGroup, visible]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await onOk(values);
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
      destroyOnClose
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
          className="mb-0"
        >
          <GroupTreeSelect
            value={form.getFieldValue('team') || []}
            onChange={(value) => form.setFieldValue('team', value)}
            placeholder={t('provider.model.availableGroupsPlaceholder')}
            multiple
          />
        </Form.Item>
      </Form>
    </OperateModal>
  );
};

export default ModelItemModal;
