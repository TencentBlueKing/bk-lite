'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Form, Input, Select, Button, Radio } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import GroupTreeSelector from '@/components/group-tree-select';
import Icon from '@/components/icon';
import { K8sCommandData } from './k8sConfiguration';
import IntegrationStepCallout, {
  createLogK8sStepCalloutPreset,
} from '@/components/integration-step-callout';

interface AccessConfigProps {
  onNext: (data?: K8sCommandData) => void;
  commandData: K8sCommandData | null;
}

interface CloudRegionItem {
  id: React.Key;
  name?: string;
}

interface InstanceItem {
  id: string;
  name: string;
}

type RuntimeProfile = 'standard' | 'docker' | 'custom';

const FORM_CONTROL_WIDTH = 300;

const AccessConfig: React.FC<AccessConfigProps> = ({ onNext, commandData }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const searchParams = useSearchParams();
  const collectTypeId = searchParams.get('id')
    ? Number(searchParams.get('id'))
    : undefined;
  const { isLoading } = useApiClient();
  const {
    getCloudRegionList,
    createK8sInstance,
    getK8sCommand,
    getInstanceList
  } = useIntegrationApi();
  const [submitLoading, setSubmitLoading] = useState(false);
  const [cloudRegionLoading, setCloudRegionLoading] = useState(false);
  const [cloudRegionList, setCloudRegionList] = useState<CloudRegionItem[]>([]);
  const [k8sClusterLoading, setK8sClusterLoading] = useState(false);
  const [k8sClusterList, setK8sClusterList] = useState<InstanceItem[]>([]);
  const hasDockerContainerPath = useMemo(
    () => Boolean(String(commandData?.docker_container_log_path || '').trim()),
    [commandData?.docker_container_log_path]
  );
  const [showDockerAdvanced, setShowDockerAdvanced] = useState(
    hasDockerContainerPath
  );

  useEffect(() => {
    if (!isLoading) {
      void getCloudRegions();
      void getK8sClusters();
    }
  }, [isLoading]);

  useEffect(() => {
    if (commandData) {
      form.setFieldsValue({
        accessType: 'existing',
        cloud_region_id: commandData.cloud_region_id,
        k8sCluster: commandData.instance_id,
        runtime_profile: commandData.runtime_profile || 'standard',
        host_log_path: commandData.host_log_path,
        docker_container_log_path: commandData.docker_container_log_path
      });
    }
  }, [commandData, form]);

  useEffect(() => {
    setShowDockerAdvanced(hasDockerContainerPath);
  }, [hasDockerContainerPath]);

  const getCloudRegions = async () => {
    setCloudRegionLoading(true);
    try {
      const data = await getCloudRegionList();
      setCloudRegionList(data || []);
    } finally {
      setCloudRegionLoading(false);
    }
  };

  const getK8sClusters = async () => {
    if (!collectTypeId) {
      return;
    }
    setK8sClusterLoading(true);
    try {
      const data = await getInstanceList({
        collect_type_id: collectTypeId,
        page: 1,
        page_size: -1
      });
      setK8sClusterList(data?.items || []);
    } finally {
      setK8sClusterLoading(false);
    }
  };

  const handleSubmit = async () => {
    try {
      setSubmitLoading(true);
      const values = await form.validateFields();
      const commandParams = {
        cloud_region_id: values.cloud_region_id,
        runtime_profile: values.runtime_profile as RuntimeProfile,
        host_log_path: values.host_log_path,
        docker_container_log_path: values.docker_container_log_path
      };

      if (values.accessType === 'new') {
        const clusterName = String(values.name || '').trim();
        const createResult = await createK8sInstance({
          id: clusterName,
          name: clusterName,
          organizations: values.organizations,
          collect_type_id: collectTypeId
        });
        const commandResult = await getK8sCommand({
          ...commandParams,
          instance_id: createResult?.instance_id
        });
        onNext({
          command: commandResult,
          instance_id: createResult?.instance_id,
          cloud_region_id: values.cloud_region_id,
          runtime_profile: values.runtime_profile,
          host_log_path: values.host_log_path,
          docker_container_log_path: values.docker_container_log_path
        });
        return;
      }

      const commandResult = await getK8sCommand({
        ...commandParams,
        instance_id: values.k8sCluster
      });
      onNext({
        command: commandResult,
        instance_id: values.k8sCluster,
        cloud_region_id: values.cloud_region_id,
        runtime_profile: values.runtime_profile,
        host_log_path: values.host_log_path,
        docker_container_log_path: values.docker_container_log_path
      });
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <div className="p-0">
      <IntegrationStepCallout {...createLogK8sStepCalloutPreset(t)} />

      <Form
        form={form}
        layout="vertical"
        className="w-full"
        initialValues={{
          accessType: 'new',
          runtime_profile: commandData?.runtime_profile || 'standard'
        }}
      >
        <div className="flex items-center mb-6">
          <Icon type="settings-fill" className="text-lg mr-2" />
          <h3 className="text-base font-semibold">
            {t('log.integration.k8s.accessConfig')}
          </h3>
        </div>

        <Form.Item label={t('log.integration.k8s.accessAsset')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="accessType"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Radio.Group style={{ width: FORM_CONTROL_WIDTH }}>
                <Radio value="new">{t('log.integration.k8s.newAsset')}</Radio>
                <Radio value="existing">
                  {t('log.integration.k8s.existingAsset')}
                </Radio>
              </Radio.Group>
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('log.integration.k8s.accessAssetDesc')}
            </div>
          </div>
        </Form.Item>

        <Form.Item
          noStyle
          shouldUpdate={(prevValues, currentValues) =>
            prevValues.accessType !== currentValues.accessType
          }
        >
          {({ getFieldValue }) =>
            getFieldValue('accessType') === 'new' ? (
              <>
                <Form.Item
                  label={t('log.integration.k8s.clusterName')}
                  required
                >
                  <div className="flex items-start gap-4">
                    <Form.Item
                      name="name"
                      noStyle
                      rules={[
                        { required: true, message: t('common.required') }
                      ]}
                    >
                      <Input
                        placeholder={t(
                          'log.integration.k8s.clusterNamePlaceholder'
                        )}
                        style={{ width: FORM_CONTROL_WIDTH }}
                      />
                    </Form.Item>
                    <div className="text-[var(--color-text-3)] flex-1">
                      {t('log.integration.k8s.clusterNameDesc')}
                    </div>
                  </div>
                </Form.Item>

                <Form.Item
                  label={t('log.integration.k8s.organization')}
                  required
                >
                  <div className="flex items-start gap-4">
                    <Form.Item
                      name="organizations"
                      noStyle
                      rules={[
                        { required: true, message: t('common.required') }
                      ]}
                    >
                      <GroupTreeSelector
                        style={{ width: FORM_CONTROL_WIDTH }}
                        placeholder={t('common.selectTip')}
                      />
                    </Form.Item>
                    <div className="text-[var(--color-text-3)] flex-1">
                      {t('log.integration.k8s.organizationDesc')}
                    </div>
                  </div>
                </Form.Item>
              </>
            ) : (
              <Form.Item label={t('log.integration.k8s.k8sCluster')} required>
                <div className="flex items-start gap-4">
                  <Form.Item
                    name="k8sCluster"
                    noStyle
                    rules={[{ required: true, message: t('common.required') }]}
                  >
                    <Select
                      showSearch
                      loading={k8sClusterLoading}
                      placeholder={t('log.integration.k8s.selectK8sCluster')}
                      style={{ width: FORM_CONTROL_WIDTH }}
                      options={k8sClusterList.map((item) => ({
                        label: item.name,
                        value: item.id
                      }))}
                    />
                  </Form.Item>
                  <div className="text-[var(--color-text-3)] flex-1">
                    {t('log.integration.k8s.k8sClusterDesc')}
                  </div>
                </div>
              </Form.Item>
            )
          }
        </Form.Item>

        <Form.Item label={t('log.integration.k8s.cloudRegion')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="cloud_region_id"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Select
                loading={cloudRegionLoading}
                placeholder={t('log.integration.k8s.selectCloudRegion')}
                style={{ width: FORM_CONTROL_WIDTH }}
                options={cloudRegionList.map((item) => ({
                  label: item.name || item.id,
                  value: item.id
                }))}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('log.integration.k8s.cloudRegionDesc')}
            </div>
          </div>
        </Form.Item>

        <Form.Item label={t('log.integration.k8s.runtimeProfile')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="runtime_profile"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Radio.Group style={{ width: FORM_CONTROL_WIDTH }}>
                <Radio value="standard">
                  {t('log.integration.k8s.runtimeProfileStandard')}
                </Radio>
                <Radio value="docker">
                  {t('log.integration.k8s.runtimeProfileDocker')}
                </Radio>
                <Radio value="custom">
                  {t('log.integration.k8s.runtimeProfileCustom')}
                </Radio>
              </Radio.Group>
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('log.integration.k8s.runtimeProfileDesc')}
            </div>
          </div>
        </Form.Item>

        <Form.Item
          noStyle
          shouldUpdate={(prevValues, currentValues) =>
            prevValues.runtime_profile !== currentValues.runtime_profile
          }
        >
          {({ getFieldValue }) =>
            getFieldValue('runtime_profile') === 'custom' ? (
              <>
                <Form.Item
                  label={t('log.integration.k8s.hostLogPath')}
                  required
                >
                  <div className="flex items-start gap-4">
                    <Form.Item
                      name="host_log_path"
                      noStyle
                      rules={[
                        { required: true, message: t('common.required') },
                        {
                          validator: (_, value) => {
                            if (!value || String(value).startsWith('/')) {
                              return Promise.resolve();
                            }
                            return Promise.reject(
                              new Error(
                                t('log.integration.k8s.absolutePathRequired')
                              )
                            );
                          }
                        }
                      ]}
                    >
                      <Input
                        placeholder={t(
                          'log.integration.k8s.hostLogPathPlaceholder'
                        )}
                        style={{ width: FORM_CONTROL_WIDTH }}
                      />
                    </Form.Item>
                    <div className="text-[var(--color-text-3)] flex-1">
                      {t('log.integration.k8s.hostLogPathDesc')}
                    </div>
                  </div>
                </Form.Item>

                <Button
                  type="link"
                  className="px-0 mb-3"
                  onClick={() => setShowDockerAdvanced((prev) => !prev)}
                >
                  {showDockerAdvanced
                    ? t('log.integration.k8s.hideDockerAdvanced')
                    : t('log.integration.k8s.showDockerAdvanced')}
                </Button>

                {showDockerAdvanced ? (
                  <Form.Item
                    label={t('log.integration.k8s.dockerContainerLogPath')}
                  >
                    <div className="flex items-start gap-4">
                      <Form.Item
                        name="docker_container_log_path"
                        noStyle
                        rules={[
                          {
                            validator: (_, value) => {
                              if (!value || String(value).startsWith('/')) {
                                return Promise.resolve();
                              }
                              return Promise.reject(
                                new Error(
                                  t('log.integration.k8s.absolutePathRequired')
                                )
                              );
                            }
                          }
                        ]}
                      >
                        <Input
                          placeholder={t(
                            'log.integration.k8s.dockerContainerLogPathPlaceholder'
                          )}
                          style={{ width: FORM_CONTROL_WIDTH }}
                        />
                      </Form.Item>
                      <div className="text-[var(--color-text-3)] flex-1">
                        {t('log.integration.k8s.dockerContainerLogPathDesc')}
                      </div>
                    </div>
                  </Form.Item>
                ) : null}
              </>
            ) : null
          }
        </Form.Item>

        <div className="pt-[20px]">
          <Button type="primary" loading={submitLoading} onClick={handleSubmit}>
            {t('common.next')}
          </Button>
        </div>
      </Form>
    </div>
  );
};

export default AccessConfig;
