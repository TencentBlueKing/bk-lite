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
import useNodeManagerApi from '@/app/node-manager/api';
import { ModalRef, ModalSuccess } from '@/app/node-manager/types';
import { NodeParams } from '@/app/node-manager/types/node';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';

const EditNode = forwardRef<ModalRef, ModalSuccess>(({ onSuccess }, ref) => {
  const { updateNode } = useNodeManagerApi();
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const [visible, setVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [nodeForm, setNodeForm] = useState<NodeParams>({});

  useImperativeHandle(ref, () => ({
    showModal: ({ form }) => {
      setNodeForm(form || {});
      setVisible(true);
    },
  }));

  useEffect(() => {
    if (visible) {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        name: nodeForm.name,
        organizations: nodeForm.organization || [],
      });
    }
  }, [visible, nodeForm]);

  const handleSubmit = () => {
    formRef.current?.validateFields().then(async (values) => {
      try {
        setConfirmLoading(true);
        await updateNode({
          id: nodeForm.id,
          name: values.name,
          organizations: values.organizations,
        });
        message.success(t('common.successfullyModified'));
        handleCancel();
        onSuccess();
      } finally {
        setConfirmLoading(false);
      }
    });
  };

  const handleCancel = () => {
    setVisible(false);
  };

  return (
    <OperateModal
      width={600}
      title={t('common.edit')}
      open={visible}
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
      <Form ref={formRef} name="editNode" layout="vertical">
        <Form.Item
          label={t('node-manager.cloudregion.node.nodeName')}
          name="name"
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Input placeholder={t('common.inputTip')} />
        </Form.Item>
        <Form.Item
          label={t('node-manager.cloudregion.node.group')}
          name="organizations"
          rules={[{ required: true, message: t('common.required') }]}
        >
          <GroupTreeSelector />
        </Form.Item>
      </Form>
    </OperateModal>
  );
});

EditNode.displayName = 'EditNode';
export default EditNode;
