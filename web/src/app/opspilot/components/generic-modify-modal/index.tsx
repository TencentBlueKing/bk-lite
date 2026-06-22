'use client';

import React, { useState } from 'react';
import { Form } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import SkillForm from './SkillForm';
import StudioForm from './StudioForm';

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

  const handleConfirm = async () => {
    try {
      setConfirmLoading(true);
      const values = await form.validateFields();
      await onConfirm(values);
      form.resetFields();
      setConfirmLoading(false);
    } catch {
      setConfirmLoading(false);
    }
  };

  const handleCancel = () => {
    // 取消时清空表单，避免下次打开粘连上一次（未保存）的编辑内容
    form.resetFields();
    onCancel();
  };

  const renderForm = () => {
    if (formType === 'skill') {
      return <SkillForm form={form} initialValues={initialValues} visible={visible} />;
    }
    if (formType === 'studio') {
      return <StudioForm form={form} initialValues={initialValues} visible={visible} />;
    }
    return null;
  };

  return (
    <OperateModal
      width={800}
      visible={visible}
      title={initialValues ? t('common.edit') : t('common.add')}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onCancel={handleCancel}
      onOk={handleConfirm}
      confirmLoading={confirmLoading}
    >
      {renderForm()}
    </OperateModal>
  );
};

export default GenericModifyModal;
