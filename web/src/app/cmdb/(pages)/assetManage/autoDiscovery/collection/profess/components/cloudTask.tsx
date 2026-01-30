'use client';

import React, { useEffect, useRef, useState } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import styles from '../index.module.scss';
import { useCollectApi } from '@/app/cmdb/api';
import { CaretRightOutlined, SyncOutlined } from '@ant-design/icons';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { Form, Spin, Input, Collapse, Select, message } from 'antd';
import {
  CLOUD_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';

interface RegionItem {
  cloud_type: string;
  resource_id: string;
  resource_name: string;
  desc: string;
  tag: any[];
  extra: {
    RegionEndpoint: string;
  };
  status: string;
}

interface cloudTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

interface RegionSelectProps {
  value?: string;
  onChange?: (value: string) => void;
  loading?: boolean;
  options?: { label: string; value: string }[];
  onRefresh: () => void;
}

const CloudTask: React.FC<cloudTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const localeContext = useLocale();
  const { model_id: modelId } = modelItem;
  const [regions, setRegions] = useState<RegionItem[]>([]);
  const [loadingRegions, setLoadingRegions] = useState(false);
  const collectApi = useCollectApi();

  const {
    form,
    loading,
    submitLoading,
    fetchTaskDetail,
    formatCycleValue,
    onFinish,
  } = useTaskForm({
    modelId,
    editId,
    initialValues: CLOUD_FORM_INITIAL_VALUES,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const regionItem = regions.find(
        (item: any) => item.resource_id === values.regionId
      );

      const baseData = formatTaskValues({
        values,
        baseRef,
        selectedNode,
        modelItem,
        modelId,
        formatCycleValue,
      });

      const instance = baseRef.current?.instOptions?.find(
        (item: any) => item.value === values.instId
      );

      const credential: any = {
        regions: regionItem,
      };

      if (values.accessKey && values.accessKey !== PASSWORD_PLACEHOLDER) {
        credential.accessKey = values.accessKey;
      }

      if (values.accessSecret && values.accessSecret !== PASSWORD_PLACEHOLDER) {
        credential.accessSecret = values.accessSecret;
      }

      return {
        ...baseData,
        instances: instance?.origin && [instance.origin],
        credential,
      };
    },
  });

  const fetchRegions = async (
    accessKey: string,
    accessSecret: string,
    cloudRegionId: string,
    refreshFlag = true,
  ) => {
    if (!accessKey || !accessSecret) return;
    setLoadingRegions(true);
    try {
      const data = await collectApi.getCollectRegions({
        model_id: modelId,
        access_key: accessKey,
        access_secret: accessSecret,
        cloud_id: cloudRegionId,
      });
      setRegions(data || []);
      if (refreshFlag) {
        message.success(t('common.updateSuccess'));
      }
    } catch (error) {
      console.error('获取regions失败:', error);
    } finally {
      setLoadingRegions(false);
    }
  };

  const handleRefreshRegions = async (refreshFlag = false) => {
    const values = form.getFieldsValue([
      'accessKey',
      'accessSecret',
      'accessPointId',
    ]);
    if (!values.accessKey || !values.accessSecret) {
      const msg = !values.accessKey
        ? t('Collection.cloudTask.accessKey')
        : t('Collection.cloudTask.accessSecret');
      message.error(t('common.inputMsg') + msg);
      return;
    }
    if (!values.accessPointId) {
      message.error(t('common.selectTip') + t('Collection.accessPoint'));
      return;
    }

    const selectedAccessPoint = baseRef.current?.accessPoints?.find(
      (item: any) => item.value === values.accessPointId,
    );
    const cloudRegion = selectedAccessPoint?.origin?.cloud_region || '';

    await fetchRegions(
      values.accessKey,
      values.accessSecret,
      cloudRegion,
      refreshFlag,
    );
  };

  const handleCredentialChange = () => {
    setRegions([]);
    form.setFieldValue('region', undefined);
  };

  useEffect(() => {
    const initForm = async () => {
      if (editId) {
        const values = await fetchTaskDetail(editId);
        const regions = values.credential?.regions || [];
        form.setFieldsValue({
          ...values,
          accessKey: PASSWORD_PLACEHOLDER,
          accessSecret: PASSWORD_PLACEHOLDER,
          regionId: regions?.resource_id,
          organization: values.team || [],
          accessPointId: values.access_point?.[0]?.id,
        });
        handleRefreshRegions(false);
      } else {
        form.setFieldsValue(CLOUD_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId]);

  const RegionSelect: React.FC<RegionSelectProps> = ({
    value,
    loading,
    options,
    onChange,
    onRefresh,
  }) => (
    <div className="flex items-center gap-2">
      <Select
        value={value}
        onChange={onChange}
        className="flex-1"
        loading={loading}
        placeholder={t('common.selectTip')}
        options={options}
      />
      <SyncOutlined
        spin={loading}
        className="cursor-pointer"
        onClick={onRefresh}
      />
    </div>
  );

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }}
        onFinish={onFinish}
        initialValues={CLOUD_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('Collection.cloudTask.cloudAccount')}`}
          timeoutProps={{
            min: 0,
            defaultValue: 600,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Collapse
            ghost
            defaultActiveKey={['credential']}
            expandIcon={({ isActive }) => (
              <CaretRightOutlined
                rotate={isActive ? 90 : 0}
                className="text-base"
              />
            )}
          >
            <Collapse.Panel
              header={
                <div className={styles.panelHeader}>
                  {t('Collection.credential')}
                </div>
              }
              key="credential"
            >
              <Form.Item
                label={t('Collection.cloudTask.accessKey')}
                name="accessKey"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <Input
                  placeholder={t('common.inputTip')}
                  onChange={handleCredentialChange}
                  onFocus={(e) => {
                    if (!editId) return;
                    const value = e.target.value;
                    if (value === PASSWORD_PLACEHOLDER) {
                      form.setFieldValue('accessKey', '');
                    }
                  }}
                  onBlur={(e) => {
                    if (!editId) return;
                    const value = e.target.value;
                    if (!value || value.trim() === '') {
                      form.setFieldValue('accessKey', PASSWORD_PLACEHOLDER);
                    }
                  }}
                />
              </Form.Item>

              <Form.Item
                label={t('Collection.cloudTask.accessSecret')}
                name="accessSecret"
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <Input.Password
                  placeholder={t('common.inputTip')}
                  onChange={handleCredentialChange}
                  onFocus={(e) => {
                    if (!editId) return;
                    const value = e.target.value;
                    if (value === PASSWORD_PLACEHOLDER) {
                      form.setFieldValue('accessSecret', '');
                    }
                  }}
                  onBlur={(e) => {
                    if (!editId) return;
                    const value = e.target.value;
                    if (!value || value.trim() === '') {
                      form.setFieldValue('accessSecret', PASSWORD_PLACEHOLDER);
                    }
                  }}
                />
              </Form.Item>

              <Form.Item
                label={t('Collection.cloudTask.region')}
                name="regionId"
                rules={[{ required: true, message: t('common.selectTip') }]}
              >
                <RegionSelect
                  loading={loadingRegions}
                  onRefresh={handleRefreshRegions}
                  options={regions.map((item) => ({
                    label: item.resource_name,
                    value: item.resource_id,
                  }))}
                />
              </Form.Item>
            </Collapse.Panel>
          </Collapse>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default CloudTask;
