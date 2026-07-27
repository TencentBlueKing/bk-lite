'use client';

import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  message,
  Modal,
  Segmented,
  Space,
  Spin,
  Steps,
  Tag,
  theme,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleFilled,
  ExportOutlined,
  InfoCircleOutlined,
  RocketOutlined,
  StarOutlined,
  SyncOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import CodeEditor from '@/app/node-manager/components/codeEditor';
import MainLayout from '../mainlayout/layout';
import useNodeManagerApi from '@/app/node-manager/api';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import type {
  CloudRegionDetail,
  ServiceItem,
} from '@/app/node-manager/types/cloudregion';
import useCommandCopyDialog from '@/app/node-manager/hooks/useCommandCopyDialog';
import PermissionWrapper from '@/components/permission';

const isValidProxyAddress = (value: string) => {
  const candidate = value.trim();
  const ipPattern =
    /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
  const domainPattern =
    /^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$/;
  if (ipPattern.test(candidate) || domainPattern.test(candidate)) return true;

  const ipv6Candidate =
    candidate.startsWith('[') && candidate.endsWith(']')
      ? candidate.slice(1, -1)
      : candidate;
  if (!ipv6Candidate.includes(':')) return false;
  try {
    return new URL(`http://[${ipv6Candidate}]`).hostname.length > 0;
  } catch {
    return false;
  }
};

type DeploymentView = 'container' | 'k8s';

const EnvironmentPage = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [messageApi, messageContextHolder] = message.useMessage();
  const [modal, modalContextHolder] = Modal.useModal();
  const { isLoading } = useApiClient();
  const cloudId = useCloudId();
  const {
    getCloudRegionDetail,
    getDeployCommand,
    updatePartCloudIntro,
    stageCloudRegionProxyAddress,
    activateCloudRegionProxyAddress,
    cancelCloudRegionProxyAddress,
  } = useNodeManagerApi();
  const { copyCommand, commandCopyDialog, copying } = useCommandCopyDialog();
  const [deployForm] = Form.useForm();
  const [changeForm] = Form.useForm();
  const [detail, setDetail] = useState<CloudRegionDetail | null>(null);
  const [script, setScript] = useState('');
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [changeModalOpen, setChangeModalOpen] = useState(false);
  const [changing, setChanging] = useState(false);
  const [activating, setActivating] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [deploymentView, setDeploymentView] =
    useState<DeploymentView>('container');

  const fetchCloudRegion = async (showSuccess = false) => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const data = (await getCloudRegionDetail(cloudId)) as CloudRegionDetail;
      setDetail(data);
      if (data.deployment_state === 'not_deployed') {
        deployForm.setFieldValue('proxyIp', data.proxy_address || '');
      }
      if (showSuccess) messageApi.success(t('common.refSuccess'));
      return data;
    } catch {
      setLoadFailed(true);
      messageApi.error(
        t('node-manager.cloudregion.environment.loadFailed')
      );
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isLoading) void fetchCloudRegion();
    // API hooks are recreated by the request context; cloudId/isLoading are the route inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cloudId, isLoading]);

  const generateScript = async (options?: { firstDeploy?: boolean }) => {
    if (!detail || detail.is_default) return;
    setGenerating(true);
    setScript('');
    try {
      if (options?.firstDeploy) {
        const { proxyIp } = await deployForm.validateFields(['proxyIp']);
        if (proxyIp !== detail.proxy_address) {
          await updatePartCloudIntro(String(cloudId), {
            proxy_address: proxyIp,
          });
          await fetchCloudRegion();
        }
      }
      const generatedScript = await getDeployCommand({
        cloud_region_id: cloudId,
      });
      setScript(generatedScript || '');
      messageApi.success(t('node-manager.cloudregion.environment.generateSuccess'));
    } catch (error: unknown) {
      const validationError = error as { errorFields?: unknown[] };
      if (!validationError?.errorFields) {
        messageApi.error(
          t('node-manager.cloudregion.environment.operationFailed')
        );
      }
    } finally {
      setGenerating(false);
    }
  };

  const stageProxyAddress = async () => {
    const { proxyIp } = await changeForm.validateFields(['proxyIp']);
    setChanging(true);
    try {
      await stageCloudRegionProxyAddress(cloudId, proxyIp);
      changeForm.resetFields();
      setChangeModalOpen(false);
      await fetchCloudRegion();
      messageApi.success(t('node-manager.cloudregion.environment.changeStaged'));
      await generateScript();
    } catch (error) {
      messageApi.error(
        t('node-manager.cloudregion.environment.operationFailed')
      );
      throw error;
    } finally {
      setChanging(false);
    }
  };

  const confirmActivation = () => {
    modal.confirm({
      title: t('node-manager.cloudregion.environment.activateTitle'),
      icon: <ExclamationCircleFilled style={{ color: token.colorWarning }} />,
      content: t('node-manager.cloudregion.environment.activateDescription'),
      okText: t('node-manager.cloudregion.environment.activateConfirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActivating(true);
        try {
          await activateCloudRegionProxyAddress(cloudId);
          setScript('');
          await fetchCloudRegion();
          messageApi.success(t('node-manager.cloudregion.environment.activateSuccess'));
        } catch (error) {
          messageApi.error(
            t('node-manager.cloudregion.environment.operationFailed')
          );
          throw error;
        } finally {
          setActivating(false);
        }
      },
    });
  };

  const cancelPendingChange = () => {
    modal.confirm({
      title: t('node-manager.cloudregion.environment.cancelChangeTitle'),
      content: t('node-manager.cloudregion.environment.cancelChangeDescription'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await cancelCloudRegionProxyAddress(cloudId);
          setScript('');
          await fetchCloudRegion();
          messageApi.success(t('node-manager.cloudregion.environment.cancelChangeSuccess'));
        } catch (error) {
          messageApi.error(
            t('node-manager.cloudregion.environment.operationFailed')
          );
          throw error;
        }
      },
    });
  };

  const serviceStatus = (service: ServiceItem) => {
    if (service.deployment_status === 'not_deployed') {
      return {
        label: t('node-manager.cloudregion.environment.notDeployed'),
        color: 'default' as const,
        icon: <InfoCircleOutlined />,
        accent: 'var(--color-border-3)',
        surface: 'var(--color-fill-1)',
        titleColor: 'var(--color-text-2)',
      };
    }
    if (service.health_status === 'normal') {
      return {
        label: t('node-manager.cloudregion.environment.normal'),
        color: 'success' as const,
        icon: <CheckCircleOutlined />,
        accent: 'var(--color-success)',
        surface:
          'color-mix(in srgb, var(--color-success) 5%, var(--color-bg))',
        titleColor: 'var(--color-success)',
      };
    }
    return {
      label: t('node-manager.cloudregion.environment.abnormal'),
      color: 'error' as const,
      icon: <CloseCircleOutlined />,
      accent: 'var(--color-fail)',
      surface:
        'color-mix(in srgb, var(--color-fail) 5%, var(--color-bg))',
      titleColor: 'var(--color-fail)',
    };
  };

  const renderScript = () =>
    script ? (
      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between">
          <Typography.Text strong>
            {t('node-manager.cloudregion.environment.deployScript')}
          </Typography.Text>
          <Button
            type="link"
            size="small"
            loading={copying}
            onClick={() => void copyCommand(script)}
          >
            {t('node-manager.cloudregion.environment.copyScript')}
          </Button>
        </div>
        <CodeEditor
          value={script}
          width="100%"
          height="250px"
          mode="shell"
          theme="monokai"
          name="cloud-region-deploy-script"
          readOnly
        />
        <Alert
          className="mt-3"
          type="info"
          showIcon
          message={t('node-manager.cloudregion.environment.executeScriptTip')}
        />
      </div>
    ) : null;

  const renderDefaultMaintenance = () => (
    <Card
      title={t('node-manager.cloudregion.environment.maintenanceMethod')}
      className="border-[var(--color-border)]"
      style={{ background: 'var(--color-fill-1)' }}
      styles={{ body: { padding: 20 } }}
    >
      <Alert
        type={detail?.health_state === 'abnormal' ? 'warning' : 'info'}
        showIcon
        message={t('node-manager.cloudregion.environment.defaultManagedTitle')}
        description={
          detail?.health_state === 'abnormal'
            ? t('node-manager.cloudregion.environment.defaultManagedAbnormal')
            : t('node-manager.cloudregion.environment.defaultManagedDescription')
        }
      />
      {detail?.health_state === 'abnormal' && (
        <div className="mt-4 rounded-[8px] border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
          <Typography.Text strong>
            {t('node-manager.cloudregion.environment.troubleshootingTitle')}
          </Typography.Text>
          <Typography.Paragraph className="!mb-0 !mt-2 text-[var(--color-text-2)]">
            {t('node-manager.cloudregion.environment.troubleshootingDescription')}
          </Typography.Paragraph>
        </div>
      )}
    </Card>
  );

  const renderK8sDeployment = () => (
    <Card
      title={t('node-manager.cloudregion.environment.k8sDeploy')}
      className="border-[var(--color-border)]"
      style={{ background: 'var(--color-fill-1)' }}
      styles={{ body: { padding: 20 } }}
    >
      <Alert
        type="info"
        showIcon
        message={t('node-manager.cloudregion.deploy.upgradeTitle')}
        description={t('node-manager.cloudregion.deploy.upgradeDescription')}
        action={
          <Button
            type="primary"
            icon={<ExportOutlined />}
            href="https://bklite.ai/"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('node-manager.cloudregion.deploy.upgradeButton')}
          </Button>
        }
      />
    </Card>
  );

  const renderFirstDeployment = () => (
    <Card
      title={t('node-manager.cloudregion.environment.firstDeployTitle')}
      className="border-[var(--color-border)]"
      style={{ background: 'var(--color-fill-1)' }}
      styles={{ body: { padding: 20 } }}
    >
      <Steps
        className="mb-6"
        current={script ? 1 : 0}
        items={[
          { title: t('node-manager.cloudregion.environment.stepAddress') },
          { title: t('node-manager.cloudregion.environment.stepScript') },
          { title: t('node-manager.cloudregion.environment.stepVerify') },
        ]}
      />
      <Form form={deployForm} layout="vertical">
        <Form.Item
          name="proxyIp"
          label={t('node-manager.cloudregion.environment.proxyIpOrDomain')}
          extra={t('node-manager.cloudregion.environment.proxyTips')}
          rules={[
            { required: true, message: t('common.inputRequired') },
            {
              validator: (_, value) =>
                !value || isValidProxyAddress(value)
                  ? Promise.resolve()
                  : Promise.reject(
                    new Error(t('node-manager.cloudregion.deploy.ipFormatError'))
                  ),
            },
          ]}
        >
          <Input
            className="h-10"
            placeholder={t('node-manager.cloudregion.environment.proxyIpPlaceholder')}
          />
        </Form.Item>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button
            type="primary"
            icon={<RocketOutlined />}
            loading={generating}
            onClick={() => void generateScript({ firstDeploy: true })}
          >
            {t('node-manager.cloudregion.environment.generateScript')}
          </Button>
        </PermissionWrapper>
      </Form>
      {renderScript()}
    </Card>
  );

  const renderManagedDeployment = () => {
    const pendingAddress = detail?.pending_proxy_address;
    return (
      <Card
        title={t('node-manager.cloudregion.environment.deploySummary')}
        className="border-[var(--color-border)]"
        style={{ background: 'var(--color-fill-1)' }}
        styles={{ body: { padding: 20 } }}
        extra={
          !pendingAddress && (
            <Space size={8}>
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  onClick={() => setChangeModalOpen(true)}
                >
                  {t('node-manager.cloudregion.environment.changeProxy')}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  icon={<ToolOutlined />}
                  loading={generating}
                  onClick={() => void generateScript()}
                >
                  {t('node-manager.cloudregion.environment.redeploy')}
                </Button>
              </PermissionWrapper>
            </Space>
          )
        }
      >
        <Descriptions column={1} size="small">
          <Descriptions.Item label={t('node-manager.cloudregion.environment.currentProxy')}>
            {detail?.proxy_address || '-'}
          </Descriptions.Item>
          <Descriptions.Item label={t('node-manager.cloudregion.environment.deployMethod')}>
            {t('node-manager.cloudregion.environment.containerDeploy')}
          </Descriptions.Item>
          <Descriptions.Item label={t('node-manager.cloudregion.environment.deployState')}>
            {detail?.deployment_state === 'partially_deployed'
              ? t('node-manager.cloudregion.environment.partiallyDeployed')
              : t('node-manager.cloudregion.environment.deployed')}
          </Descriptions.Item>
          <Descriptions.Item label={t('node-manager.cloudregion.environment.healthState')}>
            <Tag color={detail?.health_state === 'normal' ? 'success' : 'error'}>
              {detail?.health_state === 'normal'
                ? t('node-manager.cloudregion.environment.normal')
                : t('node-manager.cloudregion.environment.abnormal')}
            </Tag>
          </Descriptions.Item>
        </Descriptions>

        {detail?.health_state === 'abnormal' && !pendingAddress && (
          <Alert
            className="mt-4"
            type="warning"
            showIcon
            message={t('node-manager.cloudregion.environment.deployedAbnormalTitle')}
            description={t('node-manager.cloudregion.environment.deployedAbnormalDescription')}
          />
        )}

        {pendingAddress && (
          <Alert
            className="mt-4"
            type="warning"
            showIcon
            message={t('node-manager.cloudregion.environment.pendingChangeTitle')}
            description={t(
              'node-manager.cloudregion.environment.pendingChangeDescription',
              undefined,
              {
                current: detail?.proxy_address || '-',
                pending: pendingAddress,
              }
            )}
            action={
              <Space wrap size={8}>
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Button loading={generating} onClick={() => void generateScript()}>
                    {t('node-manager.cloudregion.environment.generatePendingScript')}
                  </Button>
                </PermissionWrapper>
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Space size={8}>
                    <Button
                      type="primary"
                      loading={activating}
                      onClick={confirmActivation}
                    >
                      {t('node-manager.cloudregion.environment.activatePending')}
                    </Button>
                    <Button onClick={cancelPendingChange}>
                      {t('node-manager.cloudregion.environment.cancelChange')}
                    </Button>
                  </Space>
                </PermissionWrapper>
              </Space>
            }
          />
        )}
        {renderScript()}
      </Card>
    );
  };

  return (
    <MainLayout>
      {messageContextHolder}
      {modalContextHolder}
      <div className="h-full w-full min-w-0">
        <section className="mb-6" aria-labelledby="environment-status-title">
          <div className="mb-4 flex items-center justify-between">
            <h3 id="environment-status-title" className="m-0 text-base font-semibold">
              {t('node-manager.cloudregion.environment.envStatus')}
            </h3>
            <Button
              icon={<SyncOutlined />}
              aria-label={t('node-manager.cloudregion.environment.refreshStatus')}
              loading={loading}
              onClick={() => void fetchCloudRegion(true)}
            >
              {t('node-manager.cloudregion.environment.refreshStatus')}
            </Button>
          </div>
          {loadFailed && (
            <Alert
              className="mb-4"
              type="error"
              showIcon
              message={t('node-manager.cloudregion.environment.loadFailed')}
              description={t(
                'node-manager.cloudregion.environment.loadFailedDescription'
              )}
              action={
                <Button onClick={() => void fetchCloudRegion()}>
                  {t('common.retry')}
                </Button>
              }
            />
          )}
          <Spin spinning={loading && !detail}>
            {detail?.services?.length ? (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {detail.services.map((service) => {
                  const status = serviceStatus(service);
                  const isStargazer = service.name === 'stargazer';
                  const serviceIconColor = isStargazer
                    ? token.colorWarning
                    : 'var(--color-primary)';
                  return (
                    <Card
                      key={service.id}
                      size="small"
                      className="overflow-hidden border-[var(--color-border)]"
                      style={{
                        borderTop: `3px solid ${status.accent}`,
                        background: status.surface,
                      }}
                      styles={{ body: { padding: '18px 20px' } }}
                    >
                      <div className="flex min-h-12 items-center justify-between gap-4">
                        <Space size={12}>
                          <span
                            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-xl"
                            style={{
                              color: serviceIconColor,
                              background: `color-mix(in srgb, ${serviceIconColor} 12%, transparent)`,
                            }}
                          >
                            {isStargazer ? (
                              <StarOutlined />
                            ) : (
                              <RocketOutlined />
                            )}
                          </span>
                          <div>
                            <Typography.Text
                              strong
                              className="text-base"
                              style={{ color: status.titleColor }}
                            >
                              {service.name}
                            </Typography.Text>
                            {service.message && service.health_status === 'abnormal' && (
                              <div className="mt-1 max-w-[560px] text-xs text-[var(--color-text-3)]">
                                {service.message}
                              </div>
                            )}
                          </div>
                        </Space>
                        <Tag color={status.color} icon={status.icon} className="m-0">
                          {status.label}
                        </Tag>
                      </div>
                    </Card>
                  );
                })}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Spin>
        </section>

        <section aria-labelledby="environment-deployment-title">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3
              id="environment-deployment-title"
              className="m-0 text-base font-semibold"
            >
              {t('node-manager.cloudregion.environment.envDeploy')}
            </h3>
            <Segmented
              value={deploymentView}
              options={[
                {
                  label: t('node-manager.cloudregion.environment.containerDeploy'),
                  value: 'container',
                },
                {
                  label: t('node-manager.cloudregion.environment.k8sDeploy'),
                  value: 'k8s',
                },
              ]}
              onChange={(value) => setDeploymentView(value as DeploymentView)}
            />
          </div>

          {deploymentView === 'k8s'
            ? renderK8sDeployment()
            : detail &&
              (detail.is_default
                ? renderDefaultMaintenance()
                : detail.deployment_state === 'not_deployed'
                  ? renderFirstDeployment()
                  : renderManagedDeployment())}
          {(deploymentView !== 'container' ||
            detail?.deployment_state !== 'not_deployed' ||
            detail?.is_default) && (
            <Form form={deployForm} className="hidden" aria-hidden />
          )}
        </section>
      </div>

      {changeModalOpen ? (
        <Modal
          title={t('node-manager.cloudregion.environment.changeProxyTitle')}
          open
          confirmLoading={changing}
          okText={t('node-manager.cloudregion.environment.stageAndGenerate')}
          cancelText={t('common.cancel')}
          onOk={() => stageProxyAddress()}
          onCancel={() => {
            changeForm.resetFields();
            setChangeModalOpen(false);
          }}
        >
          <Alert
            className="mb-4"
            type="warning"
            showIcon
            message={t('node-manager.cloudregion.environment.changeProxyWarning')}
          />
          <Form form={changeForm} layout="vertical">
            <Form.Item label={t('node-manager.cloudregion.environment.currentProxy')}>
              <Input value={detail?.proxy_address || '-'} readOnly />
            </Form.Item>
            <Form.Item
              name="proxyIp"
              label={t('node-manager.cloudregion.environment.pendingProxy')}
              rules={[
                { required: true, message: t('common.inputRequired') },
                {
                  validator: (_, value) =>
                    !value || isValidProxyAddress(value)
                      ? Promise.resolve()
                      : Promise.reject(
                        new Error(t('node-manager.cloudregion.deploy.ipFormatError'))
                      ),
                },
              ]}
            >
              <Input
                autoFocus
                className="h-10"
                placeholder={t('node-manager.cloudregion.environment.proxyIpPlaceholder')}
              />
            </Form.Item>
          </Form>
        </Modal>
      ) : (
        <Form form={changeForm} className="hidden" aria-hidden />
      )}
      {commandCopyDialog}
    </MainLayout>
  );
};

export default EnvironmentPage;
