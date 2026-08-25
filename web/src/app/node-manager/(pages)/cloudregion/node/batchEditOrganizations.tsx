'use client';

import React, {
  forwardRef,
  useImperativeHandle,
  useRef,
  useState
} from 'react';
import { Alert, Button, Form, message } from 'antd';
import type { FormInstance } from 'antd';

import GroupTreeSelector from '@/components/group-tree-select';
import OperateModal from '@/components/operate-modal';
import useNodeManagerApi from '@/app/node-manager/api';
import type { ModalRef, ModalSuccess } from '@/app/node-manager/types';
import { useTranslation } from '@/utils/i18n';

interface BatchEditOrganizationsForm {
  organizations: number[];
}

const BatchEditOrganizations = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { batchUpdateNodeOrganizations } = useNodeManagerApi();
    const { t } = useTranslation();
    const formRef = useRef<FormInstance<BatchEditOrganizationsForm>>(null);
    const [visible, setVisible] = useState(false);
    const [confirmLoading, setConfirmLoading] = useState(false);
    const [nodeIds, setNodeIds] = useState<string[]>([]);

    useImperativeHandle(ref, () => ({
      showModal: ({ ids = [] }) => {
        setNodeIds(ids);
        formRef.current?.resetFields();
        setVisible(true);
      }
    }));

    const handleCancel = () => {
      setVisible(false);
      formRef.current?.resetFields();
    };

    const handleSubmit = async () => {
      const values = await formRef.current?.validateFields();
      if (!values) return;

      try {
        setConfirmLoading(true);
        await batchUpdateNodeOrganizations({
          node_ids: nodeIds,
          organizations: values.organizations
        });
        message.success(t('common.successfullyModified'));
        handleCancel();
        onSuccess();
      } finally {
        setConfirmLoading(false);
      }
    };

    return (
      <OperateModal
        width={600}
        title={t(
          'node-manager.cloudregion.node.batchEditOrganizations',
          '批量修改组织'
        )}
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
        <Alert
          className="mb-4"
          type="info"
          showIcon
          message={t(
            'node-manager.cloudregion.node.batchEditOrganizationsHint',
            '将为已选择的 {count} 个节点统一替换所属组织。',
            { count: nodeIds.length }
          )}
        />
        <Form ref={formRef} name="batchEditNodeOrganizations" layout="vertical">
          <Form.Item
            label={t('node-manager.cloudregion.node.organization')}
            name="organizations"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <GroupTreeSelector
              showSearch
              placeholder={t('common.pleaseSelect')}
            />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

BatchEditOrganizations.displayName = 'BatchEditOrganizations';

export default BatchEditOrganizations;
