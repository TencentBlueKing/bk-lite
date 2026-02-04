"use client";
import OperateModal from '@/components/operate-modal';
import { Form, Input, Button, FormInstance, message } from 'antd';
import { useState, useImperativeHandle, useEffect, useRef, forwardRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { DatasetType, ModalRef } from '@/app/mlops/types';
import useMlopsManageApi from '@/app/mlops/api/manage';

interface DatasetModalProps {
  user?: any;
  options?: any,
  onSuccess: () => void;
  activeTag: string[];
  [key: string]: any
}

const DatasetModal = forwardRef<ModalRef, DatasetModalProps>(({ onSuccess, activeTag }, ref) => {
  const { t } = useTranslation();
  const {
    addDataset,
    updateDataset,
  } = useMlopsManageApi();
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [type, setType] = useState<string>('edit');
  const [title, setTitle] = useState<string>('editform');
  const [formData, setFormData] = useState<any>({
    name: '',
    description: '',
  });
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const formRef = useRef<FormInstance>(null);

  useImperativeHandle(ref, () => ({
    showModal: ({ type, title, form }) => {
      setIsModalOpen(true);
      setType(type);
      setTitle(title as string);
      setFormData(form);
    }
  }));

  useEffect(() => {
    if (isModalOpen && formRef.current) {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        ...formData,
      })
    }
  }, [formData, isModalOpen]);

  const handleSubmit = async () => {
    setConfirmLoading(true);
    try {
      const [tagName] = activeTag;
      const { name, description } = await formRef.current?.validateFields();
      if (type === 'add') {
        await addDataset(tagName as DatasetType, { name, description });
      } else if (type === 'edit') {
        await updateDataset(formData.id, tagName as DatasetType, {
          name,
          description
        });
      }
      message.success(t(`datasets.${type}Success`));
      setIsModalOpen(false);
      onSuccess();
    } catch (e) {
      console.error(e)
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleCancel = () => {
    setIsModalOpen(false);
  };

  return (
    <>
      <OperateModal
        title={t(`datasets.${title}`)}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        footer={[
          <Button key="submit" loading={confirmLoading} type="primary" onClick={handleSubmit}>
            {t('common.confirm')}
          </Button>,
          <Button key="cancel" onClick={handleCancel}>
            {t('common.cancel')}
          </Button>,
        ]}
      >
        <Form ref={formRef} layout="vertical">
          <Form.Item
            name='name'
            label={t('common.name')}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Input placeholder={t('common.inputMsg')} />
          </Form.Item>
          <Form.Item
            name='description'
            label={t(`datasets.description`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Input.TextArea placeholder={t('common.inputMsg')} />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  )
});

DatasetModal.displayName = 'DatasetModal';
export default DatasetModal;
