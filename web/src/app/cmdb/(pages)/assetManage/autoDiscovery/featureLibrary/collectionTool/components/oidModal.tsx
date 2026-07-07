'use client';

import React from 'react';
import { Modal, Input, Form, Typography } from 'antd';
import { useTranslation } from '@/utils/i18n';

const { Text } = Typography;

interface OidModalProps {
  open: boolean;
  onConfirm: (oid: string) => void;
  onCancel: () => void;
  title?: string;
  label?: string;
  placeholder?: string;
}

const OidModal: React.FC<OidModalProps> = ({
  open,
  onConfirm,
  onCancel,
  title,
  label,
  placeholder,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onConfirm(values.oid);
      form.resetFields();
    } catch {
      // validation error shown inline
    }
  };

  const handleCancel = () => {
    form.resetFields();
    onCancel();
  };

  return (
    <Modal
      title={title || t('CollectTool.getOidTitle')}
      open={open}
      centered
      onOk={handleOk}
      onCancel={handleCancel}
      okText={t('CollectTool.confirm')}
      cancelText={t('CollectTool.cancel')}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label={label || 'OID'}
          name="oid"
          style={{ marginBottom: 8 }}
          rules={[
            { required: true, message: t('CollectTool.oidRequired') },
            {
              pattern: /^[\d.]+$/,
              message: t('CollectTool.oidFormatError'),
            },
          ]}
        >
          <Input placeholder={placeholder || t('CollectTool.oidPlaceholder')} />
        </Form.Item>
        <Text type="secondary" className="block text-xs leading-5">
          {t('CollectTool.oidHint')}
        </Text>
      </Form>
    </Modal>
  );
};

export default OidModal;
