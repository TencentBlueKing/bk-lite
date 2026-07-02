'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Checkbox, Form, Input, Spin, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useLocale } from '@/context/locale';
import { useUserInfoContext } from '@/context/userInfo';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import CredentialPoolEditor from './credentialPoolEditor';
import { useTaskForm, getCleanupFormValues, getCycleFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  NETWORK_CONFIG_FILE_FORM_INITIAL_VALUES,
  NETWORK_CONFIG_SUPPORTED_BRANDS,
  PASSWORD_PLACEHOLDER,
  validateNetworkConfigCommands,
} from '@/app/cmdb/constants/professCollection';
import {
  buildCredentialPool,
  formatTaskValues,
  normalizeCredentialPool,
  trimFormString,
} from '../hooks/formatTaskValues';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import { useCollectApi } from '@/app/cmdb/api';

interface NetworkConfigFileTaskProps {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const defaultBrandTip = `当前支持厂商：${NETWORK_CONFIG_SUPPORTED_BRANDS.join('、')}`;

const NetworkConfigFileTask: React.FC<NetworkConfigFileTaskProps> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const localeContext = useLocale();
  const { selectedGroup } = useUserInfoContext();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const copyTaskData = useAssetManageStore((state) => state.copyTaskData);
  const collectApi = useCollectApi();
  const [brandTip, setBrandTip] = useState(defaultBrandTip);
  const { model_id: modelId } = modelItem;
  const initialFormValues = useMemo(
    () => ({
      ...NETWORK_CONFIG_FILE_FORM_INITIAL_VALUES,
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
        const selectedData = baseRef.current?.selectedData || [];

        return {
          ...baseData,
          ip_range: '',
          instances: selectedData,
          credential: buildCredentialPool(values.credentialPool, (item) => {
            const credential: Record<string, any> = {};
            const username = trimFormString(item.username);
            const password = trimFormString(item.password);
            const enablePassword = trimFormString(item.enable_password);
            if (item.credential_id) {
              credential.credential_id = item.credential_id;
            }
            if (username !== undefined) {
              credential.username = username;
            }
            if (password && password !== PASSWORD_PLACEHOLDER) {
              credential.password = password;
            }
            if (values.needEnable && enablePassword && enablePassword !== PASSWORD_PLACEHOLDER) {
              credential.enable_password = enablePassword;
            }
            if (item.port !== undefined && item.port !== null && item.port !== '') {
              credential.port = item.port;
            }
            return credential;
          }),
          params: {
            config_name: values.configName?.trim(),
            commands: values.commands,
            need_enable: Boolean(values.needEnable),
          },
        };
      },
    });

  useEffect(() => {
    collectApi.getNetworkConfigBrands().then((data: any) => {
      const labels = (data?.items || []).map((item: any) => item.label).filter(Boolean);
      if (labels.length) {
        setBrandTip(`当前支持厂商：${labels.join('、')}`);
      }
    });
  }, [collectApi]);

  const buildFormValues = (values: any, isCopy: boolean) => ({
    ...NETWORK_CONFIG_FILE_FORM_INITIAL_VALUES,
    credentialPool: normalizeCredentialPool(values.credential).map((item) => ({
      ...item,
      password: isCopy ? '' : PASSWORD_PLACEHOLDER,
      enable_password: isCopy ? '' : PASSWORD_PLACEHOLDER,
    })),
    ...getCleanupFormValues(values),
    ...getCycleFormValues(values),
    ...values,
    taskName: isCopy ? '' : values.name,
    organization: values.team || [],
    accessPointId: values.access_point?.[0]?.id,
    configName: values.params?.config_name || '',
    commands: values.params?.commands || '',
    needEnable: Boolean(values.params?.need_enable),
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
          instPlaceholder="选择网络设备"
          assetOptionLabel="选择网络设备"
          timeoutProps={{
            min: 1,
            defaultValue: 60,
            addonAfter: '秒',
          }}
        >
          <Alert
            type="info"
            showIcon
            className="mb-4"
            message={(
              <span>
                {brandTip}
                <Tooltip title="缺少厂商或厂商不支持的实例不可选择">
                  <InfoCircleOutlined className="ml-1 text-gray-400" />
                </Tooltip>
              </span>
            )}
          />

          <Form.Item
            label="配置名称"
            name="configName"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input autoComplete="off" placeholder="例如 running-config" />
          </Form.Item>

          <Form.Item
            label="采集命令"
            name="commands"
            rules={[
              {
                validator: async (_, value) => {
                  const error = validateNetworkConfigCommands(value);
                  if (error) {
                    throw new Error(error);
                  }
                },
              },
            ]}
          >
            <Input.TextArea
              autoComplete="off"
              rows={6}
              placeholder={'每行一条命令，例如：\nshow running-config\nshow version'}
            />
          </Form.Item>

          <Form.Item name="needEnable" valuePropName="checked">
            <Checkbox>需要特权模式</Checkbox>
          </Form.Item>

          <Form.Item
            name="credentialPool"
            rules={[
              {
                validator: async (_, value) => {
                  if (!form.getFieldValue('needEnable')) {
                    return;
                  }
                  const hasEnablePassword = (value || []).some(
                    (item: any) => item?.enable_password && item.enable_password !== PASSWORD_PLACEHOLDER
                  );
                  if (!hasEnablePassword) {
                    throw new Error('启用特权模式时必须配置特权密码');
                  }
                },
              },
            ]}
          >
            <CredentialPoolEditor credentialShape="network_config_file" editMode={Boolean(editId)} />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default NetworkConfigFileTask;
