'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Button, Form, message, Input } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useLogApi from '@/app/log/api/search';
import { ModalRef, ModalProps } from '@/app/log/types';
import { StoreConditions } from '@/app/log/types/search';
import { useTranslation } from '@/utils/i18n';
import { cloneDeep } from 'lodash';

const AddConditions = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const { saveLogCondition } = useLogApi();
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const [visible, setVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [configForm, setConfigForm] = useState<StoreConditions>({});
  const [title, setTitle] = useState<string>('');

  useImperativeHandle(ref, () => ({
    showModal: ({ title, form }) => {
      setTitle(title);
      setConfigForm(cloneDeep(form));
      setVisible(true);
    },
  }));

  useEffect(() => {
    if (visible) {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        name: configForm.name,
      });
    }
  }, [visible, configForm]);

  const handleOperate = async (params: any) => {
    try {
      setConfirmLoading(true);
      await saveLogCondition(params);
      message.success(t('common.successfullyAdded'));
      handleCancel();
      onSuccess?.();
    } catch (error) {
      console.log(error);
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleSubmit = () => {
    formRef.current?.validateFields().then((values) => {
      handleOperate({
        name: values.name,
        condition: configForm,
      });
    });
  };

  const handleCancel = () => {
    setVisible(false);
  };

  return (
    <div>
      <OperateModal
        width={600}
        title={title}
        visible={visible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={confirmLoading}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Form ref={formRef} name="basic" layout="vertical">
          <Form.Item<StoreConditions>
            label={t('common.name')}
            name="name"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
});
AddConditions.displayName = 'AddConditions';
export default AddConditions;
