'use client';

import React, { useEffect, useState } from 'react';
import { Form, Input, Select, Button, Radio } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import GroupTreeSelector from '@/components/group-tree-select';
import Icon from '@/components/icon';
import { K8sCommandData } from './k8sConfiguration';
import FormSettingRow from '@/components/form-setting-row';
import CollectSettingFields, {
  FieldLabel,
  K8S_SETTING_FORM_WIDTH
} from './collectSettingFields';
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
    getK8sCollectSetting,
    saveK8sCollectSetting,
    getInstanceList
  } = useIntegrationApi();
  const [submitLoading, setSubmitLoading] = useState(false);
  const [cloudRegionLoading, setCloudRegionLoading] = useState(false);
  const [cloudRegionList, setCloudRegionList] = useState<CloudRegionItem[]>([]);
  const [k8sClusterLoading, setK8sClusterLoading] = useState(false);
  const [k8sClusterList, setK8sClusterList] = useState<InstanceItem[]>([]);
  const [settingUnknown, setSettingUnknown] = useState(false);
  const [dockerPathForFields, setDockerPathForFields] = useState(
    commandData?.docker_container_log_path
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
        docker_container_log_path: commandData.docker_container_log_path,
        namespace_patterns: commandData.namespace_patterns,
        pod_patterns: commandData.pod_patterns
      });
      setDockerPathForFields(commandData.docker_container_log_path);
      if (commandData.instance_id) {
        void loadSetting(commandData.instance_id);
      }
    }
  }, [commandData, form]);

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

  const loadSetting = async (instanceId: string) => {
    const setting = await getK8sCollectSetting(instanceId);
    if (setting?.unknown) {
      setSettingUnknown(true);
      setDockerPathForFields(undefined);
      form.setFieldsValue({
        runtime_profile: undefined,
        host_log_path: undefined,
        docker_container_log_path: undefined,
        namespace_patterns: undefined,
        pod_patterns: undefined
      });
      return;
    }
    setSettingUnknown(false);
    const dockerPath = setting?.docker_container_log_path;
    setDockerPathForFields(dockerPath);
    form.setFieldsValue({
      runtime_profile: setting?.runtime_profile,
      host_log_path: setting?.host_log_path,
      docker_container_log_path: dockerPath,
      namespace_patterns: (setting?.namespace_patterns || []).join('\n'),
      pod_patterns: (setting?.pod_patterns || []).join('\n')
    });
  };

  const handleSubmit = async () => {
    try {
      setSubmitLoading(true);
      const values = await form.validateFields();
      const settingPayload = {
        cloud_region_id: values.cloud_region_id,
        runtime_profile: values.runtime_profile as RuntimeProfile,
        host_log_path: values.host_log_path,
        docker_container_log_path: values.docker_container_log_path,
        namespace_patterns: values.namespace_patterns,
        pod_patterns: values.pod_patterns
      };

      let instanceId = values.k8sCluster as string;
      if (values.accessType === 'new') {
        const clusterName = String(values.name || '').trim();
        const createResult = await createK8sInstance({
          id: clusterName,
          name: clusterName,
          organizations: values.organizations,
          collect_type_id: collectTypeId
        });
        instanceId = createResult?.instance_id;
      }

      const settingResult = await saveK8sCollectSetting({
        ...settingPayload,
        instance_id: instanceId
      });
      onNext({
        command: settingResult?.command,
        instance_id: instanceId,
        cloud_region_id: values.cloud_region_id,
        runtime_profile: values.runtime_profile,
        host_log_path: values.host_log_path,
        docker_container_log_path: values.docker_container_log_path,
        namespace_patterns: values.namespace_patterns,
        pod_patterns: values.pod_patterns
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

        <Form.Item
          label={
            <FieldLabel
              label={t('log.integration.k8s.accessAsset')}
              detail={t('log.integration.k8s.accessAssetDesc')}
            />
          }
          required
        >
          <FormSettingRow
            control={
              <Form.Item
                name="accessType"
                noStyle
                rules={[{ required: true, message: t('common.required') }]}
              >
                <Radio.Group
                  style={{ width: K8S_SETTING_FORM_WIDTH }}
                  onChange={(event) => {
                    if (event.target.value === 'new') {
                      setSettingUnknown(false);
                      form.setFieldsValue({ runtime_profile: 'standard' });
                    }
                  }}
                >
                  <Radio value="new">{t('log.integration.k8s.newAsset')}</Radio>
                  <Radio value="existing">
                    {t('log.integration.k8s.existingAsset')}
                  </Radio>
                </Radio.Group>
              </Form.Item>
            }
            description={t('log.integration.k8s.accessAssetHint')}
          />
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
                  label={
                    <FieldLabel
                      label={t('log.integration.k8s.clusterName')}
                      detail={t('log.integration.k8s.clusterNameDesc')}
                    />
                  }
                  required
                >
                  <FormSettingRow
                    control={
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
                          style={{ width: K8S_SETTING_FORM_WIDTH }}
                        />
                      </Form.Item>
                    }
                    description={t('log.integration.k8s.clusterNameHint')}
                  />
                </Form.Item>

                <Form.Item
                  label={
                    <FieldLabel
                      label={t('log.integration.k8s.organization')}
                      detail={t('log.integration.k8s.organizationDesc')}
                    />
                  }
                  required
                >
                  <FormSettingRow
                    control={
                      <Form.Item
                        name="organizations"
                        noStyle
                        rules={[
                          { required: true, message: t('common.required') }
                        ]}
                      >
                        <GroupTreeSelector
                          style={{ width: K8S_SETTING_FORM_WIDTH }}
                          placeholder={t('common.selectTip')}
                        />
                      </Form.Item>
                    }
                    description={t('log.integration.k8s.organizationHint')}
                  />
                </Form.Item>
              </>
            ) : (
              <Form.Item
                label={
                  <FieldLabel
                    label={t('log.integration.k8s.k8sCluster')}
                    detail={t('log.integration.k8s.k8sClusterDesc')}
                  />
                }
                required
              >
                <FormSettingRow
                  control={
                    <Form.Item
                      name="k8sCluster"
                      noStyle
                      rules={[{ required: true, message: t('common.required') }]}
                    >
                      <Select
                        showSearch
                        loading={k8sClusterLoading}
                        placeholder={t('log.integration.k8s.selectK8sCluster')}
                        style={{ width: K8S_SETTING_FORM_WIDTH }}
                        options={k8sClusterList.map((item) => ({
                          label: item.name,
                          value: item.id
                        }))}
                        onChange={(value) => {
                          if (value) {
                            void loadSetting(String(value));
                          }
                        }}
                      />
                    </Form.Item>
                  }
                  description={t('log.integration.k8s.k8sClusterHint')}
                />
              </Form.Item>
            )
          }
        </Form.Item>

        <Form.Item
          label={
            <FieldLabel
              label={t('log.integration.k8s.cloudRegion')}
              detail={t('log.integration.k8s.cloudRegionDesc')}
            />
          }
          required
        >
          <FormSettingRow
            control={
              <Form.Item
                name="cloud_region_id"
                noStyle
                rules={[{ required: true, message: t('common.required') }]}
              >
                <Select
                  loading={cloudRegionLoading}
                  placeholder={t('log.integration.k8s.selectCloudRegion')}
                  style={{ width: K8S_SETTING_FORM_WIDTH }}
                  options={cloudRegionList.map((item) => ({
                    label: item.name || item.id,
                    value: item.id
                  }))}
                />
              </Form.Item>
            }
            description={t('log.integration.k8s.cloudRegionHint')}
          />
        </Form.Item>

        <CollectSettingFields
          unknown={settingUnknown}
          initialDockerPath={dockerPathForFields}
        />

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
