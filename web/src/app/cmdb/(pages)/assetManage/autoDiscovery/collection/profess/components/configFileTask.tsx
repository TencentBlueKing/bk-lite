'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import { Alert, Form, Input, Spin } from 'antd';
import { useLocale } from '@/context/locale';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import { useTaskForm, getCleanupFormValues, getCycleFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  CONFIG_FILE_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import {
  formatTaskValues,
  buildCredentialPool,
  normalizeCredentialPool,
  trimFormString,
} from '../hooks/formatTaskValues';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import styles from '../index.module.scss';
import CredentialPoolEditor from './credentialPoolEditor';

interface ConfigFileTaskFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const MAX_FILE_SIZE_LIMIT = 5 * 1024 * 1024;
const LINUX_FILE_PATH_RE = /^\/(?!.*\/$)(?!.*[*?]).+/;
const WINDOWS_FILE_PATH_RE = /^[A-Za-z]:\\(?!.*[\\/]$)(?!.*[*?]).+/;

const validateConfigFilePath = (_: unknown, value: string) => {
  const normalizedValue = (value || '').trim();
  if (!normalizedValue) {
    return Promise.reject(new Error('请输入配置文件绝对路径'));
  }

  const matchesAbsolutePath =
    LINUX_FILE_PATH_RE.test(normalizedValue) || WINDOWS_FILE_PATH_RE.test(normalizedValue);
  if (!matchesAbsolutePath) {
    return Promise.reject(new Error('请输入完整的配置文件路径，不能填写目录'));
  }

  const pathSegments = normalizedValue.split(/[\\/]/).filter(Boolean);
  const fileName = pathSegments[pathSegments.length - 1] || '';
  if (!fileName || fileName === '.' || fileName === '..') {
    return Promise.reject(new Error('请输入完整的配置文件路径，不能填写目录'));
  }

  return Promise.resolve();
};

const ConfigFileTask: React.FC<ConfigFileTaskFormProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const localeContext = useLocale();
  const { selectedGroup } = useUserInfoContext();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const copyTaskData = useAssetManageStore((state) => state.copyTaskData);
  const { model_id: modelId } = modelItem;
  const initialFormValues = useMemo(
    () => ({
      ...CONFIG_FILE_FORM_INITIAL_VALUES,
      organization: selectedGroup ? [Number(selectedGroup.id)] : [],
      credentialPool: [{ port: '22' }],
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
            config_file_path: values.configFilePath?.trim(),
          },
        };
      },
    });

  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...CONFIG_FILE_FORM_INITIAL_VALUES,
    credentialPool: normalizeCredentialPool(values.credential).map((item) => ({
      ...item,
      password: isCopy ? '' : PASSWORD_PLACEHOLDER,
    })),
    ...getCleanupFormValues(values),
    ...getCycleFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    accessPointId: values.access_point?.[0]?.id,
    configFilePath: values.params?.config_file_path || '',
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
          instPlaceholder={t('Collection.chooseHost')}
          assetOptionLabel={t('Collection.chooseHost')}
          timeoutProps={{
            min: 1,
            defaultValue: 10,
            addonAfter: t('Collection.k8sTask.second'),
          }}
        >
          <Alert
            type="info"
            showIcon
            className="mb-4"
            message={`单文件大小上限 ${MAX_FILE_SIZE_LIMIT / 1024 / 1024} MB，由系统在入库时统一限制，仅支持文本文件采集`}
          />

          <Form.Item
            label="配置文件绝对路径"
            name="configFilePath"
            rules={[{ validator: validateConfigFilePath }]}
          >
            <Input
              autoComplete="off"
              placeholder="/etc/nginx/nginx.conf 或 C:\\Windows\\System32\\drivers\\etc\\hosts"
            />
          </Form.Item>

          <div className={styles.panelHeader}>{t('Collection.credential')}</div>
          <Form.Item name="credentialPool">
            <CredentialPoolEditor credentialShape="config_file" editMode={Boolean(editId)} />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default ConfigFileTask;
