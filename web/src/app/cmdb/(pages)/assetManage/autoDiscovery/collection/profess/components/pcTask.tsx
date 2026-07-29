'use client';

import React, { useEffect, useRef, useState } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
import { useTaskForm } from '../hooks/useTaskForm';
import { getCleanupFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { PC_FORM_INITIAL_VALUES } from '@/app/cmdb/constants/professCollection';
import { formatTaskValues } from '../hooks/formatTaskValues';
import {
  buildPCFormValues,
  buildPCSubmitPayload,
  getPCCredentialShape,
  getPCDefaults,
  PCOSType,
} from '../utils/pcTask';
import { Form, message, Select, Spin } from 'antd';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import CredentialPoolEditor from './credentialPoolEditor';
import { useCollectApi } from '@/app/cmdb/api';
import { buildPCCredentialHelp } from './credentialHelp';

interface PCTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const PCTask: React.FC<PCTaskFormProps> = ({
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
  const collectApi = useCollectApi();
  const [testLoading, setTestLoading] = useState(false);

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
    initialValues: PC_FORM_INITIAL_VALUES,
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

      let instanceData;
      if (collectType === 'ip') {
        instanceData = {
          ip_range: ipRange.join('-'),
          instances: [],
        };
      } else {
        instanceData = {
          ip_range: '',
          instances: selectedData || [],
        };
      }

      return {
        ...baseData,
        ...instanceData,
        ...buildPCSubmitPayload({
          osType: values.osType,
          credentialPool: values.credentialPool,
        }),
      };
    },
  });

  const osType: PCOSType = Form.useWatch('osType', form) || 'windows';

  // 构建表单值，用于复制任务和编辑任务中回填表单数据（true:复制任务，false:编辑任务）
  const buildFormValues = (
    values: any,
    isCopy: boolean,
    ipRange?: string[],
  ) => ({
    ...values,
    ipRange,
    ...getCleanupFormValues(values),
    ...buildPCFormValues(values, isCopy),
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

        // 复制任务中回填表单数据（此时任务名称和所有秘密值为空，OS 可重新选择）
        form.setFieldsValue(buildFormValues(values, true, ipRange));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }

        // 编辑任务中回填表单数据（OS 创建后不可修改）
        form.setFieldsValue(buildFormValues(values, false, ipRange));
      } else {
        form.setFieldsValue({
          ...PC_FORM_INITIAL_VALUES,
          ...getPCDefaults('windows'),
        });
      }
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  // 新建时切换 OS：重置为该 OS 的默认凭据，清空另一种 OS 的秘密值
  const handleOSChange = (nextOS: PCOSType) => {
    form.setFieldsValue({
      osType: nextOS,
      credentialPool: getPCDefaults(nextOS).credentialPool,
    });
  };

  const resolveTestHost = (): string => {
    const values = form.getFieldsValue();
    if (baseRef.current?.collectionType === 'ip') {
      return values.ipRange?.[0] || '';
    }
    const firstAsset: any = baseRef.current?.selectedData?.[0];
    return firstAsset?.ip_addr || firstAsset?.inst_name || '';
  };

  const handleTest = async () => {
    const values = form.getFieldsValue();
    const host = resolveTestHost();
    if (!host) {
      message.warning(t('Collection.PCTask.testNeedsTarget'));
      return;
    }
    const firstCredential = (values.credentialPool || [])[0] || {};
    const payload: Record<string, any> = {
      os_type: values.osType,
      host,
      access_point_id: values.accessPointId,
      credential: {
        username: firstCredential.username,
        password: firstCredential.password,
        private_key: firstCredential.private_key,
        passphrase: firstCredential.passphrase,
        port: firstCredential.port,
      },
    };
    if (values.osType === 'windows') {
      payload.winrm_scheme = firstCredential.scheme || 'https';
      payload.winrm_transport = 'ntlm';
      payload.winrm_cert_validation = Boolean(firstCredential.certValidation);
    }
    if (editId) {
      payload.task_id = editId;
    }
    try {
      setTestLoading(true);
      const result = await collectApi.pcTestConnection(payload);
      if (result?.success) {
        message.success(
          `${t('Collection.PCTask.testSuccess')}：${result.inst_name}`
        );
      } else {
        message.error(
          result?.message || t('Collection.PCTask.testFailed')
        );
      }
    } finally {
      setTestLoading(false);
    }
  };

  return (
    <Spin spinning={loading || testLoading}>
      <Form
        {...collectionFormLayout}
        form={form}
        onFinish={onFinish}
        initialValues={{ ...PC_FORM_INITIAL_VALUES, ...getPCDefaults('windows') }}
      >
        <BaseTaskForm
          ref={baseRef}
          nodeId={selectedNode.id}
          modelItem={modelItem}
          onClose={onClose}
          onTest={handleTest}
          submitLoading={submitLoading}
          instPlaceholder={`${t('Collection.chooseAsset')}`}
          timeoutProps={{
            min: 30,
            defaultValue: 120,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item
            name="osType"
            label={t('Collection.PCTask.osType')}
            rules={[{ required: true, message: t('common.selectTip') }]}
          >
            <Select
              disabled={Boolean(editId)}
              onChange={handleOSChange}
              options={[
                { label: 'Windows', value: 'windows' },
                { label: 'macOS', value: 'macos' },
              ]}
            />
          </Form.Item>
          <Form.Item name="credentialPool">
            <CredentialPoolEditor
              credentialShape={getPCCredentialShape(osType)}
              editMode={Boolean(editId)}
              credentialHelp={buildPCCredentialHelp(osType, t)}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default PCTask;
