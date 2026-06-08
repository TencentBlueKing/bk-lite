'use client';

import React, { useEffect, useRef } from 'react';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { useTaskForm } from '../hooks/useTaskForm';
import { getCleanupFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  SQL_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import {
  formatTaskValues,
  buildCredentialPool,
  normalizeCredentialPool,
  trimFormString,
} from '../hooks/formatTaskValues';
import { Form, Spin } from 'antd';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import CredentialPoolEditor from './credentialPoolEditor';

interface SQLTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const SQLTask: React.FC<SQLTaskFormProps> = ({
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
  const isMssql = modelId === 'mssql';
  const initialFormValues = {
    ...SQL_FORM_INITIAL_VALUES,
    ...(isMssql ? { port: '1433', database: 'master' } : {}),
  };

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

      const collectType = baseRef.current?.collectionType;
      const ipRange = values.ipRange?.length ? values.ipRange : undefined;
      const selectedData = baseRef.current?.selectedData;

      let instanceData: {
        ip_range: string;
        instances: any[];
      };
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
        credential: buildCredentialPool(values.credentialPool, (item) => {
          const credential: Record<string, any> = {};
          if (item.credential_id) {
            credential.credential_id = item.credential_id;
          }
          const user = trimFormString(item.user || item.username);
          const password = trimFormString(item.password);
          if (user !== undefined) {
            credential.user = user;
          }
          if (password && password !== PASSWORD_PLACEHOLDER) {
            credential.password = password;
          }
          if (item.port !== undefined && item.port !== null && item.port !== '') {
            credential.port = item.port;
          }
          if (isMssql) {
            credential.database = trimFormString(item.database);
          }
          return credential;
        }),
      };
    },
  });

  // 构建表单值，用于复制任务和编辑任务中回填表单数据（true:复制任务，false:编辑任务）
  const buildFormValues = (values: any, isCopy: boolean, ipRange?: string[]) => {
    return {
      credentialPool: normalizeCredentialPool(values.credential).map((item) => ({
        ...item,
        user: item.user || item.username,
        password: isCopy ? '' : PASSWORD_PLACEHOLDER,
      })),
      ipRange,
      ...getCleanupFormValues(values),
      ...values,
      taskName: isCopy ? '' : values.name,
      organization: values.team || [],
      accessPointId: values.access_point?.[0]?.id,
    };
  };

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

        // 复制任务中回填表单数据（此时任务名称和密码为空，需要用户手动输入）
        form.setFieldsValue(buildFormValues(values, true, ipRange));
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        const ipRange = values.ip_range?.split('-');
        if (values.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(values.instances, 'asset');
        }

        // 编辑任务中回填表单数据
        form.setFieldsValue(buildFormValues(values, false, ipRange));
      } else {
        form.setFieldsValue({
          ...initialFormValues,
          credentialPool: [{ port: initialFormValues.port, ...(isMssql ? { database: 'master' } : {}) }],
        });
      }
    };
    initForm();
  }, [modelId, copyTaskData, setCopyTaskData]);

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }}
        onFinish={onFinish}
        initialValues={initialFormValues}
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
            defaultValue: 600,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Form.Item name="credentialPool">
            <CredentialPoolEditor credentialShape="sql" editMode={Boolean(editId)} showDatabase={isMssql} />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default SQLTask;
