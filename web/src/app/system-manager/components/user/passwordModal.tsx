import React, { useState, forwardRef, useImperativeHandle, useRef } from 'react';
import { Form, Input, message, Switch } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import { useUserApi } from '@/app/system-manager/api/user/index';

export interface PasswordModalRef {
  showModal: (config: { userId: string }) => void;
}

const PasswordModal = forwardRef<PasswordModalRef, { onSuccess: () => void }>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [userId, setUserId] = useState('');
    const formRef = useRef<FormInstance>(null);
    const { setUserPassword } = useUserApi();

    useImperativeHandle(ref, () => ({
      showModal: ({ userId }) => {
        setUserId(userId);
        setVisible(true);
        formRef.current?.resetFields();
      },
    }));

    const handleCancel = () => {
      setVisible(false);
    };

    const handleConfirm = async () => {
      try {
        setIsSubmitting(true);
        const values = await formRef.current?.validateFields();
        await setUserPassword({ id: userId, password: values.password, temporary: values.temporary ?? false });
        message.success(t('common.updateSuccess'));
        onSuccess();
        setVisible(false);
      } catch {
        message.error(t('common.operationFailed'));
      } finally {
        setIsSubmitting(false);
      }
    };

    return (
      <OperateModal
        title={t('system.user.passwordTitle')}
        visible={visible}
        onCancel={handleCancel}
        onOk={handleConfirm}
        confirmLoading={isSubmitting}
      >
        <Form layout="vertical" ref={formRef}>
          <Form.Item
            name="password"
            label={t('system.user.form.password')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input.Password placeholder={`${t('common.inputMsg')}${t('system.user.form.password')}`} />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label={t('system.user.form.confirmPassword')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('common.inputRequired') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(
                    new Error(t('system.user.form.passwordMismatch'))
                  );
                },
              }),
            ]}
          >
            <Input.Password placeholder={`${t('common.inputMsg')}${t('system.user.form.confirmPassword')}`} />
          </Form.Item>
          <Form.Item
            name="temporary"
            label={t('system.user.form.temporary')}
            valuePropName="checked"
            tooltip={t('system.user.form.tempTooltip')}>
            <Switch size="small" />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

PasswordModal.displayName = 'PasswordModal';
export default PasswordModal;
