'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useTranslation } from '@/utils/i18n';
import { Form, Spin } from 'antd';
import { useTaskForm } from '../hooks/useTaskForm';
import { K8S_FORM_INITIAL_VALUES } from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';

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
  const baseRef = useRef<BaseTaskRef>(null);
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

  useEffect(() => {
    const initForm = async () => {
      if (editId) {
        const values = await fetchTaskDetail(editId);
        form.setFieldsValue({
          ...values,
          organization: values.team || [],
        });
      } else {
        form.setFieldsValue(K8S_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId]);

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
