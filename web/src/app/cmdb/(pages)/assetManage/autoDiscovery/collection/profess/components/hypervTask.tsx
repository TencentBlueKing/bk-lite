'use client';

import React, { useEffect, useRef } from 'react';
import { Form, Spin } from 'antd';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import CredentialPoolEditor from './credentialPoolEditor';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
import { useTaskForm, getCleanupFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  HOST_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import {
  formatTaskValues,
  normalizeCredentialPool,
  trimFormString,
} from '../hooks/formatTaskValues';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import {
  HYPERV_DEFAULT_CREDENTIAL,
  buildHypervFormValues,
  buildHypervSubmitPayload,
} from '../utils/hypervTask';

interface HypervTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const HYPERV_FORM_INITIAL_VALUES = {
  ...HOST_FORM_INITIAL_VALUES,
  timeout: 180,
};

const HypervTask: React.FC<HypervTaskFormProps> = ({
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
    initialValues: HYPERV_FORM_INITIAL_VALUES,
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
      const collectType = baseRef.current?.collectionType || 'ip';
      const ipRange = values.ipRange?.length ? values.ipRange : [];
      const selectedData = baseRef.current?.selectedData;
      let instanceData;
      if (collectType === 'ip') {
        instanceData = {
          ip_range: ipRange.join('-'),
          instances: [],
        };
      } else {
        instanceData = {
          ip_range: '',
          instances: (selectedData || []).map(({ inst_uuid }) => ({
            inst_uuid,
          })),
        };
      }
      const hypervPayload = buildHypervSubmitPayload({
        credentialPool: values.credentialPool,
      });

      return {
        ...baseData,
        ...instanceData,
        params: {
          ...baseData.params,
          ...hypervPayload.params,
          target_source: collectType,
        },
        credential: hypervPayload.credential,
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean, ipRange?: string[]) => ({
    ipRange,
    ...getCleanupFormValues(values),
    ...values,
    ...buildHypervFormValues(values, isCopy),
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData || editId) {
        const values = copyTaskData || (await fetchTaskDetail(editId as number));
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else if (
          values.params?.target_source === 'host' ||
          values.instances?.length
        ) {
          baseRef.current?.initCollectionType(values.instances, 'host');
        } else {
          baseRef.current?.initCollectionType([], 'ip');
        }
        form.setFieldsValue(buildFormValues(values, Boolean(copyTaskData), ipRange));
        return;
      }
      form.setFieldsValue({
        ...HYPERV_FORM_INITIAL_VALUES,
        credentialPool: [{ ...HYPERV_DEFAULT_CREDENTIAL }],
      });
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  const validateCredentialPool = (_: unknown, value?: any[]) => {
    const credentialValue = normalizeCredentialPool(value)[0] || {};
    if (
      credentialValue.credential_source === 'vault' &&
      !credentialValue.vault_credential_id
    ) {
      return Promise.reject(new Error('请选择已有凭据'));
    }
    if (
      credentialValue.credential_source !== 'vault' &&
      !trimFormString(credentialValue.username)
    ) {
      return Promise.reject(new Error(`${t('common.inputMsg')}${t('user', '用户')}`));
    }
    if (
      credentialValue.credential_source !== 'vault' &&
      !trimFormString(credentialValue.password)
    ) {
      return Promise.reject(
        new Error(`${t('common.inputMsg')}${t('password', '密码')}`)
      );
    }
    if (
      credentialValue.credential_source !== 'vault' &&
      !editId &&
      credentialValue.password === PASSWORD_PLACEHOLDER
    ) {
      return Promise.reject(
        new Error(`${t('common.inputMsg')}${t('password', '密码')}`)
      );
    }
    if (!credentialValue.port) {
      return Promise.reject(
        new Error(`${t('common.inputMsg')}${t('Collection.port', '端口')}`)
      );
    }
    return Promise.resolve();
  };

  return (
    <Spin spinning={loading}>
      <Form
        {...collectionFormLayout}
        form={form}
        onFinish={onFinish}
        initialValues={HYPERV_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={t('Collection.chooseHost')}
          timeoutProps={{
            min: 1,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item
            name="credentialPool"
            rules={[{ validator: validateCredentialPool }]}
            validateTrigger={[]}
          >
            <CredentialPoolEditor
              vaultCategory={modelItem.credential_category}
              vaultTypeKeys={modelItem.credential_type_keys}
              credentialShape="winrm"
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

export default HypervTask;
