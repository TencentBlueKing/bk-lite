'use client';

import React, { useEffect, useState } from 'react';
import { Form } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import CommonForm from '@/app/opspilot/components/knowledge/commonForm';

interface GenericModifyModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: any) => void;
  initialValues: any;
  formType: string;
}

const GenericModifyModal: React.FC<GenericModifyModalProps> = ({ visible, onCancel, onConfirm, initialValues, formType }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    if (!visible) return;

    Promise.resolve().then(() => {
      if (initialValues) {
        form.setFieldsValue(initialValues);
      } else {
        form.resetFields();
      }
    });
  }, [initialValues, form, visible]);

  const handleConfirm = async () => {
    try {
      setConfirmLoading(true);
      const values = await form.validateFields();
      console.log('values', values);
      await onConfirm(values);
      form.resetFields();
      setConfirmLoading(false);
    } catch {
      setConfirmLoading(false);
    }
  };

  return (
    <OperateModal
      visible={visible}
      title={initialValues ? t('common.edit') : t('common.add')}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onCancel={onCancel}
      onOk={handleConfirm}
      confirmLoading={confirmLoading}
    >
      <CommonForm 
        form={form} 
        formType={formType} 
        visible={visible} 
      />
    </OperateModal>
  );
};

export default GenericModifyModal;
