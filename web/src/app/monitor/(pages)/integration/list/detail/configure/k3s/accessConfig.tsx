'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, Radio, Select } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import { useSearchParams } from 'next/navigation';
import GroupTreeSelector from '@/components/group-tree-select';
import useIntegrationApi from '@/app/monitor/api/integration';
import useMonitorApi from '@/app/monitor/api';
import { useTranslation } from '@/utils/i18n';
import type { K3sCommandData } from '@/app/monitor/types/integration';

interface AccessConfigProps {
  commandData: K3sCommandData | null;
  onNext: (data: K3sCommandData) => void;
}

const AccessConfig: React.FC<AccessConfigProps> = ({
  commandData,
  onNext,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const searchParams = useSearchParams();
  const objectId = Number(searchParams.get('id'));
  const [submitting, setSubmitting] = useState(false);
  const [cloudRegions, setCloudRegions] = useState<any[]>([]);
  const [clusters, setClusters] = useState<any[]>([]);
  const { getCloudRegionList, createK3sInstance, getK3sCommands } =
    useIntegrationApi();
  const { getInstanceList } = useMonitorApi();

  useEffect(() => {
    void getCloudRegionList({ page_size: -1 }).then((items) =>
      setCloudRegions(items || [])
    );
    void getInstanceList(objectId, { page_size: -1 }).then((result) =>
      setClusters(result?.results || [])
    );
  }, [getCloudRegionList, getInstanceList, objectId]);

  useEffect(() => {
    if (commandData) {
      form.setFieldsValue({
        accessType: 'existing',
        existingInstance: commandData.instance_id,
        cloud_region_id: commandData.cloud_region_id,
      });
    }
  }, [commandData, form]);

  const submit = async () => {
    setSubmitting(true);
    try {
      const values = await form.validateFields();
      let instanceId = values.existingInstance as string;
      if (values.accessType === 'new') {
        const created = await createK3sInstance({
          monitor_object_id: objectId,
          instance_id: uuidv4().replaceAll('-', ''),
          name: values.name,
          organizations: values.organizations || [],
        });
        instanceId = created.instance_id;
      }
      const commands = await getK3sCommands({
        instance_id: instanceId,
        cloud_region_id: values.cloud_region_id,
      });
      onNext({
        ...commands,
        monitor_object_id: objectId,
        instance_id: instanceId,
        cloud_region_id: values.cloud_region_id,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{ accessType: 'new' }}
      className="w-full"
    >
      <Form.Item name="accessType" label={t('monitor.integrations.k3s.accessAsset')}>
        <Radio.Group>
          <Radio value="new">{t('monitor.integrations.k3s.newAsset')}</Radio>
          <Radio value="existing">
            {t('monitor.integrations.k3s.existingAsset')}
          </Radio>
        </Radio.Group>
      </Form.Item>
      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) =>
          getFieldValue('accessType') === 'new' ? (
            <>
              <Form.Item
                name="name"
                label={t('monitor.integrations.k3s.clusterName')}
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="organizations"
                label={t('monitor.integrations.k3s.organization')}
                rules={[{ required: true }]}
              >
                <GroupTreeSelector />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="existingInstance"
              label={t('monitor.integrations.k3s.k3sCluster')}
              rules={[{ required: true }]}
            >
              <Select
                options={clusters.map((item) => ({
                  label: item.name,
                  value: item.id,
                }))}
              />
            </Form.Item>
          )
        }
      </Form.Item>
      <Form.Item
        name="cloud_region_id"
        label={t('monitor.integrations.k3s.cloudRegion')}
        rules={[{ required: true }]}
      >
        <Select
          options={cloudRegions.map((item) => ({
            label: item.name,
            value: item.id,
          }))}
        />
      </Form.Item>
      <Button type="primary" loading={submitting} onClick={submit}>
        {t('common.next')}
      </Button>
    </Form>
  );
};

export default AccessConfig;
