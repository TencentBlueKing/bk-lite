'use client';

import React, { useEffect, useRef } from 'react';
import { Alert, Form, Spin } from 'antd';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useTranslation } from '@/utils/i18n';
import { useCollectionFormLayout } from '../hooks/useCollectionFormLayout';
import { getCleanupFormValues, useTaskForm } from '../hooks/useTaskForm';
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
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import CredentialPoolEditor from './credentialPoolEditor';
import { buildPCCredentialHelp, resolveCredentialHelp } from './credentialHelp';
import styles from '../index.module.scss';

interface CustomScriptTaskProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const CustomScriptTask: React.FC<CustomScriptTaskProps> = ({
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
  const windows = modelItem.os_type === 'windows';
  const credentialShape = windows ? 'winrm' : 'ssh';
  const defaultPort = windows ? 5986 : 22;

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
    initialValues: HOST_FORM_INITIAL_VALUES,
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
      const selectedData = baseRef.current?.selectedData || [];
      const instanceData = collectType === 'ip'
        ? { ip_range: (ipRange || []).join('-'), instances: [] }
        : {
          ip_range: '',
          instances: selectedData.map((item) => ({
            inst_uuid: item.inst_uuid,
            ip_addr: item.ip_addr,
          })),
        };
      const first = (values.credentialPool || [])[0] || {};
      return {
        ...baseData,
        ...instanceData,
        credential: buildCredentialPool(values.credentialPool, (item) => {
          const credential: Record<string, any> = {};
          if (item.credential_id) {
            credential.credential_id = item.credential_id;
          }
          const username = trimFormString(item.username);
          const password = trimFormString(item.password);
          if (username !== undefined) {
            credential.username = username;
          }
          if (password && password !== PASSWORD_PLACEHOLDER) {
            credential.password = password;
          }
          if (item.port !== undefined && item.port !== null && item.port !== '') {
            credential.port = item.port;
          }
          return credential;
        }),
        params: {
          ...baseData.params,
          os_type: modelItem.os_type,
          ...(windows ? {
            winrm_scheme: first.scheme || 'https',
            winrm_transport: 'ntlm',
            winrm_cert_validation: Boolean(first.certValidation),
          } : {}),
        },
      };
    },
  });

  const buildFormValues = (values: any, isCopy: boolean, ipRange?: string[]) => ({
    credentialPool: normalizeCredentialPool(values.credential).map((item) => ({
      ...item,
      ...(windows ? {
        scheme: values.params?.winrm_scheme || 'https',
        transport: 'ntlm',
        certValidation: Boolean(values.params?.winrm_cert_validation),
      } : {}),
      password: isCopy ? '' : PASSWORD_PLACEHOLDER,
    })),
    ipRange,
    ...getCleanupFormValues(values),
    ...values,
    ip_precheck: Boolean(values.params?.ip_precheck),
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    accessPointId: values.access_point?.[0]?.id,
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        const ipRange = copyTaskData.ip_range?.split('-');
        if (copyTaskData.ip_range?.length) {
          baseRef.current?.initCollectionType(ipRange, 'ip');
        } else {
          baseRef.current?.initCollectionType(copyTaskData.instances, 'asset');
        }
        form.setFieldsValue(buildFormValues(copyTaskData, true, ipRange));
        setCopyTaskData(null);
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
        form.setFieldsValue({
          ...HOST_FORM_INITIAL_VALUES,
          credentialPool: [windows
            ? { port: defaultPort, scheme: 'https', transport: 'ntlm', certValidation: false }
            : { port: defaultPort }],
        });
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
        initialValues={HOST_FORM_INITIAL_VALUES}
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
          <Alert
            type="info"
            showIcon
            className={`${styles.formFieldHint} mb-4`}
            message={t('Collection.hostCredentialOptionalTip')}
          />
          <Form.Item name="credentialPool">
            <CredentialPoolEditor
              vaultCategory="host"
              vaultTypeKeys={[windows ? 'winrm' : 'ssh']}
              credentialShape={credentialShape}
              editMode={Boolean(editId)}
              credentialHelp={windows
                ? buildPCCredentialHelp('windows', t)
                : resolveCredentialHelp({ model_id: 'host', type: 'job', credential_protocol: 'ssh' }, t)}
            />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default CustomScriptTask;
