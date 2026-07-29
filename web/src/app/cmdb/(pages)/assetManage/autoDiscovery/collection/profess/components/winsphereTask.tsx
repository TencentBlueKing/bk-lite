'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import { Form, Spin } from 'antd';

import {
  CYCLE_OPTIONS,
  ENTER_TYPE,
} from '@/app/cmdb/constants/professCollection';
import { ModelItem, TreeNode } from '@/app/cmdb/types/autoDiscovery';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';

import BaseTaskForm, { BaseTaskRef } from './baseTask';
import CredentialPoolEditor from './credentialPoolEditor';
import { getCleanupFormValues, useTaskForm } from '../hooks/useTaskForm';
import {
  formatTaskValues,
  normalizeCredentialPool,
} from '../hooks/formatTaskValues';
import {
  buildWinSphereCredential,
  createWinSphereCredential,
  restoreWinSphereCredential,
  validateWinSphereCredential,
} from './winsphereCredential';
import { resolveCredentialHelp } from './credentialHelp';

interface WinSphereTaskProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const BASE_INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.INTERVAL,
  intervalValue: 30,
  enterType: ENTER_TYPE.AUTOMATIC,
  timeout: 600,
  cleanupStrategy: 'no_cleanup',
  cleanupDays: 3,
};

const WinSphereTask: React.FC<WinSphereTaskProps> = ({
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
  const initialValues = useMemo(
    () => ({
      ...BASE_INITIAL_VALUES,
      credentialPool: [createWinSphereCredential()],
    }),
    [],
  );

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
      const credentialValue =
        normalizeCredentialPool(values.credentialPool)[0] || {};

      return {
        ...baseData,
        instances: instance?.origin && [instance.origin],
        credential: buildWinSphereCredential(credentialValue),
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    enterType:
      values.input_method === 0 ? ENTER_TYPE.AUTOMATIC : ENTER_TYPE.APPROVAL,
    accessPointId: values.access_point?.[0]?.id,
    organization: values.team || [],
    credentialPool: [
      restoreWinSphereCredential(values.credential, isCopy),
    ],
    instId: values.instances?.[0]?._id,
  });

  useEffect(() => {
    const initialize = async () => {
      if (copyTaskData) {
        form.setFieldsValue(buildFormValues(copyTaskData, true));
        setCopyTaskData(null);
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        form.setFieldsValue(buildFormValues(values, false));
      } else {
        form.setFieldsValue(initialValues);
      }
    };
    initialize();
  }, [modelId, editId]);

  const validateCredential = (_: unknown, value?: any[]) => {
    const credential =
      normalizeCredentialPool(value)[0]
      || createWinSphereCredential();
    const invalidField = validateWinSphereCredential(credential);
    if (!invalidField) return Promise.resolve();
    const fieldLabels = {
      user: t('Collection.WinSphereTask.user', 'WinSphere账号'),
      password: t('password', '密码'),
      https_port: t('Collection.WinSphereTask.httpsPort', 'HTTPS端口'),
      verify_tls: t('Collection.WinSphereTask.verifyTls', 'TLS证书校验'),
    };
    const label = fieldLabels[invalidField] || invalidField;
    return Promise.reject(
      new Error(`${t('common.inputMsg')}${label}`),
    );
  };

  return (
    <Spin spinning={loading}>
      <Form
        {...collectionFormLayout}
        form={form}
        onFinish={onFinish}
        initialValues={initialValues}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('common.select')} ${t(
            'Collection.WinSphereTask.platform',
            'WinSphere管理平台',
          )}`}
          timeoutProps={{
            min: 0,
            defaultValue: 600,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item
            name="credentialPool"
            rules={[{ validator: validateCredential }]}
            validateTrigger={[]}
          >
            <CredentialPoolEditor
              credentialShape="winsphere"
              credentialHelp={resolveCredentialHelp(modelItem, t)}
              editMode={Boolean(editId)}
              maxCount={1}
              allowAdd={false}
              allowRemove={false}
              showCount={false}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default WinSphereTask;
