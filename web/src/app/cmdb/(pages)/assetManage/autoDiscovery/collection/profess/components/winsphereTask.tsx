'use client';

import React, { useEffect, useRef } from 'react';
import { Form, Spin } from 'antd';

import {
  CYCLE_OPTIONS,
  ENTER_TYPE,
} from '@/app/cmdb/constants/professCollection';
import { ModelItem, TreeNode } from '@/app/cmdb/types/autoDiscovery';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import { useTranslation } from '@/utils/i18n';

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

interface WinSphereTaskProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.INTERVAL,
  intervalValue: 30,
  enterType: ENTER_TYPE.AUTOMATIC,
  timeout: 600,
  cleanupStrategy: 'no_cleanup',
  cleanupDays: 3,
  credentialPool: [createWinSphereCredential()],
};

const WinSphereTask: React.FC<WinSphereTaskProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const { copyTaskData, setCopyTaskData } = useAssetManageStore();
  const modelId = modelItem.model_id;

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
    initialValues: INITIAL_VALUES,
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
        form.setFieldsValue(INITIAL_VALUES);
      }
    };
    initialize();
  }, [modelId, editId]);

  const validateCredential = (_: unknown, value?: any[]) => {
    const credential =
      normalizeCredentialPool(value)[0] || createWinSphereCredential();
    const invalidField = validateWinSphereCredential(credential);
    if (!invalidField) return Promise.resolve();
    const labels = {
      user: t('Collection.WinSphereTask.user', 'WinSphere账号'),
      password: t('Collection.WinSphereTask.password', '密码'),
      https_port: t('Collection.WinSphereTask.httpsPort', 'HTTPS端口'),
      verify_tls: t('Collection.WinSphereTask.verifyTls', 'TLS证书校验'),
    };
    return Promise.reject(
      new Error(`${t('common.inputMsg')}${labels[invalidField]}`),
    );
  };

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        initialValues={INITIAL_VALUES}
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
