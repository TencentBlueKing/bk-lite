'use client';

import React, { useEffect, useRef } from 'react';
import { Form, Spin } from 'antd';

import { HOST_FORM_INITIAL_VALUES } from '@/app/cmdb/constants/professCollection';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import type { CollectTask, ModelItem, TreeNode } from '@/app/cmdb/types/autoDiscovery';
import { useTranslation } from '@/utils/i18n';

import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
import {
  formatTaskValues,
  normalizeCredentialPool,
} from '../hooks/formatTaskValues';
import { getCleanupFormValues, useTaskForm } from '../hooks/useTaskForm';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { resolveCredentialHelp } from './credentialHelp';
import CredentialPoolEditor from './credentialPoolEditor';
import {
  buildRedfishCredential,
  createRedfishCredential,
  restoreRedfishCredential,
} from './redfishCredential';

interface RedfishTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const REDFISH_FORM_INITIAL_VALUES = {
  ...HOST_FORM_INITIAL_VALUES,
  credentialPool: [createRedfishCredential()],
};

const RedfishTask: React.FC<RedfishTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const collectionFormLayout = useCollectionFormLayout();
  const baseRef = useRef<BaseTaskRef>(null!);
  const { copyTaskData } = useAssetManageStore();
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
    initialValues: REDFISH_FORM_INITIAL_VALUES,
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
      const ipRange = values.ipRange?.length ? values.ipRange : undefined;
      const selectedData = baseRef.current?.selectedData;
      const instanceData = collectType === 'ip'
        ? { ip_range: ipRange.join('-'), instances: [] }
        : { ip_range: '', instances: selectedData || [] };

      return {
        ...baseData,
        ...instanceData,
        params: {
          ...(baseData.params || {}),
          collection_protocol: 'redfish',
        },
        credential: normalizeCredentialPool(values.credentialPool).map(
          buildRedfishCredential,
        ),
      };
    },
  });

  const buildFormValues = (values: CollectTask, isCopy: boolean, ipRange?: string[]) => ({
    ipRange,
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    credentialPool: (normalizeCredentialPool(values.credential).length
      ? normalizeCredentialPool(values.credential)
      : REDFISH_FORM_INITIAL_VALUES.credentialPool
    ).map((item) => restoreRedfishCredential(item, isCopy)),
    accessPointId: values.access_point?.[0]?.id,
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const values = copyTaskData;
        const ipRange = values.ip_range?.split('-');
        baseRef.current?.initCollectionType(
          values.ip_range?.length ? ipRange : values.instances,
          values.ip_range?.length ? 'ip' : 'asset',
        );
        form.setFieldsValue(buildFormValues(values, true, ipRange));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        const ipRange = values.ip_range?.split('-');
        baseRef.current?.initCollectionType(
          values.ip_range?.length ? ipRange : values.instances,
          values.ip_range?.length ? 'ip' : 'asset',
        );
        form.setFieldsValue(buildFormValues(values, false, ipRange));
      } else {
        form.setFieldsValue(REDFISH_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId, copyTaskData, editId]);

  return (
    <Spin spinning={loading}>
      <Form
        {...collectionFormLayout}
        form={form}
        onFinish={onFinish}
        initialValues={REDFISH_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={t('Collection.chooseAsset')}
          timeoutProps={{
            min: 1,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item name="credentialPool">
            <CredentialPoolEditor
              credentialShape="redfish"
              credentialHelp={resolveCredentialHelp(modelItem, t)}
              editMode={Boolean(editId)}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default RedfishTask;
