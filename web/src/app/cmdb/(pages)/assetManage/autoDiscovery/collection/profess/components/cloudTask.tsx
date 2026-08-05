'use client';

import React, { useEffect, useRef, useState } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useCollectApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
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
import {
  buildCloudCredential,
  getCloudCredentialConfig,
  restoreCloudCredential,
  validateCloudCredential,
} from './cloudCredentialConfig';
import { buildCloudCredentialHelp } from './credentialHelp';

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
  const collectionFormLayout = useCollectionFormLayout();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const { model_id: modelId } = modelItem;
  const cloudCredentialConfig = getCloudCredentialConfig(modelId);
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

      const credential = buildCloudCredential(
        modelId,
        {
          ...credentialValue,
          accessKey,
          accessSecret,
        },
        regionItem,
      );

      return {
        ...baseData,
        instances: instance?.origin && [instance.origin],
        credential,
      };
    },
  });

  // 构建表单值，用于复制任务和编辑任务中回填表单数据（true:复制任务，false:编辑任务）
  const buildFormValues = (values: any, isCopy: boolean) => {
    return {
      ...getCleanupFormValues(values),
      ...values,
      taskName: isCopy ? '' : values.name,
      credentialPool: [
        restoreCloudCredential(modelId, values.credential || {}, isCopy),
      ],
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
    host?: string,
    projectId?: string,
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
      if (projectId) {
        params.project_id = projectId;
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
      projectId: trimFormString(credentialValue.projectId),
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
    if (
      cloudCredentialConfig.requiresProjectId
      && !trimFormString(values.projectId)
    ) {
      message.error(
        t('common.inputMsg') + t('Collection.cloudTask.projectId'),
      );
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
      values.projectId,
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
        const credentialItem = normalizeCredentialPool(values.credential)[0];
        const regionItem = credentialItem?.regions;

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
    const invalidField = validateCloudCredential(modelId, credentialValue);
    if (invalidField) {
      const label = invalidField === 'accessKey'
        ? t(cloudCredentialConfig.accessKeyLabelKey)
        : invalidField === 'accessSecret'
          ? t(cloudCredentialConfig.accessSecretLabelKey)
          : invalidField === 'projectId'
            ? t('Collection.cloudTask.projectId')
            : t('Collection.cloudTask.region');
      const prefix = invalidField === 'regionId'
        ? t('common.selectTip')
        : t('common.inputMsg');
      return Promise.reject(new Error(prefix + label));
    }
    return Promise.resolve();
  };

  return (
    <Spin spinning={loading}>
      <Form
        {...collectionFormLayout}
        form={form}
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
              cloudCredentialLabels={{
                accessKey: t(cloudCredentialConfig.accessKeyLabelKey),
                accessSecret: t(cloudCredentialConfig.accessSecretLabelKey),
                ...(cloudCredentialConfig.requiresProjectId
                  ? { projectId: t('Collection.cloudTask.projectId') }
                  : {}),
              }}
              credentialHelp={buildCloudCredentialHelp(modelId, t)}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default CloudTask;
