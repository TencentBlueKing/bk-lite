'use client';

import React, { forwardRef, useImperativeHandle, useState } from 'react';
import { Button, Form, Input, message } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelector from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';

interface ModalConfig {
  selectedOrganization?: number;
  objectId: number;
}

export interface CreateAssetModalRef {
  showModal: (config: ModalConfig) => void;
}

interface CreateAssetModalProps {
  onConfirm: (createdInstanceId?: string) => void;
}

const CreateAssetModal = forwardRef<CreateAssetModalRef, CreateAssetModalProps>(
  ({ onConfirm }, ref) => {
    const { t } = useTranslation();
    const [form] = Form.useForm();
    const { createK8sInstance } = useIntegrationApi();

    const [visible, setVisible] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [objectId, setObjectId] = useState(0);

    useImperativeHandle(ref, () => ({
      showModal: (config: ModalConfig) => {
        setObjectId(config.objectId);
        form.setFieldsValue({
          name: '',
          organizations: config.selectedOrganization
            ? [config.selectedOrganization]
            : []
        });
        setVisible(true);
      }
    }));

    const handleConfirm = async () => {
      try {
        const values = await form.validateFields();
        setSubmitting(true);

        const result = await createK8sInstance({
          organizations: values.organizations,
          id: uuidv4().replace(/-/g, ''),
          name: values.name,
          monitor_object_id: objectId
        });

        message.success(
          t('monitor.integrations.customApi.assetCreatedSuccess')
        );
        setVisible(false);
        form.resetFields();
        onConfirm(result?.instance_id);
      } catch {
        // Form validation failed or API error - handled by form/API
      } finally {
        setSubmitting(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
      form.resetFields();
    };

    return (
      <OperateModal
        open={visible}
        title={t('monitor.integrations.customApi.createAsset')}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={submitting}
              onClick={handleConfirm}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label={t('monitor.integrations.customApi.instanceName')}
            name="name"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Input
              placeholder={t(
                'monitor.integrations.customApi.enterInstanceName'
              )}
            />
          </Form.Item>
          <Form.Item
            label={t('monitor.integrations.customApi.belongOrganization')}
            name="organizations"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <GroupTreeSelector />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

CreateAssetModal.displayName = 'CreateAssetModal';
export default CreateAssetModal;
