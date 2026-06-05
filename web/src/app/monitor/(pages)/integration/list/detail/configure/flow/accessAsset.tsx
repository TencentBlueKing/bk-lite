'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Form, Input, InputNumber, Radio, Select, message } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import useMonitorApi from '@/app/monitor/api';
import GroupTreeSelector from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import type { FlowProtocol } from '@/app/monitor/types/integration';
import type { FlowAssetWizardState } from './flowConfiguration';

interface FlowAssetFormValues {
  accessType: 'new' | 'existing';
  instance_id?: string;
  cloud_region_id?: number;
  ip?: string;
  name?: string;
  organizations?: React.Key[];
  fallback_sampling_rate?: number;
}

interface ExistingAssetItem {
  instance_id?: string;
  id?: string;
  instance_name?: string;
  name?: string;
  agent_id?: string;
  time?: string;
  cloud_region_id?: number;
  ip?: string;
  organizations?: React.Key[];
  fallback_sampling_rate?: number;
}

interface AccessAssetProps {
  protocol: FlowProtocol;
  objectId?: number;
  initialState?: FlowAssetWizardState;
  onNext: (data: FlowAssetWizardState) => void;
}

const FORM_CONTROL_WIDTH = 360;
const FALLBACK_SAMPLING_RATE_DEFAULT = 1000;

const protocolLabelMap: Record<FlowProtocol, string> = {
  netflow: 'NetFlow',
  sflow: 'sFlow'
};

const AccessAsset: React.FC<AccessAssetProps> = ({
  protocol,
  objectId,
  initialState,
  onNext
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<FlowAssetFormValues>();
  const { selectedGroup } = useUserInfoContext();
  const { createFlowAsset, getCloudRegionList } = useIntegrationApi();
  const { getInstanceList } = useMonitorApi();
  const [submitLoading, setSubmitLoading] = useState(false);
  const [cloudRegionLoading, setCloudRegionLoading] = useState(false);
  const [cloudRegionList, setCloudRegionList] = useState<any[]>([]);
  const [assetLoading, setAssetLoading] = useState(false);
  const [existingAssets, setExistingAssets] = useState<ExistingAssetItem[]>([]);
  const accessType = Form.useWatch('accessType', form);
  const getCloudRegionListRef = useRef(getCloudRegionList);
  const getInstanceListRef = useRef(getInstanceList);

  useEffect(() => {
    getCloudRegionListRef.current = getCloudRegionList;
  }, [getCloudRegionList]);

  useEffect(() => {
    getInstanceListRef.current = getInstanceList;
  }, [getInstanceList]);

  useEffect(() => {
    const fetchOptions = async () => {
      setCloudRegionLoading(true);
      setAssetLoading(true);
      try {
        const [regions, assets] = await Promise.all([
          getCloudRegionListRef.current({ page_size: -1 }),
          objectId
            ? getInstanceListRef.current(objectId, { page_size: -1 })
            : Promise.resolve({ results: [] })
        ]);
        const nextRegions = regions || [];
        const nextAssets = assets?.results || [];
        setCloudRegionList(nextRegions);
        setExistingAssets(nextAssets);

        form.setFieldsValue(
          initialState
            ? initialState
            : {
              accessType: 'new',
              organizations: selectedGroup?.id
                ? [Number(selectedGroup.id)]
                : undefined,
              fallback_sampling_rate: FALLBACK_SAMPLING_RATE_DEFAULT,
              cloud_region_id: nextRegions[0]?.id
            }
        );
      } finally {
        setCloudRegionLoading(false);
        setAssetLoading(false);
      }
    };

    fetchOptions();
  }, [form, initialState, objectId, selectedGroup?.id]);

  const existingAssetMap = useMemo(
    () =>
      existingAssets.reduce<Record<string, ExistingAssetItem>>((acc, item) => {
        const key = String(item.instance_id || item.id || '');
        if (key) {
          acc[key] = item;
        }
        return acc;
      }, {}),
    [existingAssets]
  );

  const assetOptions = useMemo(
    () =>
      existingAssets.map((item) => {
        const value = String(item.instance_id || item.id || '');
        const name = item.instance_name || item.name || value;
        const suffix = value && value !== name ? value : '';
        return {
          value,
          label: suffix ? `${name} (${suffix})` : name
        };
      }),
    [existingAssets]
  );

  const handleAccessTypeChange = (value: FlowAssetFormValues['accessType']) => {
    if (value === 'new') {
      form.setFieldsValue({
        organizations: selectedGroup?.id ? [Number(selectedGroup.id)] : undefined,
        fallback_sampling_rate: FALLBACK_SAMPLING_RATE_DEFAULT
      });
    }
  };

  const handleExistingAssetChange = (value: string) => {
    const selectedAsset = existingAssetMap[String(value)];
    form.setFieldsValue({
      instance_id: value,
      name: selectedAsset?.instance_name || selectedAsset?.name,
      cloud_region_id: selectedAsset?.cloud_region_id,
      ip: selectedAsset?.ip,
      organizations: selectedAsset?.organizations,
      fallback_sampling_rate: selectedAsset?.fallback_sampling_rate
    });
  };

  const handleSubmit = async () => {
    try {
      setSubmitLoading(true);
      const values = await form.validateFields();
      const result = await createFlowAsset({
        protocol,
        monitor_object_id: objectId!,
        cloud_region_id: values.cloud_region_id!,
        ip: values.ip!,
        name: values.name!,
        fallback_sampling_rate:
          values.fallback_sampling_rate ?? FALLBACK_SAMPLING_RATE_DEFAULT,
        organizations: values.organizations || [],
        instance_id:
          values.accessType === 'existing' ? values.instance_id : undefined
      });

      onNext({
        accessType: values.accessType,
        instance_id: result?.instance_id || values.instance_id || '',
        cloud_region_id: values.cloud_region_id!,
        ip: values.ip!,
        name: values.name!,
        organizations: values.organizations || [],
        fallback_sampling_rate:
          values.fallback_sampling_rate ?? FALLBACK_SAMPLING_RATE_DEFAULT,
        enabled_protocols: result?.enabled_protocols
      });
    } catch (error: any) {
      if (error?.errorFields) {
        return;
      }
      message.error(error?.message || t('common.operationFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <div className="p-0">
      <Alert
        className="mb-6"
        showIcon
        type="info"
        message={t('monitor.integrations.flow.assetTipTitle')}
        description={t('monitor.integrations.flow.assetTipDesc', undefined, {
          protocol: protocolLabelMap[protocol]
        })}
      />

      <Form
        form={form}
        layout="vertical"
        className="w-full"
        initialValues={{
          accessType: 'new',
          fallback_sampling_rate: FALLBACK_SAMPLING_RATE_DEFAULT
        }}
      >
        <div className="flex items-center mb-6">
          <InfoCircleOutlined className="text-lg mr-2" />
          <h3 className="text-base font-semibold">
            {t('monitor.integrations.flow.accessAsset')}
          </h3>
        </div>

        <Form.Item label={t('monitor.integrations.flow.accessAsset')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="accessType"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Radio.Group
                style={{ width: FORM_CONTROL_WIDTH }}
                onChange={(event) =>
                  handleAccessTypeChange(
                    event.target.value as FlowAssetFormValues['accessType']
                  )
                }
              >
                <Radio value="new">{t('monitor.integrations.flow.newAsset')}</Radio>
                <Radio value="existing">
                  {t('monitor.integrations.flow.existingAsset')}
                </Radio>
              </Radio.Group>
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('monitor.integrations.flow.accessAssetDesc')}
            </div>
          </div>
        </Form.Item>

        {accessType === 'existing' && (
          <Form.Item label={t('monitor.integrations.flow.existingAsset')} required>
            <div className="flex items-start gap-4">
              <Form.Item
                name="instance_id"
                noStyle
                rules={[{ required: true, message: t('common.required') }]}
              >
                <Select
                  loading={assetLoading}
                  options={assetOptions}
                  placeholder={t('monitor.integrations.flow.selectExistingAsset')}
                  onChange={handleExistingAssetChange}
                  style={{ width: FORM_CONTROL_WIDTH }}
                />
              </Form.Item>
              <div className="text-[var(--color-text-3)] flex-1">
                {t('monitor.integrations.flow.existingAssetDesc')}
              </div>
            </div>
          </Form.Item>
        )}

        {accessType === 'existing' && (
          <Alert
            className="mb-6"
            showIcon
            type="info"
            message={t('monitor.integrations.flow.existingAssetReviewNoticeTitle')}
            description={t('monitor.integrations.flow.existingAssetReviewNoticeDesc')}
          />
        )}

        <Form.Item label={t('monitor.integrations.flow.cloudRegion')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="cloud_region_id"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Select
                style={{ width: FORM_CONTROL_WIDTH }}
                loading={cloudRegionLoading}
                placeholder={t('monitor.integrations.flow.selectCloudRegion')}
                options={cloudRegionList.map((item) => ({
                  value: item.id,
                  label: item.name
                }))}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t(
                accessType === 'existing'
                  ? 'monitor.integrations.flow.existingAssetReviewDesc'
                  : 'monitor.integrations.flow.cloudRegionDesc'
              )}
            </div>
          </div>
        </Form.Item>

        <Form.Item label={t('monitor.integrations.flow.assetIp')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="ip"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input
                placeholder={t('common.inputTip')}
                style={{ width: FORM_CONTROL_WIDTH }}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t(
                accessType === 'existing'
                  ? 'monitor.integrations.flow.existingAssetReviewDesc'
                  : 'monitor.integrations.flow.assetIpDesc'
              )}
            </div>
          </div>
        </Form.Item>

        <Form.Item label={t('monitor.integrations.flow.assetName')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="name"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input
                placeholder={t('common.inputTip')}
                style={{ width: FORM_CONTROL_WIDTH }}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t('monitor.integrations.flow.assetNameDesc')}
            </div>
          </div>
        </Form.Item>

        <Form.Item label={t('monitor.integrations.flow.organization')} required>
          <div className="flex items-start gap-4">
            <Form.Item
              name="organizations"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <GroupTreeSelector
                style={{ width: FORM_CONTROL_WIDTH }}
                placeholder={t('common.selectTip')}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t(
                accessType === 'existing'
                  ? 'monitor.integrations.flow.existingAssetReviewDesc'
                  : 'monitor.integrations.flow.organizationDesc'
              )}
            </div>
          </div>
        </Form.Item>

        <Form.Item
          label={t('monitor.integrations.flow.fallbackSamplingRate')}
          required
        >
          <div className="flex items-start gap-4">
            <Form.Item
              name="fallback_sampling_rate"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <InputNumber
                min={0}
                precision={0}
                style={{ width: FORM_CONTROL_WIDTH }}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] flex-1">
              {t(
                accessType === 'existing'
                  ? 'monitor.integrations.flow.existingAssetReviewDesc'
                  : 'monitor.integrations.flow.fallbackSamplingRateDesc'
              )}
            </div>
          </div>
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

export default AccessAsset;
