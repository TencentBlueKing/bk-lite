'use client';
import { useState, useEffect } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import {
  Card,
  Segmented,
  Input,
  Button,
  Tag,
  Space,
  Form,
  message,
  Modal,
  Spin,
  Empty,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  RocketOutlined,
  StarOutlined,
  EditOutlined,
  CheckCircleFilled,
  SyncOutlined,
  CheckOutlined,
  ExclamationCircleFilled,
} from '@ant-design/icons';
import useApiClient from '@/utils/request';
import CodeEditor from '@/app/node-manager/components/codeEditor';
import { useCommon } from '@/app/node-manager/context/common';
import MainLayout from '../mainlayout/layout';
import useNodeManagerApi from '@/app/node-manager/api';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { ServiceItem } from '@/app/node-manager/types/cloudregion';
import { useHandleCopy } from '@/app/node-manager/hooks';
import PermissionWrapper from '@/components/permission';

const EnvironmentPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { handleCopy } = useHandleCopy();
  const pathname = usePathname();
  const commonContext = useCommon();
  const nodeStateEnum = commonContext?.nodeStateEnum || {};
  const { isLoading } = useApiClient();
  const { getCloudRegionDetail, getDeployCommand, updatePartCloudIntro } =
    useNodeManagerApi();
  const cloudId = useCloudId();
  const [form] = Form.useForm();
  const searchParams = useSearchParams();
  const notDeployed = searchParams.get('not_deployed');
  const isNotDeployed = notDeployed === '1';
  const proxyAddress = searchParams.get('proxy_address') || '';
  const [deployType, setDeployType] = useState('container');
  const [script, setScript] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [envStatusList, setEnvStatusList] = useState<ServiceItem[]>([]);

  useEffect(() => {
    if (!isLoading) {
      fetchCloudRegions();
    }
  }, [isLoading]);

  // 获取相关的接口
  const fetchCloudRegions = async () => {
    setLoading(true);
    try {
      const data = await getCloudRegionDetail(cloudId);
      const services = data?.services || [];
      const list = services.map((item: ServiceItem) => ({
        ...item,
        icon:
          item.name === 'stargazer' ? (
            <StarOutlined style={{ fontSize: 24, color: '#faad14' }} />
          ) : (
            <RocketOutlined
              style={{ fontSize: 24, color: 'var(--color-primary)' }}
            />
          ),
      }));
      setEnvStatusList(list);
      // 修改 not_deployed 参数为 2 并跳转
      const servicesNotDeployed = services.find(
        (service) => service.status === 'not_deployed'
      );
      const flag = servicesNotDeployed ? '1' : '0';
      if (notDeployed !== flag) {
        const searchParams = new URLSearchParams(window.location.search);
        searchParams.set('not_deployed', flag);
        router.replace(`${pathname}?${searchParams.toString()}`);
      }
    } finally {
      setLoading(false);
    }
  };

  // 根据颜色值生成带透明度的背景色
  const getBackgroundColor = (color: string, opacity: number = 0.04) => {
    if (color.startsWith('var(')) {
      const varName = color.match(/var\((--[^)]+)\)/)?.[1];
      if (varName && typeof window !== 'undefined') {
        const computedColor = getComputedStyle(document.documentElement)
          .getPropertyValue(varName)
          .trim();
        return `color-mix(in srgb, ${computedColor} ${
          opacity * 100
        }%, transparent)`;
      }
    }
    return `color-mix(in srgb, ${color} ${opacity * 100}%, transparent)`;
  };

  // 状态配置管理
  const statusConfig = {
    error: {
      borderColor: 'var(--color-fail)',
      backgroundColor: getBackgroundColor('var(--color-fail)', 0.04),
      textColor: 'var(--color-fail)',
      tagColor: 'error' as const,
      label:
        nodeStateEnum.cloud_server_status?.error ||
        t('node-manager.cloudregion.environment.abnormal'),
    },
    normal: {
      borderColor: 'var(--color-success)',
      backgroundColor: getBackgroundColor('var(--color-success)', 0.04),
      textColor: 'var(--color-success)',
      tagColor: 'success' as const,
      label:
        nodeStateEnum.cloud_server_status?.normal ||
        t('node-manager.cloudregion.environment.normal'),
    },
    not_deployed: {
      borderColor: 'var(--color-fill-1)',
      backgroundColor: 'var(--color-fill-1)',
      textColor: 'var(--color-text-2)',
      tagColor: 'default' as const,
      label:
        nodeStateEnum.cloud_server_status?.not_deployed ||
        t('node-manager.cloudregion.environment.notDeployed'),
    },
  };

  const deployTabs = [
    {
      label: t('node-manager.cloudregion.environment.containerDeploy'),
      value: 'container',
    },
    {
      label: t('node-manager.cloudregion.environment.k8sDeploy'),
      value: 'k8s',
    },
  ];

  const generateScript = () => {
    form.validateFields(['proxyIp']).then(async (values) => {
      setScript('');
      setGenerateLoading(true);
      setIsEditing(false);
      const { proxyIp } = values;
      try {
        await updatePartCloudIntro(String(cloudId), {
          proxy_address: proxyIp || '',
        });
      } catch {
        setGenerateLoading(false);
      }
      // 模拟异步生成脚本
      getDeployCommand({ proxy_address: proxyIp })
        .then((res) => {
          const generatedScript = res?.commands || '';
          setScript(generatedScript);
          message.success(
            t('node-manager.cloudregion.environment.generateSuccess')
          );
        })
        .finally(() => {
          setGenerateLoading(false);
        });
    });
  };

  const handleEditConfirm = async () => {
    // 强制标记字段为 touched，确保验证被触发
    form.setFields([
      {
        name: 'proxyIp',
        touched: true,
      },
    ]);
    form.validateFields(['proxyIp']).then(() => {
      setIsEditing(false);
    });
  };

  const handleEditClick = () => {
    Modal.confirm({
      title: t('node-manager.cloudregion.environment.editWarningTitle'),
      icon: <ExclamationCircleFilled style={{ color: '#faad14' }} />,
      content: (
        <div>
          <p style={{ marginBottom: 16 }}>
            {t('node-manager.cloudregion.environment.editWarningContent')}
          </p>
          <div
            style={{
              background: getBackgroundColor('#faad14', 0.04),
              borderLeft: '3px solid #faad14',
              borderRadius: 4,
              padding: '12px 16px',
              color: 'var(--color-warning-text)',
            }}
          >
            {t('node-manager.cloudregion.environment.editWarningTip')}
          </div>
        </div>
      ),
      okText: t('node-manager.cloudregion.environment.confirmEdit'),
      cancelText: t('common.cancel'),
      onOk: () => {
        setIsEditing(true);
      },
    });
  };

  const copyScript = () => {
    handleCopy({
      value: script,
      showSuccessMessage: false,
    });
    Modal.confirm({
      title: t('node-manager.cloudregion.environment.copySuccess'),
      icon: <CheckCircleFilled style={{ color: 'var(--color-success)' }} />,
      content: t('node-manager.cloudregion.environment.copySuccessDesc'),
      okText: t('node-manager.cloudregion.environment.refreshProxyStatus'),
      cancelText: t('common.close'),
      okButtonProps: {
        icon: <SyncOutlined />,
      },
      onOk: () => {
        return refreshEnvStatus();
      },
    });
  };

  // 刷新环境状态
  const refreshEnvStatus = () => {
    return new Promise<void>(async (resolve) => {
      await fetchCloudRegions();
      message.success(t('common.refSuccess'));
      resolve();
    });
  };

  const linkToBklite = () => {
    window.open('https://bklite.ai/');
  };

  return (
    <MainLayout>
      <div className="w-[calc(100vw-288px)] min-w-[1000px] h-full">
        {/* 环境状态 */}
        <div style={{ marginBottom: 32 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 16,
            }}
          >
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
              {t('node-manager.cloudregion.environment.envStatus')}
            </h3>
            <Button
              icon={<SyncOutlined />}
              type="link"
              onClick={refreshEnvStatus}
            />
          </div>
          <Spin spinning={loading}>
            {!!envStatusList?.length ? (
              <div style={{ display: 'flex', gap: 24 }}>
                {envStatusList.map((envItem) => {
                  const config =
                    statusConfig[envItem.status] || statusConfig.not_deployed;
                  return (
                    <Card
                      key={envItem.id}
                      bordered={false}
                      style={{
                        flex: 1,
                        borderTop: `3px solid ${config.borderColor}`,
                        borderRadius: '4px',
                        background: config.backgroundColor,
                      }}
                      bodyStyle={{ padding: '20px 24px' }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <Space size={12}>
                          {envItem.icon}
                          <span
                            style={{
                              fontSize: 16,
                              fontWeight: 500,
                              color: config.textColor,
                            }}
                          >
                            {envItem.name}
                          </span>
                        </Space>
                        <Tag color={config.tagColor} style={{ margin: 0 }}>
                          {config.label}
                        </Tag>
                      </div>
                    </Card>
                  );
                })}
              </div>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ height: 54 }}
              />
            )}
          </Spin>
        </div>

        {/* 环境部署 */}
        <div>
          <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600 }}>
            {t('node-manager.cloudregion.environment.envDeploy')}
          </h3>

          <Segmented
            options={deployTabs}
            value={deployType}
            onChange={(value) => setDeployType(value as string)}
            style={{ marginBottom: 24 }}
          />

          {deployType === 'container' && (
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                proxyIp: proxyAddress,
              }}
            >
              <div
                style={{
                  background: 'var(--color-fill-1)',
                  padding: 24,
                  borderRadius: 4,
                  marginBottom: 24,
                }}
              >
                <Form.Item
                  label={t(
                    'node-manager.cloudregion.environment.proxyIpOrDomain'
                  )}
                >
                  <Space.Compact style={{ width: '100%' }}>
                    <Form.Item
                      name="proxyIp"
                      noStyle
                      rules={[
                        {
                          validator: (_, value) => {
                            if (!value) return Promise.resolve();
                            // IP地址验证
                            const ipPattern =
                              /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
                            // 域名验证
                            const domainPattern =
                              /^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$/;
                            // URL验证 (http/https)
                            const urlPattern =
                              /^https?:\/\/([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(\/.*)?$/;

                            if (
                              ipPattern.test(value) ||
                              domainPattern.test(value) ||
                              urlPattern.test(value)
                            ) {
                              return Promise.resolve();
                            }
                            return Promise.reject(
                              new Error(
                                t(
                                  'node-manager.cloudregion.deploy.ipFormatError'
                                )
                              )
                            );
                          },
                        },
                      ]}
                    >
                      <Input
                        placeholder={t(
                          'node-manager.cloudregion.environment.proxyIpPlaceholder'
                        )}
                        disabled={!isEditing && !isNotDeployed}
                      />
                    </Form.Item>
                    {!isNotDeployed && (
                      <Button
                        icon={isEditing ? <CheckOutlined /> : <EditOutlined />}
                        onClick={
                          isEditing ? handleEditConfirm : handleEditClick
                        }
                      />
                    )}
                  </Space.Compact>
                </Form.Item>
                <div
                  style={{
                    marginBottom: 16,
                    fontSize: 12,
                    color: 'var(--color-text-3)',
                    lineHeight: 1.6,
                  }}
                >
                  {t('node-manager.cloudregion.environment.proxyTips')}
                </div>
                <PermissionWrapper
                  className="mb-[20px]"
                  requiredPermissions={['Edit']}
                >
                  <Button
                    type="primary"
                    onClick={generateScript}
                    loading={generateLoading}
                  >
                    {t('node-manager.cloudregion.environment.generateScript')}
                  </Button>
                </PermissionWrapper>
                {script && (
                  <>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginBottom: 8,
                      }}
                    >
                      <span style={{ fontWeight: 500, fontSize: 14 }}>
                        {t('node-manager.cloudregion.environment.deployScript')}
                      </span>
                      <Button
                        type="link"
                        onClick={copyScript}
                        style={{ padding: 0 }}
                      >
                        {t('node-manager.cloudregion.environment.copyScript')}
                      </Button>
                    </div>
                    <Form.Item label="">
                      <CodeEditor
                        value={script}
                        width="100%"
                        height="250px"
                        mode="python"
                        theme="monokai"
                        name="editor"
                        readOnly
                      />
                    </Form.Item>
                  </>
                )}
              </div>
            </Form>
          )}
          {deployType === 'k8s' && (
            <div className="min-h-[400px] flex items-center justify-center bg-[var(--color-fill-1)] border-dashed border-[var(--color-primary)] border rounded-xl">
              <div className="text-center py-10 px-5">
                <div className="inline-flex items-center justify-center w-20 h-20 bg-[var(--color-primary)] rounded-[20px] mb-6">
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
          )}
        </div>
      </div>
    </MainLayout>
  );
};

export default EnvironmentPage;
