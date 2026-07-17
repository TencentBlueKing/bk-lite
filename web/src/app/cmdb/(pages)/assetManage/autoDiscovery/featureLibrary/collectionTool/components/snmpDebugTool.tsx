'use client';

import React, { useState, useEffect } from 'react';
import { Form, Input, Select, InputNumber, Button, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import type {
  SnmpCredential,
  CollectToolPrefillResponse,
} from '@/app/cmdb/types/collectTool';
import { useCollectTool } from '../hooks/useCollectTool';
import ResultPanel from './resultPanel';
import OidModal from './oidModal';

const MASKED = '••••••';
const IPV4_REG =
  /^((2[0-4]\d|25[0-5]|[01]?\d\d?)\.){3}(2[0-4]\d|25[0-5]|[01]?\d\d?)$/;

interface SnmpToolProps {
  accessPointOptions: Array<{ value: string; label: string }>;
  prefill?: CollectToolPrefillResponse['prefill'];
  taskId?: number;
}

const SnmpTool: React.FC<SnmpToolProps> = ({
  accessPointOptions,
  prefill,
  taskId,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [version, setVersion] = useState<string>('v2c');
  const [level, setLevel] = useState<string>('authNoPriv');
  const [oidModalOpen, setOidModalOpen] = useState(false);
  const { execStatus, activeAction, result, timerDisplay, execute, pause } =
    useCollectTool({ protocol: 'snmp' });

  useEffect(() => {
    if (prefill) {
      const cred = (prefill.credential || {}) as Partial<SnmpCredential>;
      const initialValues: any = {
        target: prefill.target || '',
        snmp_port: prefill.port || 161,
        access_point_id: prefill.access_point?.id || undefined,
        version: cred.version || 'v2c',
        community: cred.community || '',
        username: cred.username || '',
        level: cred.level || 'authNoPriv',
        integrity: cred.integrity || 'sha',
        authkey: cred.authkey || '',
        privacy: cred.privacy || 'aes',
        privkey: cred.privkey || '',
      };
      form.setFieldsValue(initialValues);
      setVersion(initialValues.version);
      setLevel(initialValues.level);
      return;
    }

    form.resetFields();
    setVersion('v2c');
    setLevel('authNoPriv');
  }, [form, prefill]);

  const buildPayload = (action: string, oid?: string) => {
    const values = form.getFieldsValue();
    const cred: any = { version: values.version };
    if (values.version === 'v2' || values.version === 'v2c') {
      cred.community = values.community;
    } else {
      cred.username = values.username;
      cred.level = values.level;
      cred.integrity = values.integrity;
      cred.authkey = values.authkey;
      if (values.level === 'authPriv') {
        cred.privacy = values.privacy;
        cred.privkey = values.privkey;
      }
    }
    const payload: any = {
      protocol: 'snmp',
      action,
      access_point_id: String(values.access_point_id),
      target: values.target,
      port: values.snmp_port || 161,
      credential: cred,
    };
    if (action === 'get_oid' && oid) {
      payload.oid = oid;
    }
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

  const handleOpenOidModal = () => {
    form
      .validateFields()
      .then(() => {
        setOidModalOpen(true);
      })
      .catch(() => {});
  };

  const handleOidConfirm = (oid: string) => {
    setOidModalOpen(false);
    const payload = buildPayload('get_oid', oid);
    execute(payload);
  };

  const isRunning = execStatus === 'running' || execStatus === 'submitting';

  const clearMaskedFieldOnFocus =
    (fieldName: string) => (e: React.FocusEvent<HTMLInputElement>) => {
      if (e.target.value === MASKED) {
        form.setFieldValue(fieldName, '');
      }
    };

  const restoreMaskedFieldOnBlur =
    (fieldName: string) => (e: React.FocusEvent<HTMLInputElement>) => {
      const value = e.target.value;
      if (prefill && (!value || value.trim() === '')) {
        form.setFieldValue(fieldName, MASKED);
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
            autoComplete="off-snmp-form"
            initialValues={{
              snmp_port: 161,
              version: 'v2c',
              level: 'authNoPriv',
              integrity: 'sha',
              privacy: 'aes',
            }}
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
              label={t('CollectTool.snmpPort')}
              name="snmp_port"
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
              label={t('Collection.SNMPTask.version')}
              name="version"
              rules={[{ required: true, message: t('CollectTool.required') }]}
            >
              <Select
                options={[
                  { value: 'v2', label: 'V2' },
                  { value: 'v2c', label: 'V2C' },
                  { value: 'v3', label: 'V3' },
                ]}
                onChange={(v) => {
                  setVersion(v);
                  form.resetFields([
                    'community',
                    'username',
                    'level',
                    'integrity',
                    'authkey',
                    'privacy',
                    'privkey',
                  ]);
                }}
              />
            </Form.Item>

            {(version === 'v2' || version === 'v2c') && (
              <Form.Item
                label={t('Collection.SNMPTask.communityString')}
                name="community"
                rules={[{ required: true, message: t('CollectTool.required') }]}
              >
                <Input.Password
                  visibilityToggle
                  autoComplete="off-community"
                  onFocus={clearMaskedFieldOnFocus('community')}
                  onBlur={restoreMaskedFieldOnBlur('community')}
                />
              </Form.Item>
            )}

            {version === 'v3' && (
              <>
                <Form.Item
                  label={t('Collection.SNMPTask.userName')}
                  name="username"
                  rules={[
                    { required: true, message: t('CollectTool.required') },
                  ]}
                >
                  <Input autoComplete="off-username" />
                </Form.Item>

                <Form.Item
                  label={t('Collection.SNMPTask.securityLevel')}
                  name="level"
                  rules={[
                    { required: true, message: t('CollectTool.required') },
                  ]}
                >
                  <Select
                    options={[
                      { value: 'authNoPriv', label: 'authNoPriv' },
                      { value: 'authPriv', label: 'authPriv' },
                    ]}
                    onChange={(v) => setLevel(v)}
                  />
                </Form.Item>

                <Form.Item
                  label={t('Collection.SNMPTask.hashAlgorithm')}
                  name="integrity"
                  rules={[
                    { required: true, message: t('CollectTool.required') },
                  ]}
                >
                  <Select
                    options={[
                      { value: 'sha', label: 'SHA' },
                      { value: 'md5', label: 'MD5' },
                    ]}
                  />
                </Form.Item>

                <Form.Item
                  label={t('Collection.SNMPTask.authPassword')}
                  name="authkey"
                  rules={[
                    { required: true, message: t('CollectTool.required') },
                  ]}
                >
                  <Input.Password
                    visibilityToggle
                    autoComplete="off-authkey"
                    onFocus={clearMaskedFieldOnFocus('authkey')}
                    onBlur={restoreMaskedFieldOnBlur('authkey')}
                  />
                </Form.Item>

                {level === 'authPriv' && (
                  <>
                    <Form.Item
                      label={t('Collection.SNMPTask.encryptAlgorithm')}
                      name="privacy"
                      rules={[
                        { required: true, message: t('CollectTool.required') },
                      ]}
                    >
                      <Select
                        options={[
                          { value: 'aes', label: 'AES' },
                          { value: 'des', label: 'DES' },
                        ]}
                      />
                    </Form.Item>

                    <Form.Item
                      label={t('Collection.SNMPTask.encryptKey')}
                      name="privkey"
                      rules={[
                        { required: true, message: t('CollectTool.required') },
                      ]}
                    >
                      <Input.Password
                        visibilityToggle
                        autoComplete="off-privkey"
                        onFocus={clearMaskedFieldOnFocus('privkey')}
                        onBlur={restoreMaskedFieldOnBlur('privkey')}
                      />
                    </Form.Item>
                  </>
                )}
              </>
            )}
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
                loading={activeAction === 'get_oid' && isRunning}
                disabled={isRunning && activeAction !== 'get_oid'}
                onClick={handleOpenOidModal}
              >
                {t('CollectTool.getOidData')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Execute']}>
              <Button
                loading={activeAction === 'raw_collect' && isRunning}
                disabled={isRunning && activeAction !== 'raw_collect'}
                onClick={() => handleAction('raw_collect')}
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

      <OidModal
        open={oidModalOpen}
        onConfirm={handleOidConfirm}
        onCancel={() => setOidModalOpen(false)}
        title={t('CollectTool.getOidTitle')}
        label="OID"
        placeholder={t('CollectTool.oidPlaceholder')}
      />
    </div>
  );
};

export default SnmpTool;
