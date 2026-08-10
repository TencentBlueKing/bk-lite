'use client';

import React, { useEffect, useRef } from 'react';
import { Form, Spin } from 'antd';

import { PLATFORM_API_FORM_INITIAL_VALUES } from '@/app/cmdb/constants/professCollection';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import type { ModelItem, TreeNode } from '@/app/cmdb/types/autoDiscovery';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';

import { getCleanupFormValues, useTaskForm } from '../hooks/useTaskForm';
import { formatTaskValues, normalizeCredentialPool } from '../hooks/formatTaskValues';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import CredentialPoolEditor from './credentialPoolEditor';
import { buildPlatformApiCredentialHelp } from './credentialHelp';
import {
  buildPlatformApiCredential,
  createPlatformApiCredential,
  restorePlatformApiCredential,
  validatePlatformApiCredential,
} from './platformApiCredential';

interface PlatformApiTaskProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

/**
 * FusionInsight / OceanStor / 华三 UIS / 深信服 等平台 HTTPS 采集。
 * task_type=cloud → BaseTask 走与 VCenter/公有云相同的单资产 instId 选择，
 * 因此 instances 必须从 instOptions 解析，不能走 IP/selectedData 路径。
 */
const PlatformApiTask: React.FC<PlatformApiTaskProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const collectionFormLayout = useCollectionFormLayout();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const { copyTaskData, setCopyTaskData } = useAssetManageStore();
  const modelId = modelItem.model_id;
  const initialValues = {
    ...PLATFORM_API_FORM_INITIAL_VALUES,
    credentialPool: [createPlatformApiCredential(modelId)],
  };

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
    initialValues,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const baseData = formatTaskValues({
        values,
        baseRef,
        selectedNode,
        modelItem,
        modelId,
        formatCycleValue,
      });
      const instance = baseRef.current?.instOptions?.find(
        (item: any) => item.value === values.instId,
      );
      const credential = normalizeCredentialPool(values.credentialPool)[0]
        || createPlatformApiCredential(modelId);

      return {
        ...baseData,
        instances: instance?.origin ? [instance.origin] : [],
        credential: [buildPlatformApiCredential(modelId, credential)],
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    accessPointId: values.access_point?.[0]?.id,
    instId: values.instances?.[0]?._id,
    credentialPool: [
      restorePlatformApiCredential(
        modelId,
        normalizeCredentialPool(values.credential)[0]
          || createPlatformApiCredential(modelId),
        isCopy,
        values.instances?.[0]?.endpoint
          || values.instances?.[0]?.ip_addr
          || values.instances?.[0]?.host,
      ),
    ],
  });

  useEffect(() => {
    const initForm = async () => {
      const values = copyTaskData || (editId ? await fetchTaskDetail(editId) : null);
      if (!values) {
        form.setFieldsValue(initialValues);
        return;
      }
      form.setFieldsValue(buildFormValues(values, Boolean(copyTaskData)));
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  const validateCredential = (_: unknown, value: any[]) => {
    const credential = normalizeCredentialPool(value)[0]
      || createPlatformApiCredential(modelId);
    const invalidField = validatePlatformApiCredential(credential);
    if (!invalidField) {
      return Promise.resolve();
    }
    const label = invalidField === 'username'
      ? t('user')
      : invalidField === 'password'
        ? t('password')
        : t('Collection.port');
    return Promise.reject(new Error(t('common.inputMsg') + label));
  };

  return (
    <Spin spinning={loading}>
      <Form {...collectionFormLayout} form={form} onFinish={onFinish} initialValues={initialValues}>
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={t('Collection.chooseAsset')}
          timeoutProps={{
            min: 1,
            defaultValue: PLATFORM_API_FORM_INITIAL_VALUES.timeout,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item
            name="credentialPool"
            rules={[{ validator: validateCredential }]}
            validateTrigger={[]}
          >
            <CredentialPoolEditor
              credentialShape="platform_api"
              editMode={Boolean(editId)}
              maxCount={1}
              allowAdd={false}
              allowRemove={false}
              showCount={false}
              credentialHelp={buildPlatformApiCredentialHelp(modelId, t)}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default PlatformApiTask;
