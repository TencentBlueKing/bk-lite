'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect
} from 'react';
import { Input, Button, Form, message } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { ModalRef } from '@/app/monitor/types';
import { ObjectTypeFormData } from './types';
import { useTranslation } from '@/utils/i18n';
import useObjectApi from './api';

interface ModalProps {
  onSuccess: (type: 'add' | 'edit', data: ObjectTypeFormData) => void;
}

const ObjectTypeModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { createObjectType, updateObjectType } = useObjectApi();
    const formRef = useRef<FormInstance>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [formData, setFormData] = useState<ObjectTypeFormData>(
      {} as ObjectTypeFormData
    );
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form, title }) => {
        setVisible(true);
        setType(type);
        setTitle(title);
        setFormData(form as ObjectTypeFormData);
      }
    }));

    useEffect(() => {
      if (visible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(formData);
      }
    }, [visible, formData]);

    const handleSubmit = () => {
      formRef.current?.validateFields().then(async (values) => {
        try {
          setConfirmLoading(true);
          if (type === 'add') {
            // 创建时前端生成 UUID 作为 id
            const newId = uuidv4();
            const submitData = { id: newId, name: values.name };
            await createObjectType(submitData);
            message.success(t('common.addSuccess'));
            handleCancel();
            onSuccess('add', submitData);
          } else {
            await updateObjectType(formData.id!, values);
            message.success(t('common.updateSuccess'));
            handleCancel();
            onSuccess('edit', { ...formData, ...values });
          }
        } catch {
          message.error(t('common.operationFailed'));
        } finally {
          setConfirmLoading(false);
        }
      });
    };

    const handleCancel = () => {
      setVisible(false);
      formRef.current?.resetFields();
    };

    return (
      <OperateModal
        width={500}
        title={title}
        visible={visible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-2"
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
        <Form
          ref={formRef}
          name="objectTypeForm"
          labelCol={{ span: 5 }}
          wrapperCol={{ span: 18 }}
        >
          <Form.Item<ObjectTypeFormData>
            label={t('monitor.object.typeName')}
            name="name"
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={t('monitor.object.typeNamePlaceholder')} />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

ObjectTypeModal.displayName = 'ObjectTypeModal';
export default ObjectTypeModal;
