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
import { buildInfluxdbCredentialHelp } from './credentialHelp';
import {
  buildInfluxdbTarget,
  buildInfluxdbCredential,
  createInfluxdbCredential,
  restoreInfluxdbCredential,
  validateInfluxdbCredential,
} from './influxdbCredential';

interface InfluxdbTaskProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const InfluxdbTask: React.FC<InfluxdbTaskProps> = ({
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
    credentialPool: [createInfluxdbCredential()],
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
      const credential = normalizeCredentialPool(values.credentialPool)[0]
        || createInfluxdbCredential();
      const target = buildInfluxdbTarget(
        values.instId,
        baseRef.current?.instOptions || [],
      );

      return {
        ...baseData,
        ...target,
        credential: [buildInfluxdbCredential(credential)],
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean, ipRange?: string[]) => ({
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    accessPointId: values.access_point?.[0]?.id,
    instId: values.instances?.[0]?._id,
    ipRange,
    credentialPool: [
      restoreInfluxdbCredential(
        normalizeCredentialPool(values.credential)[0] || createInfluxdbCredential(),
        isCopy,
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
    const credential = normalizeCredentialPool(value)[0] || createInfluxdbCredential();
    const invalidField = validateInfluxdbCredential(credential);
    if (invalidField) {
      return Promise.reject(
        new Error(
          invalidField === 'scheme'
            ? t('Collection.influxdbTask.invalidScheme', '请选择 HTTP 或 HTTPS')
            : t('Collection.influxdbTask.invalidPort', '请输入 1–65535 的有效端口'),
        ),
      );
    }
    return Promise.resolve();
  };

  // Operator Token 是可选的；填写后才会读取 /api/v2/config。
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
          singleInstanceOnly
        >
          <Form.Item
            name="credentialPool"
            rules={[{ validator: validateCredential }]}
            validateTrigger={[]}
          >
            <CredentialPoolEditor
              credentialShape="influxdb"
              editMode={Boolean(editId)}
              maxCount={1}
              allowAdd={false}
              allowRemove={false}
              showCount={false}
              credentialHelp={buildInfluxdbCredentialHelp(t)}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default InfluxdbTask;
