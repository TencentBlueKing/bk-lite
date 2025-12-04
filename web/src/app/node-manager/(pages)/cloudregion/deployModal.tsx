import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from 'react';
import { Form, Button, Input, message, Tabs, Alert } from 'antd';
import { InfoCircleOutlined, RocketOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalSuccess,
  TableDataItem,
} from '@/app/node-manager/types';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from '@/components/permission';
import useNodeManagerApi from '@/app/node-manager/api';
import { DeployCloudRegionParams } from '@/app/node-manager/types/cloudregion';

const DeployModal = forwardRef<ModalRef, ModalSuccess>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const { deployCloudRegion } = useNodeManagerApi();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('container');
  const [cloudRegionData, setCloudRegionData] = useState<TableDataItem>({});

  useImperativeHandle(ref, () => ({
    showModal: (data: TableDataItem) => {
      setCloudRegionData(data);
      setOpen(true);
      setActiveTab('container');
    },
  }));

  useEffect(() => {
    if (open) {
      form.resetFields();
    }
  }, [open, form]);

  const handleFormOkClick = async () => {
    setConfirmLoading(true);
    try {
      await form.validateFields();
      const values = form.getFieldsValue();
      const data: DeployCloudRegionParams = {
        ip: values.ip,
        port: Number(values.port),
        username: values.username,
        password: values.password,
        cloud_region_id: cloudRegionData.id as number,
      };
      await deployCloudRegion(data);
      message.success(t('node-manager.cloudregion.deploy.deploySuccess'));
      onSuccess?.();
      setOpen(false);
      form.resetFields();
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleCancel = () => {
    setOpen(false);
    form.resetFields();
    setConfirmLoading(false);
  };

  const linkToBklite = () => {
    window.open('https://bklite.ai/');
  };

  const containerDeployContent = (
    <div className="py-2">
      <div className="mb-[15px] text-[var(--color-text-3)]">
        {t('node-manager.cloudregion.deploy.containerTips')}
      </div>
      <Form form={form} layout="vertical">
        <Form.Item
          name="ip"
          label={t('node-manager.cloudregion.deploy.ipAddress')}
          rules={[
            { required: true, message: t('common.inputRequired') },
            {
              pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
              message: t('node-manager.cloudregion.deploy.ipFormatError'),
            },
          ]}
        >
          <Input
            placeholder={t('node-manager.cloudregion.deploy.ipPlaceholder')}
          />
        </Form.Item>
        <Form.Item
          name="port"
          label={t('node-manager.cloudregion.deploy.sshPort')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
          initialValue={22}
        >
          <Input
            type="number"
            placeholder={`${t('common.inputMsg')}${t(
              'node-manager.cloudregion.deploy.sshPort'
            )}`}
          />
        </Form.Item>
        <Form.Item
          name="username"
          label={t('node-manager.cloudregion.deploy.loginAccount')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input
            placeholder={t(
              'node-manager.cloudregion.deploy.usernamePlaceholder'
            )}
          />
        </Form.Item>
        <Form.Item
          name="password"
          label={t('node-manager.cloudregion.deploy.loginPassword')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input.Password
            placeholder={`${t('common.inputMsg')}${t(
              'node-manager.cloudregion.deploy.loginPassword'
            )}`}
          />
        </Form.Item>
        <Alert
          message={t('node-manager.cloudregion.deploy.sshServiceTips')}
          type="info"
          showIcon
          icon={<InfoCircleOutlined />}
        />
      </Form>
    </div>
  );

  const k8sDeployContent = (
    <div className="min-h-[400px] flex items-center justify-center bg-[var(--color-fill-1)]  border-dashed border-[var(--color-primary)] border rounded-xl">
      <div className="text-center py-10 px-5">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-[20px] mb-6">
          <RocketOutlined className="text-[40px] text-white" />
        </div>
        <h3 className="text-lg font-semibold text-[var(--color-text-1)] mb-3">
          {t('node-manager.cloudregion.deploy.upgradeTitle')}
        </h3>
        <p className="text-sm text-[var(--color-text-3)] mb-8 leading-relaxed">
          {t('node-manager.cloudregion.deploy.upgradeDescription')}
        </p>
        <Button
          type="primary"
          size="large"
          className="min-w-[140px] h-10 text-[15px] rounded-lg"
          onClick={linkToBklite}
        >
          {t('node-manager.cloudregion.deploy.upgradeButton')}
        </Button>
      </div>
    </div>
  );

  const tabItems = [
    {
      key: 'container',
      label: t('node-manager.cloudregion.deploy.containerDeploy'),
      children: containerDeployContent,
    },
    {
      key: 'k8s',
      label: t('node-manager.cloudregion.deploy.k8sDeploy'),
      children: k8sDeployContent,
    },
  ];

  return (
    <OperateModal
      title={t('node-manager.cloudregion.deploy.title')}
      open={open}
      onCancel={handleCancel}
      width={600}
      footer={
        <div>
          {activeTab === 'container' ? (
            <>
              <PermissionWrapper
                className="mr-2"
                requiredPermissions={['Edit']}
              >
                <Button
                  type="primary"
                  loading={confirmLoading}
                  onClick={handleFormOkClick}
                >
                  {t('node-manager.cloudregion.deploy.deploy')}
                </Button>
              </PermissionWrapper>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </>
          ) : (
            <></>
          )}
        </div>
      }
    >
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </OperateModal>
  );
});

DeployModal.displayName = 'DeployModal';
export default DeployModal;
