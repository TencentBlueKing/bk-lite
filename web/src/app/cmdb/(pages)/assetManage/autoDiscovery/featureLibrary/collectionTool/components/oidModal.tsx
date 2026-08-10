'use client';

import React from 'react';
import { Modal, Input, Form, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

const LONG_TOOLTIP_OVERLAY_STYLE = {
  maxWidth: 'min(520px, calc(100vw - 48px))',
};

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
          label={(
            <span>
              {label || 'OID'}
              <Tooltip
                overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                title={t('CollectTool.oidHint')}
              >
                <QuestionCircleOutlined className="ml-1 text-[var(--color-text-tertiary)]" />
              </Tooltip>
            </span>
          )}
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
      </Form>
    </Modal>
  );
};

export default OidModal;
