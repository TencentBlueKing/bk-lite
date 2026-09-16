'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import { Alert, Form, Spin } from 'antd';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useTaskForm, getCleanupFormValues, getCycleFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { HOST_FORM_INITIAL_VALUES } from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';

interface SslCerTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const SslCerTask: React.FC<SslCerTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const collectionFormLayout = useCollectionFormLayout();
  const { selectedGroup } = useUserInfoContext();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const copyTaskData = useAssetManageStore((state) => state.copyTaskData);
  const { model_id: modelId } = modelItem;
  const initialFormValues = useMemo(
    () => ({
      ...HOST_FORM_INITIAL_VALUES,
      organization: selectedGroup ? [Number(selectedGroup.id)] : [],
    }),
    [selectedGroup]
  );

  const { form, loading, submitLoading, fetchTaskDetail, formatCycleValue, onFinish } =
    useTaskForm({
      modelId,
      editId,
      initialValues: initialFormValues,
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

        const selectedData = baseRef.current?.selectedData;

        return {
          ...baseData,
          ip_range: '',
          instances: selectedData || [],
          credential: [],
          task_type: 'protocol',
          driver_type: 'protocol',
        };
      },
    });

  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...HOST_FORM_INITIAL_VALUES,
    ...getCleanupFormValues(values),
    ...getCycleFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    accessPointId: values.access_point?.[0]?.id,
    ip_precheck: Boolean(values.params?.ip_precheck),
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const values = copyTaskData;
        baseRef.current?.initCollectionType(values.instances, 'asset');
        form.setFieldsValue(buildFormValues(values, true));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        if (!values) {
          return;
        }
        baseRef.current?.initCollectionType(values.instances, 'asset');
        form.setFieldsValue(buildFormValues(values, false));
      } else {
        baseRef.current?.initCollectionType([], 'asset');
        form.setFieldsValue(initialFormValues);
      }
    };

    initForm();
  }, [modelId, copyTaskData, editId, form, initialFormValues]);

  return (
    <Spin spinning={loading}>
      <Form
        {...collectionFormLayout}
        form={form}
        onFinish={onFinish}
        initialValues={initialFormValues}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={t('Collection.chooseAsset')}
          assetOptionLabel={t('Collection.chooseAsset')}
          timeoutProps={{
            min: 1,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Alert
            type="info"
            showIcon
            className="mb-4"
            message="只选已录入的 SSL 证书实例，不能选网段。默认端口 443，无需凭据。"
          />
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default SslCerTask;
