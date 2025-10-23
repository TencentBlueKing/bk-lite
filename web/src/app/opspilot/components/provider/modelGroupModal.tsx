import React, { useEffect } from 'react';
import { Form, Input, Select, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ModelGroupModalProps } from '@/app/opspilot/types/provider';
import OperateModal from '@/components/operate-modal';

const TAG_OPTIONS = [
  { label: 'LLM', value: 'llm' },
  { label: 'Embed', value: 'embed' },
  { label: 'OCR', value: 'ocr' },
  { label: 'Rerank', value: 'rerank' },
];

const ModelGroupModal: React.FC<ModelGroupModalProps> = ({
  visible,
  mode,
  group,
  onOk,
  onCancel,
  confirmLoading,
}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();

  useEffect(() => {
    if (!visible) return;
    
    if (mode === 'edit' && group) {
      form.setFieldsValue({
        name: group.name,
        display_name: group.display_name,
        tags: group.tags || [],
      });
    } else {
      form.resetFields();
    }
  }, [visible, mode, group, form]);

  const handleOk = () => {
    form.validateFields()
      .then((values) => {
        const submitValues = {
          name: values.name,
          display_name: values.display_name,
          tags: values.tags || [],
          ...(mode === 'edit' && group?.icon && { icon: group.icon })
        };
        onOk(submitValues);
      })
      .catch((info) => {
        message.error(t('common.valFailed'));
        console.error(info);
      });
  };

  return (
    <OperateModal
      title={t(mode === 'add' ? 'common.add' : 'common.edit') + t('provider.group.title')}
      visible={visible}
      confirmLoading={confirmLoading}
      onOk={handleOk}
      onCancel={onCancel}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={t('provider.group.name')}
          rules={[
            { required: true, message: `${t('common.input')}${t('provider.group.name')}` }
          ]}
        >
          <Input placeholder={`${t('common.input')}${t('provider.group.name')}`} />
        </Form.Item>

        <Form.Item
          name="display_name"
          label={t('provider.group.displayName')}
          rules={[
            { required: true, message: `${t('common.input')}${t('provider.group.displayName')}` }
          ]}
        >
          <Input placeholder={`${t('common.input')}${t('provider.group.displayName')}`} />
        </Form.Item>

        <Form.Item
          name="tags"
          label={t('provider.group.tags')}
        >
          <Select
            mode="multiple"
            placeholder={`${t('common.select')}${t('provider.group.tags')}`}
            options={TAG_OPTIONS}
            allowClear
          />
        </Form.Item>
      </Form>
    </OperateModal>
  );
};

export default ModelGroupModal;