'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { getCleanupFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { Form, Spin } from 'antd';

import {
  ENTER_TYPE,
  VM_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import { formatTaskValues, normalizeCredentialPool, trimFormString } from '../hooks/formatTaskValues';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import CredentialPoolEditor from './credentialPoolEditor';

interface VMTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const VMTask: React.FC<VMTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const localeContext = useLocale();
  const { copyTaskData, setCopyTaskData } = useAssetManageStore();
  const { model_id: modelId } = modelItem;

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
    initialValues: VM_FORM_INITIAL_VALUES,
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
        (item: any) => item.value === values.instId
      );

      const credentialValue = normalizeCredentialPool(values.credentialPool)[0] || {};
      const password = trimFormString(credentialValue.password);

      const credential: any = {
        username: trimFormString(credentialValue.username),
        port: credentialValue.port,
        ssl: credentialValue.ssl,
      };

      if (password && password !== PASSWORD_PLACEHOLDER) {
        credential.password = password;
      }

      return {
        ...baseData,
        instances: instance?.origin && [instance.origin],
        credential,
      };
    },
  });

  // 构建表单值，用于复制任务和编辑任务中回填表单数据（true:复制任务，false:编辑任务）
  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    enterType:
      values.input_method === 0 ? ENTER_TYPE.AUTOMATIC : ENTER_TYPE.APPROVAL,
    accessPointId: values.access_point?.[0]?.id,
    organization: values.team || [],
    credentialPool: [{
      username: values.credential?.username,
      password: isCopy ? '' : PASSWORD_PLACEHOLDER,
      port: values.credential?.port || '443',
      ssl: values.credential?.ssl,
    }],
    instId: values.instances?.[0]?._id,
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const values = copyTaskData;

        // 复制任务中回填表单数据（此时任务名称和密码为空，需要用户手动输入）
        form.setFieldsValue(buildFormValues(values, true));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);

        // 编辑任务中回填表单数据
        form.setFieldsValue(buildFormValues(values, false));
      } else {
        form.setFieldsValue({
          ...VM_FORM_INITIAL_VALUES,
          credentialPool: [{ port: '443', ssl: false }],
        });
      }
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  const validateCredentialPool = (_: any, value?: any[]) => {
    const credentialValue = normalizeCredentialPool(value)[0] || {};
    if (!trimFormString(credentialValue.username)) {
      return Promise.reject(new Error(`${t('common.inputMsg')}${t('Collection.VMTask.username')}`));
    }
    if (!trimFormString(credentialValue.password)) {
      return Promise.reject(new Error(`${t('common.inputMsg')}${t('Collection.VMTask.password')}`));
    }
    if (!credentialValue.port) {
      return Promise.reject(new Error(`${t('common.inputMsg')}${t('Collection.port')}`));
    }
    return Promise.resolve();
  };

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }}
        onFinish={onFinish}
        initialValues={VM_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('common.select')} ${t('Collection.VMTask.chooseVCenter')}`}
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
              credentialShape="vm"
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

export default VMTask;
