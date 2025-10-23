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
  ENTER_TYPE,
  CLOUD_FORM_INITIAL_VALUES,
} from '@/app/cmdb/constants/professCollection';

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
  const baseRef = useRef<BaseTaskRef>(null);
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
      const instance = baseRef.current?.instOptions.find(
        (item: any) => item.value === values.instId
      );
      const driverType = selectedNode.tabItems?.find(
        (item) => item.model_id === modelId
      )?.type;

      const accessPoint = baseRef.current?.accessPoints.find(
        (item: any) => item.value === values.accessPointId
      );

      const regionItem = regions.find(
        (item: any) => item.resource_id === values.regionId
      );

      return {
        name: values.taskName,
        instances: instance?.origin && [instance.origin],
        input_method: values.enterType === ENTER_TYPE.APPROVAL ? 1 : 0,
        access_point: accessPoint?.origin && [accessPoint.origin],
        timeout: values.timeout || 600,
        scan_cycle: formatCycleValue(values),
        model_id: modelId,
        driver_type: driverType,
        task_type: modelItem.task_type,
        accessPointId: values.access_point?.[0]?.id,
        credential: {
          accessKey: values.accessKey,
          accessSecret: values.accessSecret,
          regions: regionItem,
        },
      };
    },
  });

  const fetchRegions = async (
    accessKey: string,
    accessSecret: string,
    refreshFlag = true
  ) => {
    if (!accessKey || !accessSecret) return;
    setLoadingRegions(true);
    try {
      const res = await collectApi.getCollectRegions({
        model_id: modelId,
        access_key: accessKey,
        access_secret: accessSecret,
      });
      if (res.result) {
        setRegions(res.data);
      }
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
    const values = form.getFieldsValue(['accessKey', 'accessSecret']);
    if (!values.accessKey || !values.accessSecret) {
      const msg = !values.accessKey
        ? t('Collection.cloudTask.accessKey')
        : t('Collection.cloudTask.accessSecret');
      message.error(t('common.inputMsg') + msg);
      return;
    }
    await fetchRegions(values.accessKey, values.accessSecret, refreshFlag);
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
          ...values.credential,
          regionId: regions?.resource_id,
          organization: values.params?.organization,
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
