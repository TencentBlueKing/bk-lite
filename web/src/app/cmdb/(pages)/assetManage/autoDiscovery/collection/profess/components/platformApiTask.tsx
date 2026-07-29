'use client';

import React, { useEffect, useRef } from 'react';
import { Form, Spin } from 'antd';

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
    credentialPool: [createPlatformApiCredential(modelId)],
    timeout: 60,
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
      const collectType = baseRef.current?.collectionType;
      const ipRange = values.ipRange?.length ? values.ipRange : [];
      const credential = normalizeCredentialPool(values.credentialPool)[0]
        || createPlatformApiCredential(modelId);

      return {
        ...baseData,
        ip_range: collectType === 'ip' ? ipRange.join('-') : '',
        instances: collectType === 'ip'
          ? []
          : baseRef.current?.selectedData || [],
        credential: [buildPlatformApiCredential(modelId, credential)],
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean, ipRange?: string[]) => ({
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    accessPointId: values.access_point?.[0]?.id,
    ipRange,
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
      const ipRange = values.ip_range?.split('-');
      if (values.ip_range?.length) {
        baseRef.current?.initCollectionType(ipRange, 'ip');
      } else {
        baseRef.current?.initCollectionType(values.instances, 'asset');
      }
      form.setFieldsValue(buildFormValues(values, Boolean(copyTaskData), ipRange));
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
            defaultValue: 60,
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
