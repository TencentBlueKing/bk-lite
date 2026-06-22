'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { getCleanupFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  HOST_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import {
  buildCredentialPool,
  formatTaskValues,
  normalizeCredentialPool,
  trimFormString,
} from '../hooks/formatTaskValues';
import { Form, Spin } from 'antd';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import CredentialPoolEditor from './credentialPoolEditor';

interface IPMITaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const IPMI_FORM_INITIAL_VALUES = {
  ...HOST_FORM_INITIAL_VALUES,
  credentialPool: [{ port: '623', privilege: 'administrator' }],
};

const IPMITask: React.FC<IPMITaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const localeContext = useLocale();
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
    initialValues: IPMI_FORM_INITIAL_VALUES,
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
      // IPMI 与 SSH 物理机任务共享 BaseTask 的目标选择交互：既支持 IP 段，也支持从现有资产实例中选择。
      const instanceData = collectType === 'ip'
        ? {
          ip_range: ipRange.join('-'),
          instances: [],
        }
        : {
          ip_range: '',
          instances: selectedData || [],
        };

      return {
        ...baseData,
        ...instanceData,
        // 注意：这里仍然写回现有 physcial_server 模型，但凭据语义已经变成 IPMI/BMC 登录信息。
        credential: buildCredentialPool(values.credentialPool, (item) => ({
          username: trimFormString(item.username),
          password: trimFormString(item.password),
          port: item.port,
          privilege: item.privilege,
        })),
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean, ipRange?: string[]) => ({
    ipRange,
    ...getCleanupFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    credentialPool: (normalizeCredentialPool(values.credential).length
      ? normalizeCredentialPool(values.credential)
      : IPMI_FORM_INITIAL_VALUES.credentialPool
    ).map((item) => ({
      ...item,
      username: item.username || item.user,
      password: isCopy ? '' : PASSWORD_PLACEHOLDER,
      port: item.port || '623',
      privilege: item.privilege || 'administrator',
    })),
    accessPointId: values.access_point?.[0]?.id,
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const values = copyTaskData;
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }
        form.setFieldsValue(buildFormValues(values, true, ipRange));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }
        form.setFieldsValue(buildFormValues(values, false, ipRange));
      } else {
        form.setFieldsValue(IPMI_FORM_INITIAL_VALUES);
      }
    };
    initForm();
  }, [modelId, copyTaskData, editId]);

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }}
        onFinish={onFinish}
        initialValues={IPMI_FORM_INITIAL_VALUES}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          submitLoading={submitLoading}
          instPlaceholder={`${t('Collection.chooseAsset')}`}
          timeoutProps={{
            min: 0,
            defaultValue: 10,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item name="credentialPool">
            <CredentialPoolEditor credentialShape="ipmi" editMode={Boolean(editId)} />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default IPMITask;
