'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useTranslation } from '@/utils/i18n';
import { Form, Spin } from 'antd';
import { getCycleFormValues, useTaskForm } from '../hooks/useTaskForm';
import { K8S_FORM_INITIAL_VALUES } from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';

interface K8sTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const K8sTaskForm: React.FC<K8sTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const { model_id: modelId } = modelItem;
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
    initialValues: K8S_FORM_INITIAL_VALUES,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const instance = baseRef.current?.instOptions?.find(
        (item: any) => item.value === values.instId
      );

      return {
        ...formatTaskValues({
          values,
          baseRef,
          selectedNode,
          modelItem,
          modelId,
          formatCycleValue,
        }),
        instances: instance?.origin && [instance.origin],
        input_method: 0,
        ip_range: '',
      };
    },
  });

  // 构建表单值，用于复制任务和编辑任务中回填表单数据（true:复制任务，false:编辑任务）
  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...getCycleFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    instId: values.instances?.[0]?._id,
    timeout: values.timeout,
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
        form.setFieldsValue(K8S_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: 5 }}
        onFinish={onFinish}
        initialValues={K8S_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('common.select')} ${t('Collection.k8sTask.selectK8S')}`}
          timeoutProps={{
            min: 0,
            defaultValue: 60,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        ></BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default K8sTaskForm;
