'use client';
import React, { useState, useEffect } from 'react';
import useApiClient from '@/utils/request';
import { Form, Input, Select, InputNumber, Button, Radio, message } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import Icon from '@/components/icon';
import GroupTreeSelector from '@/components/group-tree-select';
import useIntegrationApi from '@/app/monitor/api/integration';
import useMonitorApi from '@/app/monitor/api';
import { v4 as uuidv4 } from 'uuid';
import { AccessConfigProps } from '@/app/monitor/types/integration';
import IntegrationStepCallout, {
  createMonitorK8sStepCalloutPreset,
} from '@/components/integration-step-callout';
import {
  DEFAULT_K8S_IMAGE_REGISTRY_PREFIX,
  isValidK8sImageRegistryPrefix,
} from '@/utils/k8sImageRegistry';
import {
  DEFAULT_K8S_DS_TOLERATIONS,
  K8S_DS_TOLERATION_EFFECTS,
  MAX_K8S_DS_TOLERATIONS,
  isValidK8sTolerations,
  k8sTolerationModeFromValue,
  k8sTolerationsFromMode,
  type K8sTolerationMode,
} from '@/utils/k8sTolerations';
import { parseIntegrationObjectId } from '@/app/monitor/utils/integrationEntryContext';

const AccessConfig: React.FC<AccessConfigProps> = ({ onNext, commandData }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const searchParams = useSearchParams();
  const objectId = parseIntegrationObjectId(searchParams.get('id'));
  const { isLoading } = useApiClient();
  const { getCloudRegionList, createK8sInstance, getK8sCommand } =
    useIntegrationApi();
  const { getInstanceList } = useMonitorApi();
  const [submitLoading, setSubmitLoading] = useState(false);
  const [cloudRegionLoading, setCloudRegionLoading] = useState(false);
  const [cloudRegionList, setCloudRegionList] = useState<any[]>([]);
  const [k8sClusterLoading, setK8sClusterLoading] = useState(false);
  const [k8sClusterList, setK8sClusterList] = useState<any[]>([]);
  const [unit, setUnit] = useState('seconds');
  const tolerationMode =
    (Form.useWatch('tolerationMode', form) as K8sTolerationMode | undefined) ??
    'default';

  // 表单控件宽度
  const FORM_CONTROL_WIDTH = 300;

  useEffect(() => {
    if (!isLoading) {
      getCloudRegions();
      if (objectId) {
        getK8sClusters();
      }
    }
  }, [isLoading]);

  // 当commandData存在时,回显数据
  useEffect(() => {
    if (commandData) {
      form.setFieldsValue({
        accessType: 'existing',
        interval: commandData.interval,
        image_registry_prefix:
          commandData.image_registry_prefix || DEFAULT_K8S_IMAGE_REGISTRY_PREFIX,
        tolerationMode: k8sTolerationModeFromValue(commandData.tolerations),
        tolerationItems: Array.isArray(commandData.tolerations)
          ? commandData.tolerations
          : DEFAULT_K8S_DS_TOLERATIONS,
      });
    }
  }, [commandData, form]);

  const getCloudRegions = async () => {
    setCloudRegionLoading(true);
    try {
      const data = await getCloudRegionList({ page_size: -1 });
      setCloudRegionList(data || []);
      if (commandData?.cloud_region_id) {
        form.setFieldsValue({
          cloud_region_id: commandData.cloud_region_id,
        });
      }
    } finally {
      setCloudRegionLoading(false);
    }
  };

  const getK8sClusters = async () => {
    setK8sClusterLoading(true);
    try {
      const data = await getInstanceList(objectId, { page_size: -1 });
      setK8sClusterList(data?.results || []);
      if (commandData?.instance_id) {
        form.setFieldsValue({
          k8sCluster: commandData.instance_id,
        });
      }
    } finally {
      setK8sClusterLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!objectId) {
      message.error(t('monitor.integrations.missingEntryContext'));
      return;
    }
    try {
      setSubmitLoading(true);
      const values = await form.validateFields();
      const commandParams = {
        cloud_region_id: values.cloud_region_id,
        interval: values.interval,
        image_registry_prefix: values.image_registry_prefix,
        tolerations: k8sTolerationsFromMode(
          values.tolerationMode,
          values.tolerationItems
        ),
      };
      if (values.accessType === 'new') {
        // 新建资产：先创建实例，再获取命令
        const id = uuidv4().replace(/-/g, '');
        const createParams = {
          name: values.name,
          organizations: values.organizations,
          monitor_object_id: objectId,
          id,
        };
        const createResult = await createK8sInstance(createParams);
        const commandResult = await getK8sCommand({
          ...commandParams,
          instance_id: createResult?.instance_id,
        });
        onNext({
          command: commandResult,
          ...commandParams,
          monitor_object_id: objectId,
          instance_id: createResult?.instance_id,
        });
      } else {
        // 已有资产：直接获取命令
        const commandResult = await getK8sCommand({
          ...commandParams,
          instance_id: values.k8sCluster,
        });
        onNext({
          command: commandResult,
          ...commandParams,
          monitor_object_id: objectId,
          instance_id: values.k8sCluster,
        });
      }
    } catch (error) {
      console.error('Submit error:', error);
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <div className="p-0">
      <IntegrationStepCallout {...createMonitorK8sStepCalloutPreset(t)} />

      <Form
        form={form}
        layout="vertical"
        className="w-full"
        initialValues={{
          accessType: 'new',
          interval: 60,
          image_registry_prefix: DEFAULT_K8S_IMAGE_REGISTRY_PREFIX,
          tolerationMode: 'default',
          tolerationItems: DEFAULT_K8S_DS_TOLERATIONS,
        }}
      >
        {/* 接入配置标题 */}
        <div className="flex items-center mb-6">
          <Icon type="settings-fill" className="text-lg mr-2" />
          <h3 className="text-base font-semibold">
            {t('monitor.integrations.k8s.accessConfig')}
          </h3>
        </div>

        {/* 接入资产选择 */}
        <Form.Item label={t('monitor.integrations.k8s.accessAsset')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="accessType"
              noStyle
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Radio.Group style={{ width: FORM_CONTROL_WIDTH }}>
                <Radio value="new">
                  {t('monitor.integrations.k8s.newAsset')}
                </Radio>
                <Radio value="existing">
                  {t('monitor.integrations.k8s.existingAsset')}
                </Radio>
              </Radio.Group>
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('monitor.integrations.k8s.accessAssetDesc')}
            </div>
          </div>
        </Form.Item>

        {/* 根据接入资产类型显示不同内容 */}
        <Form.Item
          noStyle
          shouldUpdate={(prevValues, currentValues) =>
            prevValues.accessType !== currentValues.accessType
          }
        >
          {({ getFieldValue }) =>
            getFieldValue('accessType') === 'new' ? (
              <>
                {/* 新建资产 - 集群名称 */}
                <Form.Item
                  label={t('monitor.integrations.k8s.clusterName')}
                  required
                >
                  <div className="flex items-start gap-4">
                    <Form.Item
                      name="name"
                      noStyle
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Input
                        placeholder={t('common.inputTip')}
                        style={{ width: FORM_CONTROL_WIDTH }}
                      />
                    </Form.Item>
                    <div className="text-[var(--color-text-3)] flex-1">
                      {t('monitor.integrations.k8s.clusterNameDesc')}
                    </div>
                  </div>
                </Form.Item>
                {/* 新建资产 - 所属组织 */}
                <Form.Item
                  label={t('monitor.integrations.k8s.organization')}
                  required
                >
                  <div className="flex items-start gap-4">
                    <Form.Item
                      name="organizations"
                      noStyle
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <GroupTreeSelector
                        style={{ width: FORM_CONTROL_WIDTH }}
                        placeholder={t('common.selectTip')}
                      />
                    </Form.Item>
                    <div className="text-[var(--color-text-3)] flex-1">
                      {t('monitor.integrations.k8s.organizationDesc')}
                    </div>
                  </div>
                </Form.Item>
              </>
            ) : (
              <>
                {/* 已有资产 - K8s集群 */}
                <Form.Item
                  label={t('monitor.integrations.k8s.k8sCluster')}
                  required
                >
                  <div className="flex items-start gap-4">
                    <Form.Item
                      name="k8sCluster"
                      noStyle
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Select
                        placeholder={t('common.selectTip')}
                        style={{ width: FORM_CONTROL_WIDTH }}
                        loading={k8sClusterLoading}
                        options={k8sClusterList.map((item) => ({
                          value: item.instance_id,
                          label: item.instance_name,
                        }))}
                      />
                    </Form.Item>
                    <div className="text-[var(--color-text-3)] flex-1">
                      {t('monitor.integrations.k8s.k8sClusterDesc')}
                    </div>
                  </div>
                </Form.Item>
              </>
            )
          }
        </Form.Item>
        {/* 新建资产 - 云区域 */}
        <Form.Item label={t('monitor.integrations.k8s.cloudRegion')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="cloud_region_id"
              noStyle
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Select
                placeholder={t('common.selectTip')}
                style={{ width: FORM_CONTROL_WIDTH }}
                loading={cloudRegionLoading}
                options={cloudRegionList.map((item) => ({
                  value: item.id,
                  label: item.name,
                }))}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('monitor.integrations.k8s.cloudRegionDesc')}
            </div>
          </div>
        </Form.Item>
        <Form.Item
          label={t('monitor.integrations.k8s.imageRegistryPrefix')}
          required
        >
          <div className="flex items-start gap-4">
            <Form.Item
              name="image_registry_prefix"
              noStyle
              validateTrigger="onBlur"
              rules={[
                { required: true, message: t('common.required') },
                {
                  validator: (_, value) =>
                    isValidK8sImageRegistryPrefix(value)
                      ? Promise.resolve()
                      : Promise.reject(
                        new Error(
                          t('monitor.integrations.k8s.imageRegistryInvalid')
                        )
                      ),
                },
              ]}
            >
              <Input
                placeholder={DEFAULT_K8S_IMAGE_REGISTRY_PREFIX}
                style={{ width: FORM_CONTROL_WIDTH }}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('monitor.integrations.k8s.imageRegistryPrefixDesc')}
            </div>
          </div>
        </Form.Item>
        <Form.Item
          label={t('monitor.integrations.k8s.tolerations')}
          required
        >
          <div className="flex items-start gap-4">
            <div className="w-[300px]">
              <Form.Item name="tolerationMode" noStyle>
                <Radio.Group
                  className="flex flex-col gap-2"
                  onChange={(event) => {
                    if (
                      event.target.value === 'custom' &&
                      !form.getFieldValue('tolerationItems')?.length
                    ) {
                      form.setFieldsValue({
                        tolerationItems: DEFAULT_K8S_DS_TOLERATIONS,
                      });
                    }
                  }}
                >
                  <Radio value="default">
                    {t('monitor.integrations.k8s.tolerationsModeDefault')}
                  </Radio>
                  <Radio value="custom">
                    {t('monitor.integrations.k8s.tolerationsModeCustom')}
                  </Radio>
                  <Radio value="none">
                    {t('monitor.integrations.k8s.tolerationsModeNone')}
                  </Radio>
                </Radio.Group>
              </Form.Item>
              {tolerationMode === 'custom' ? (
                <Form.List
                  name="tolerationItems"
                  rules={[
                    {
                      validator: async (_, value) => {
                        if (!isValidK8sTolerations(value ?? [])) {
                          throw new Error(
                            t('monitor.integrations.k8s.tolerationsInvalid')
                          );
                        }
                      },
                    },
                  ]}
                >
                  {(fields, { add, remove }) => (
                    <div className="mt-3 flex flex-col gap-2">
                      {fields.map((field) => (
                        <div key={field.key} className="flex items-start gap-2">
                          <Form.Item
                            {...field}
                            name={[field.name, 'key']}
                            className="mb-0 flex-1"
                            rules={[
                              {
                                required: true,
                                message: t('common.required'),
                              },
                            ]}
                          >
                            <Input
                              placeholder={t(
                                'monitor.integrations.k8s.tolerationsKey'
                              )}
                            />
                          </Form.Item>
                          <Form.Item
                            {...field}
                            name={[field.name, 'effect']}
                            className="mb-0 w-[130px]"
                            rules={[
                              {
                                required: true,
                                message: t('common.required'),
                              },
                            ]}
                          >
                            <Select
                              options={K8S_DS_TOLERATION_EFFECTS.map(
                                (effect) => ({
                                  value: effect,
                                  label: effect,
                                })
                              )}
                            />
                          </Form.Item>
                          <Form.Item
                            {...field}
                            name={[field.name, 'value']}
                            className="mb-0 w-[90px]"
                          >
                            <Input
                              placeholder={t(
                                'monitor.integrations.k8s.tolerationsValue'
                              )}
                            />
                          </Form.Item>
                          <MinusCircleOutlined
                            className="mt-2 text-[var(--color-text-3)]"
                            onClick={() => remove(field.name)}
                          />
                        </div>
                      ))}
                      {fields.length < MAX_K8S_DS_TOLERATIONS ? (
                        <Button
                          type="dashed"
                          icon={<PlusOutlined />}
                          onClick={() =>
                            add({ key: '', effect: 'NoSchedule' })
                          }
                        >
                          {t('monitor.integrations.k8s.tolerationsAdd')}
                        </Button>
                      ) : null}
                    </div>
                  )}
                </Form.List>
              ) : null}
            </div>
            <div className="text-[var(--color-text-3)] flex-1">
              {tolerationMode === 'none'
                ? t('monitor.integrations.k8s.tolerationsModeNoneHint')
                : t('monitor.integrations.k8s.tolerationsDesc')}
            </div>
          </div>
        </Form.Item>
        {/* 上报间隔 */}
        <Form.Item
          label={t('monitor.integrations.k8s.uploadInterval')}
          required
          className="mb-8"
        >
          <div className="flex items-start gap-4">
            <Form.Item
              name="interval"
              noStyle
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <InputNumber
                style={{ width: FORM_CONTROL_WIDTH }}
                min={1}
                max={unit === 'seconds' ? 3600 : unit === 'minutes' ? 60 : 24}
                precision={0}
                placeholder={t('common.inputTip')}
                addonAfter={
                  <Select
                    value={unit}
                    style={{ width: 80 }}
                    onChange={(val) => setUnit(val)}
                  >
                    <Select.Option value="seconds">
                      {t('monitor.integrations.k8s.seconds')}
                    </Select.Option>
                    <Select.Option value="minutes">
                      {t('monitor.integrations.k8s.minutes')}
                    </Select.Option>
                    <Select.Option value="hours">
                      {t('monitor.integrations.k8s.hours')}
                    </Select.Option>
                  </Select>
                }
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('monitor.integrations.k8s.uploadIntervalDesc')}
            </div>
          </div>
        </Form.Item>

        {/* 下一步按钮 */}
        <div className="flex justify-end mt-6">
          <Button
            type="primary"
            loading={submitLoading}
            disabled={!objectId}
            onClick={handleSubmit}
          >
            {t('common.next')} →
          </Button>
        </div>
      </Form>
    </div>
  );
};

export default AccessConfig;
