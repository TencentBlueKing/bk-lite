'use client';

import React, { useEffect, useRef, useState } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useCollectApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { getCleanupFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { Form, Spin, message } from 'antd';
import {
  CLOUD_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import { formatTaskValues, normalizeCredentialPool, trimFormString } from '../hooks/formatTaskValues';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import CredentialPoolEditor from './credentialPoolEditor';

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

const CloudTask: React.FC<cloudTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const { model_id: modelId } = modelItem;
  const [regions, setRegions] = useState<RegionItem[]>([]);
  const [loadingRegions, setLoadingRegions] = useState(false);
  const collectApi = useCollectApi();
  const { copyTaskData, setCopyTaskData } = useAssetManageStore();

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
      const credentialValue = normalizeCredentialPool(values.credentialPool)[0] || {};
      const accessKey = trimFormString(credentialValue.accessKey);
      const accessSecret = trimFormString(credentialValue.accessSecret);
      const regionItem = regions.find(
        (item: any) => item.resource_id === credentialValue.regionId
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

      if (accessKey && accessKey !== PASSWORD_PLACEHOLDER) {
        credential.accessKey = accessKey;
      }

      if (accessSecret && accessSecret !== PASSWORD_PLACEHOLDER) {
        credential.accessSecret = accessSecret;
      }

      return {
        ...baseData,
        instances: instance?.origin && [instance.origin],
        credential,
      };
    },
  });

  // 构建表单值，用于复制任务和编辑任务中回填表单数据（true:复制任务，false:编辑任务）
  const buildFormValues = (values: any, isCopy: boolean) => {
    const regionItem = values.credential?.regions;
    return {
      ...getCleanupFormValues(values),
      ...values,
      taskName: isCopy ? '' : values.name,
      credentialPool: [{
        accessKey: isCopy ? values.credential?.accessKey : PASSWORD_PLACEHOLDER,
        accessSecret: isCopy ? '' : PASSWORD_PLACEHOLDER,
        regionId: regionItem?.resource_id,
        regionName: regionItem?.resource_name,
      }],
      organization: values.team || [],
      timeout: values.timeout,
      instId: values.instances?.[0]?._id,
      accessPointId: values.access_point?.[0]?.id,
    };
  };

  const fetchRegions = async (
    accessKey: string,
    accessSecret: string,
    cloudRegionId: string,
    refreshFlag = true,
    host?: string
  ) => {
    if (!accessKey || !accessSecret || !cloudRegionId) return;
    setLoadingRegions(true);
    try {
      const isCredentialUnchanged =
        accessKey === PASSWORD_PLACEHOLDER && accessSecret === PASSWORD_PLACEHOLDER;

      const params: any = {
        model_id: modelId,
        cloud_id: cloudRegionId,
      };

      if (host) {
        params.host = host;
      }

      if (editId && isCredentialUnchanged) {
        params.task_id = editId;
      } else {
        params.access_key = accessKey;
        params.access_secret = accessSecret;
      }

      const data = await collectApi.getCollectRegions(params);
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
    const rawValues = form.getFieldsValue(['credentialPool', 'accessPointId']);
    const credentialValue = normalizeCredentialPool(rawValues.credentialPool)[0] || {};
    const values = {
      ...rawValues,
      accessKey: trimFormString(credentialValue.accessKey),
      accessSecret: trimFormString(credentialValue.accessSecret),
    };

    form.setFieldValue('credentialPool', [{
      ...credentialValue,
      accessKey: values.accessKey,
      accessSecret: values.accessSecret,
    }]);

    const isAccessKeyPlaceholder = values.accessKey === PASSWORD_PLACEHOLDER;
    const isAccessSecretPlaceholder = values.accessSecret === PASSWORD_PLACEHOLDER;
    const isCredentialUnchanged =
      isAccessKeyPlaceholder && isAccessSecretPlaceholder;
    const hasMixedCredentialState =
      isAccessKeyPlaceholder !== isAccessSecretPlaceholder;

    if (hasMixedCredentialState) {
      message.error(
        `${t('common.inputMsg')}${t('Collection.cloudTask.accessKey')} / ${t('Collection.cloudTask.accessSecret')}`
      );
      return;
    }

    if ((!values.accessKey || !values.accessSecret) && !isCredentialUnchanged) {
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

    const instId = form.getFieldValue('instId');
    const instOption = baseRef.current?.instOptions?.find((item: any) => item.value === instId);
    const host = instOption?.origin?.endpoint || undefined;

    await fetchRegions(
      values.accessKey,
      values.accessSecret,
      cloudRegion,
      refreshFlag,
      host,
    );
  };

  const handleCredentialChange = () => {
    setRegions([]);
  };

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const values = copyTaskData;
        const regionItem = normalizeCredentialPool(values.credential)[0]?.regions;

        // 复制任务中回填表单数据（此时任务名称和密码为空，需要用户手动输入）
        form.setFieldsValue(buildFormValues(values, true));
        setRegions(regionItem ? [regionItem] : []);
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        const regionItem = values.credential?.regions;

        // 编辑任务中回填表单数据
        form.setFieldsValue(buildFormValues(values, false));
        setRegions(regionItem ? [regionItem] : []);

        const cloudRegion = values.access_point?.[0]?.cloud_region || '';
        if (cloudRegion) {
          fetchRegions(PASSWORD_PLACEHOLDER, PASSWORD_PLACEHOLDER, cloudRegion, false, values.instances?.[0]?.endpoint || undefined);
        }
      } else {
        form.setFieldsValue({
          ...CLOUD_FORM_INITIAL_VALUES,
          credentialPool: [{ accessKey: '', accessSecret: '', regionId: '' }],
        });
      }
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  const validateCredentialPool = (_: any, value?: any[]) => {
    const credentialValue = normalizeCredentialPool(value)[0] || {};
    if (!trimFormString(credentialValue.accessKey)) {
      return Promise.reject(new Error(t('common.inputMsg') + t('Collection.cloudTask.accessKey')));
    }
    if (!trimFormString(credentialValue.accessSecret)) {
      return Promise.reject(new Error(t('common.inputMsg') + t('Collection.cloudTask.accessSecret')));
    }
    if (!credentialValue.regionId) {
      return Promise.reject(new Error(t('common.selectTip') + t('Collection.cloudTask.region')));
    }
    return Promise.resolve();
  };

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="vertical"
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
          <Form.Item
            name="credentialPool"
            rules={[{ validator: validateCredentialPool }]}
            validateTrigger={[]}
          >
            <CredentialPoolEditor
              credentialShape="cloud"
              editMode={Boolean(editId)}
              maxCount={1}
              allowAdd={false}
              allowRemove={false}
              showCount={false}
              cloudRegionLoading={loadingRegions}
              cloudRegionOptions={regions.map((item) => ({
                label: item.resource_name,
                value: item.resource_id,
              }))}
              onCloudRegionRefresh={() => handleRefreshRegions()}
              onCredentialFieldChange={handleCredentialChange}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default CloudTask;
