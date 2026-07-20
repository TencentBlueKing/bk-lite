'use client';

import React, { useEffect } from 'react';
import { Form, Input, InputNumber, Select, Button, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import type {
  IpmiCredential,
  CollectToolPrefillResponse,
} from '@/app/cmdb/types/collectTool';
import { useCollectTool } from '../hooks/useCollectTool';
import ResultPanel from './resultPanel';

const MASKED = '••••••';
const IPV4_REG =
  /^((2[0-4]\d|25[0-5]|[01]?\d\d?)\.){3}(2[0-4]\d|25[0-5]|[01]?\d\d?)$/;
const PRIVILEGE_OPTIONS = [
  { label: 'callback', value: 'callback' },
  { label: 'user', value: 'user' },
  { label: 'operator', value: 'operator' },
  { label: 'administrator', value: 'administrator' },
];

interface IpmiToolProps {
  accessPointOptions: Array<{ value: string; label: string }>;
  prefill?: CollectToolPrefillResponse['prefill'];
  taskId?: number;
}

const IpmiTool: React.FC<IpmiToolProps> = ({
  accessPointOptions,
  prefill,
  taskId,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { execStatus, activeAction, result, timerDisplay, execute, pause } =
    useCollectTool({ protocol: 'ipmi' });

  useEffect(() => {
    if (prefill) {
      const cred = (prefill.credential || {}) as Partial<IpmiCredential>;
      form.setFieldsValue({
        target: prefill.target || '',
        port: prefill.port || 623,
        access_point_id: prefill.access_point?.id || undefined,
        username: cred.username || '',
        password: cred.password || '',
        privilege: (cred as any).privilege || 'administrator',
        cipher_suite: (cred as any).cipher_suite || '',
      });
      return;
    }

    form.resetFields();
  }, [form, prefill]);

  const buildPayload = (action: string) => {
    const values = form.getFieldsValue();
    const cred: any = {
      username: values.username,
      password: values.password,
      privilege: values.privilege || 'administrator',
    };
    if (values.cipher_suite) {
      cred.cipher_suite = values.cipher_suite;
    }
    const payload: any = {
      protocol: 'ipmi',
      action,
      access_point_id: String(values.access_point_id),
      target: values.target,
      port: values.port || 623,
      credential: cred,
    };
    if (taskId) {
      payload.task_id = taskId;
    }
    return payload;
  };

  const handleAction = async (action: string) => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    const payload = buildPayload(action);
    execute(payload);
  };

  const isRunning = execStatus === 'running' || execStatus === 'submitting';

  const clearMaskedPasswordOnFocus = (
    e: React.FocusEvent<HTMLInputElement>,
  ) => {
    if (e.target.value === MASKED) {
      form.setFieldValue('password', '');
    }
  };

  const restoreMaskedPasswordOnBlur = (
    e: React.FocusEvent<HTMLInputElement>,
  ) => {
    const value = e.target.value;
    if (prefill && (!value || value.trim() === '')) {
      form.setFieldValue('password', MASKED);
    }
  };

  return (
    <div className="flex h-full min-h-0 gap-4">
      {/* Left: Form，max-height 限制高度，内容溢出时表单区滚动，按钮固定底部 */}
      <div
        className="w-100 shrink-0 flex flex-col"
        style={{ height: 'calc(100vh - 380px)' }}
      >
        <div className="flex-1 overflow-y-auto min-h-0 pr-2">
          <Form
            form={form}
            layout="vertical"
            autoComplete="off-ipmi-form"
            initialValues={{ port: 623, privilege: 'administrator' }}
          >
            <Form.Item
              label={t('CollectTool.targetIp')}
              name="target"
              rules={[
                { required: true, message: t('CollectTool.required') },
                {
                  validator: (_, value: string) => {
                    if (!value || IPV4_REG.test(value.trim())) {
                      return Promise.resolve();
                    }
                    return Promise.reject(
                      new Error(
                        t('common.inputMsg') + t('CollectTool.targetIp'),
                      ),
                    );
                  },
                },
              ]}
            >
              <Input placeholder="10.0.0.1" autoComplete="off-target" />
            </Form.Item>

            <Form.Item
              label={t('CollectTool.port')}
              name="port"
              rules={[{ required: true, message: t('CollectTool.required') }]}
            >
              <InputNumber min={1} max={65535} className="w-full" />
            </Form.Item>

            <Form.Item
              label={t('CollectTool.accessPoint')}
              name="access_point_id"
              rules={[{ required: true, message: t('CollectTool.required') }]}
            >
              <Select
                placeholder={t('CollectTool.selectAccessPoint')}
                options={accessPointOptions}
              />
            </Form.Item>

            <Form.Item
              label={t('CollectTool.username')}
              name="username"
              rules={[{ required: true, message: t('CollectTool.required') }]}
            >
              <Input autoComplete="off-username" />
            </Form.Item>

            <Form.Item
              label={t('CollectTool.password')}
              name="password"
              rules={[{ required: true, message: t('CollectTool.required') }]}
            >
              <Input.Password
                visibilityToggle
                autoComplete="off-password"
                onFocus={clearMaskedPasswordOnFocus}
                onBlur={restoreMaskedPasswordOnBlur}
              />
            </Form.Item>

            <Form.Item
              label={t('Collection.IPMITask.privilege')}
              name="privilege"
              rules={[{ required: true, message: t('CollectTool.required') }]}
            >
              <Select options={PRIVILEGE_OPTIONS} />
            </Form.Item>

            <Form.Item label={t('CollectTool.cipherSuite')} name="cipher_suite">
              <Input
                placeholder={t('CollectTool.optional')}
                autoComplete="off-cipher-suite"
              />
            </Form.Item>
          </Form>
        </div>

        <div className="shrink-0 pt-3">
          <Space>
            <PermissionWrapper requiredPermissions={['Execute']}>
              <Button
                type="primary"
                loading={activeAction === 'test_connection' && isRunning}
                disabled={isRunning && activeAction !== 'test_connection'}
                onClick={() => handleAction('test_connection')}
              >
                {t('CollectTool.testConnection')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Execute']}>
              <Button
                loading={activeAction === 'ipmi_collect' && isRunning}
                disabled={isRunning && activeAction !== 'ipmi_collect'}
                onClick={() => handleAction('ipmi_collect')}
              >
                {t('CollectTool.getRawData')}
              </Button>
            </PermissionWrapper>
          </Space>
        </div>
      </div>

      {/* Right: Result */}
      <div className="flex-1 min-h-0 min-w-0">
        <ResultPanel
          result={result}
          execStatus={execStatus}
          timerDisplay={timerDisplay}
          onReset={pause}
          isRunning={isRunning}
        />
      </div>
    </div>
  );
};

export default IpmiTool;
