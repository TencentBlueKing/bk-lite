'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Form, Input, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalSuccess,
  TableDataItem,
} from '@/app/node-manager/types';
import { RetryInstallParams } from '@/app/node-manager/types/controller';
import useControllerApi from '@/app/node-manager/api/useControllerApi';

const RetryInstallModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { retryInstallController } = useControllerApi();
    const formRef = useRef<FormInstance>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [nodeInfo, setNodeInfo] = useState<TableDataItem>({});

    useImperativeHandle(ref, () => ({
      showModal: (config) => {
        setVisible(true);
        setNodeInfo(config);
      },
    }));

    const handleCancel = () => {
      setVisible(false);
      setConfirmLoading(false);
      formRef.current?.resetFields();
      setNodeInfo({});
    };

    const handleConfirm = () => {
      formRef.current?.validateFields().then(async (values) => {
        try {
          setConfirmLoading(true);
          const params: RetryInstallParams = {
            task_id: nodeInfo.task_id,
            task_node_ids: [nodeInfo.task_node_id],
            port: values.port,
            username: values.username,
            password: values.password,
          };
          await retryInstallController(params);
          message.success(t('node-manager.cloudregion.node.retrySuccess'));
          handleCancel();
          onSuccess?.();
        } finally {
          setConfirmLoading(false);
        }
      });
    };

    return (
      <OperateModal
        title={
          <div className="px-[10px] py-[20px]">
            <div className="mb-[10px]">
              {t('node-manager.cloudregion.node.retryInstall')}
            </div>
            <div className="text-[12px] font-[400] text-[var(--color-text-3)]">
              {t('node-manager.cloudregion.node.retryInstallInfo')}
            </div>
          </div>
        }
        open={visible}
        destroyOnClose
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={confirmLoading}
        onCancel={handleCancel}
        onOk={handleConfirm}
      >
        <div className="mb-[16px] p-[12px] bg-[var(--color-fill-1)] rounded-[4px]">
          <div className="text-[14px]">
            <div className="flex items-center mb-[10px]">
              <span className="text-[var(--color-text-3)] w-[120px]">
                {t('node-manager.cloudregion.node.ipAdrress')}：
              </span>
              {nodeInfo.ip || '--'}
            </div>
            <div className="flex items-center">
              <span className="text-[var(--color-text-3)] w-[120px]">
                {t('node-manager.cloudregion.node.nodeName')}：
              </span>
              {nodeInfo.node_name || '--'}
            </div>
          </div>
        </div>
        <Form
          ref={formRef}
          layout="vertical"
          initialValues={nodeInfo}
          colon={false}
        >
          <Form.Item
            name="port"
            label={t('node-manager.cloudregion.node.loginPort')}
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Input placeholder={t('common.inputTip')} />
          </Form.Item>
          <Form.Item
            name="username"
            label={t('node-manager.cloudregion.node.loginAccount')}
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Input placeholder={t('common.inputTip')} />
          </Form.Item>
          <Form.Item
            name="password"
            label={t('node-manager.cloudregion.node.loginPassword')}
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Input.Password placeholder={t('common.inputTip')} />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

RetryInstallModal.displayName = 'RetryInstallModal';
export default RetryInstallModal;
