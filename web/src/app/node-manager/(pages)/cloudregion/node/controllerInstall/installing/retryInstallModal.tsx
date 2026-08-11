'use client';
import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle
} from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Select,
  Switch
} from 'antd';
const { Option } = Select;
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalSuccess
} from '@/app/node-manager/types';
import useControllerApi from '@/app/node-manager/api/useControllerApi';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import {
  buildRetryInstallParams,
  getRetryInstallInitialValues,
  validateWindowsRetryPort
} from './retryInstallForm';
import type {
  RetryInstallFormValues,
  RetryInstallNode
} from './retryInstallForm';

const RetryInstallModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { retryInstallController } = useControllerApi();
    const [form] = Form.useForm<RetryInstallFormValues>();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [nodeInfo, setNodeInfo] = useState<RetryInstallNode>({});
    const [authType, setAuthType] = useState<'password' | 'private_key'>('password');
    const watchedWinrmCertValidation = Form.useWatch(
      'winrm_cert_validation',
      form
    );
    const winrmCertValidation = watchedWinrmCertValidation !== false;
    const [uploadedFileName, setUploadedFileName] = useState<
      string | undefined
    >();
    const [privateKey, setPrivateKey] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: (config) => {
        const retryNode = config as RetryInstallNode;
        setVisible(true);
        setNodeInfo(retryNode);
        setAuthType('password');
        setUploadedFileName(undefined);
        setPrivateKey('');
      },
    }));

    useEffect(() => {
      if (!visible) {
        return;
      }
      const initialValues = getRetryInstallInitialValues(nodeInfo);
      form.setFieldsValue(initialValues);
      setAuthType(initialValues.auth_type);
    }, [form, nodeInfo, visible]);

    const handleCancel = () => {
      setVisible(false);
      setConfirmLoading(false);
      form.resetFields();
      setNodeInfo({});
      setAuthType('password');
      setUploadedFileName(undefined);
      setPrivateKey('');
    };

    const handleConfirm = async () => {
      let values: RetryInstallFormValues;
      try {
        values = await form.validateFields();
      } catch {
        return;
      }
      if (authType === 'private_key' && !privateKey) {
        return;
      }
      try {
        setConfirmLoading(true);
        await retryInstallController(
          buildRetryInstallParams(nodeInfo, values, privateKey)
        );
        message.success(t('node-manager.cloudregion.node.retrySuccess'));
        handleCancel();
        onSuccess?.();
      } finally {
        setConfirmLoading(false);
      }
    };

    const isWindows = nodeInfo.os === 'windows';

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
        destroyOnHidden
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
          form={form}
          layout="vertical"
          colon={false}
        >
          {isWindows && (
            <Alert
              className="mb-[16px]"
              type="info"
              showIcon
              message={t('node-manager.cloudregion.node.winrmRetryProfileTitle')}
              description={t('node-manager.cloudregion.node.winrmRetryProfileDesc')}
            />
          )}
          <Form.Item
            name="port"
            label={t('node-manager.cloudregion.node.loginPort')}
            extra={
              isWindows
                ? t('node-manager.cloudregion.node.winrmHttpsPortHelp')
                : undefined
            }
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
              ...(isWindows
                ? [
                  {
                    validator: (_: unknown, value?: number) =>
                      validateWindowsRetryPort(value)
                        ? Promise.resolve()
                        : Promise.reject(
                          new Error(
                            t('node-manager.cloudregion.node.winrmHttpPortError')
                          )
                        )
                  }
                ]
                : [])
            ]}
          >
            <InputNumber
              min={1}
              max={65535}
              precision={0}
              className="w-full"
              placeholder={t('common.inputTip')}
            />
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
          {isWindows ? (
            <>
              <div className="grid grid-cols-1 gap-x-[16px] md:grid-cols-2">
                <Form.Item
                  name="winrm_scheme"
                  label={t('node-manager.cloudregion.node.winrmScheme')}
                >
                  <Input readOnly />
                </Form.Item>
                <Form.Item
                  name="winrm_transport"
                  label={t('node-manager.cloudregion.node.winrmTransport')}
                >
                  <Input readOnly />
                </Form.Item>
              </div>
              <Form.Item
                name="winrm_cert_validation"
                label={t('node-manager.cloudregion.node.winrmCertValidation')}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              {!winrmCertValidation && (
                <Alert
                  className="mb-[16px]"
                  type="warning"
                  showIcon
                  message={t(
                    'node-manager.cloudregion.node.winrmCertValidationWarningTitle'
                  )}
                  description={t(
                    'node-manager.cloudregion.node.winrmCertValidationWarningDesc'
                  )}
                />
              )}
              <Form.Item name="auth_type" hidden>
                <Input />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="auth_type"
              label={t('node-manager.cloudregion.node.authType')}
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Select
                value={authType}
                onChange={(value: 'password' | 'private_key') => {
                  setAuthType(value);
                  if (value === 'private_key') {
                    form.setFieldValue('password', undefined);
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
          )}
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
          ) : !isWindows ? (
            <Form.Item
              label={t('node-manager.cloudregion.node.privateKey')}
              required
              validateStatus={!uploadedFileName && !privateKey ? 'error' : ''}
              help={
                !uploadedFileName && !privateKey ? t('common.required') : ''
              }
            >
              {uploadedFileName ? (
                <div className="inline-flex items-center gap-2 text-[var(--color-text-1)] max-w-full group">
                  <EllipsisWithTooltip
                    className="overflow-hidden text-ellipsis whitespace-nowrap"
                    text={uploadedFileName}
                  />
                  <Button
                    type="text"
                    size="small"
                    danger
                    aria-label={t('common.delete')}
                    className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                    onClick={() => {
                      setUploadedFileName(undefined);
                      setPrivateKey('');
                    }}
                  >
                    ×
                  </Button>
                </div>
              ) : (
                <Button
                  onClick={() => fileInputRef.current?.click()}
                >
                  {t('node-manager.cloudregion.node.uploadPrivateKey')}
                </Button>
              )}
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = (loadEvent) => {
                    const content = loadEvent.target?.result;
                    if (typeof content === 'string') {
                      setPrivateKey(content);
                      setUploadedFileName(file.name);
                    }
                  };
                  reader.readAsText(file);
                }}
              />
            </Form.Item>
          ) : null}
        </Form>
      </OperateModal>
    );
  }
);

RetryInstallModal.displayName = 'RetryInstallModal';
export default RetryInstallModal;
