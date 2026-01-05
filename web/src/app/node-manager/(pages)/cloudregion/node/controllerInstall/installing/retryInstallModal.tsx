'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Form, Input, message, Select, Button } from 'antd';
const { Option } = Select;
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
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

const RetryInstallModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { retryInstallController } = useControllerApi();
    const formRef = useRef<FormInstance>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [nodeInfo, setNodeInfo] = useState<TableDataItem>({});
    const [authType, setAuthType] = useState<string>('password');
    const [uploadedFileName, setUploadedFileName] = useState<
      string | undefined
    >();
    const [privateKey, setPrivateKey] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: (config) => {
        setVisible(true);
        setNodeInfo(config);
        setAuthType('password');
        setUploadedFileName(undefined);
        setPrivateKey('');
      },
    }));

    const handleCancel = () => {
      setVisible(false);
      setConfirmLoading(false);
      formRef.current?.resetFields();
      setNodeInfo({});
      setAuthType('password');
      setUploadedFileName(undefined);
      setPrivateKey('');
    };

    const handleConfirm = () => {
      formRef.current?.validateFields().then(async (values) => {
        if (authType === 'private_key' && !privateKey) {
          return;
        }
        try {
          setConfirmLoading(true);
          const params: RetryInstallParams = {
            task_id: nodeInfo.task_id,
            task_node_ids: [nodeInfo.task_node_id],
            port: values.port,
            username: values.username,
            password: privateKey ? '' : values.password,
            private_key: privateKey || '',
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
          initialValues={{ ...nodeInfo, auth_type: 'password' }}
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
            name="auth_type"
            label={t('node-manager.cloudregion.node.authType')}
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Select
              value={authType}
              onChange={(value) => {
                setAuthType(value);
                // 切换验证方式时清空相关字段
                if (value === 'private_key') {
                  formRef.current?.setFieldValue('password', undefined);
                } else {
                  setUploadedFileName(undefined);
                  setPrivateKey('');
                }
              }}
            >
              <Option value="password">
                {t('node-manager.cloudregion.node.password')}
              </Option>
              <Option value="private_key">
                {t('node-manager.cloudregion.node.privateKey')}
              </Option>
            </Select>
          </Form.Item>
          {authType === 'password' ? (
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
          ) : (
            <Form.Item
              label={t('node-manager.cloudregion.node.loginPassword')}
              required
              validateStatus={!uploadedFileName && !privateKey ? 'error' : ''}
              help={
                !uploadedFileName && !privateKey ? t('common.required') : ''
              }
            >
              {uploadedFileName ? (
                <div className="inline-flex items-center gap-2 py-1 text-[var(--color-text-1)] max-w-full group">
                  <EllipsisWithTooltip
                    className="overflow-hidden text-ellipsis whitespace-nowrap"
                    text={uploadedFileName}
                  />
                  <span
                    className="cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                    style={{
                      fontSize: 16,
                      color: 'var(--color-primary)',
                      fontWeight: 'bold',
                    }}
                    onClick={() => {
                      setUploadedFileName(undefined);
                      setPrivateKey('');
                    }}
                    title={t('common.delete')}
                  >
                    ×
                  </span>
                </div>
              ) : (
                <Button
                  onClick={() => {
                    const input = document.createElement('input');
                    input.type = 'file';
                    input.accept = '.txt';
                    input.onchange = (e: any) => {
                      const file = e.target.files[0];
                      if (file) {
                        const reader = new FileReader();
                        reader.onload = (event) => {
                          const content = event.target?.result as string;
                          setPrivateKey(content);
                          setUploadedFileName(file.name);
                        };
                        reader.readAsText(file);
                      }
                    };
                    input.click();
                  }}
                >
                  {t('node-manager.cloudregion.node.uploadPrivateKey')}
                </Button>
              )}
            </Form.Item>
          )}
        </Form>
      </OperateModal>
    );
  }
);

RetryInstallModal.displayName = 'RetryInstallModal';
export default RetryInstallModal;
