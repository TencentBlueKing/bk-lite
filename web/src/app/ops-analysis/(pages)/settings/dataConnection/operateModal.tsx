'use client';

import React, { useEffect } from 'react';
import GroupTreeSelect from '@/components/group-tree-select';
import { Drawer, Form, Input, InputNumber, Button, message, Modal, Radio, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { HandledRequestError } from '@/utils/request';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { useUserInfoContext } from '@/context/userInfo';
import {
  DataConnectionOperateModalProps,
  DataConnectionType,
  DataConnectionTestPayload,
} from '@/app/ops-analysis/types/dataConnection';
import { useDataConnectionApi } from '@/app/ops-analysis/api/dataConnection';
import {
  formatJsonText,
  parseJsonObject,
  PASSWORD_PLACEHOLDER,
} from '../dataSource/operateModalUtils';

const OperateModal: React.FC<DataConnectionOperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [testConnectionLoading, setTestConnectionLoading] = React.useState(false);
  const { selectedGroup } = useUserInfoContext();
  const {
    createDataConnection,
    updateDataConnection,
    getDataConnectionReferences,
    testDataConnectionConfig,
    testDataConnectionDraft,
  } = useDataConnectionApi();
  const connectionType = (Form.useWatch('connection_type', form) ||
    'mysql') as DataConnectionType;
  const authType = (Form.useWatch('auth_type', form) || 'none') as string;
  const handleClose = () => guardClose(form.isFieldsTouched(), onClose);

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (currentRow) {
      const config = currentRow.config || {};
      form.setFieldsValue({
        name: currentRow.name,
        connection_type: currentRow.connection_type,
        description: currentRow.description,
        groups: currentRow.groups,
        is_active: currentRow.is_active,
        host: config.host,
        port: config.port,
        database: config.database,
        username: config.username,
        password: PASSWORD_PLACEHOLDER,
        base_url: config.base_url || config.url,
        headersText: formatJsonText(config.headers || {}),
        url: config.url,
        auth_type: config.auth_type || 'none',
        api_key: config.api_key ? PASSWORD_PLACEHOLDER : undefined,
        ca_cert: config.ca_cert,
        timeout_seconds: config.timeout_seconds ?? 30,
        index: config.index,
      });
    } else {
      form.setFieldsValue({
        connection_type: 'mysql',
        is_active: true,
        port: 3306,
        groups: selectedGroup?.id ? [selectedGroup.id] : [],
        headersText: '{}',
      });
    }
  }, [open, currentRow, form, selectedGroup]);

  const handlePasswordFocus = (event: React.FocusEvent<HTMLInputElement>) => {
    if (!currentRow) return;
    if (event.target.value === PASSWORD_PLACEHOLDER) {
      form.setFieldValue('password', '');
    }
  };

  const handlePasswordBlur = (event: React.FocusEvent<HTMLInputElement>) => {
    if (!currentRow) return;
    if (!event.target.value?.trim()) {
      form.setFieldValue('password', PASSWORD_PLACEHOLDER);
    }
  };

  const isSensitiveEndpointChanged = (
    type: DataConnectionType,
    config: Record<string, any>,
  ) => {
    if (!currentRow) return false;
    const prev = currentRow.config || {};
    if (type === 'rest_api') {
      const prevBase = String(prev.base_url || prev.url || '');
      const nextBase = String(config.base_url || '');
      if (prevBase !== nextBase) return true;
      return (
        JSON.stringify(prev.headers || {}) !== JSON.stringify(config.headers || {})
      );
    }
    if (type === 'elasticsearch') {
      if (String(prev.url ?? '') !== String(config.url ?? '')) return true;
      if (String(prev.auth_type ?? 'none') !== String(config.auth_type ?? 'none')) return true;
      if (String(prev.username ?? '') !== String(config.username ?? '')) return true;
      if (String(prev.index ?? '') !== String(config.index ?? '')) return true;
      if (String(prev.ca_cert ?? '') !== String(config.ca_cert ?? '')) return true;
      if (
        config.password &&
        config.password !== PASSWORD_PLACEHOLDER &&
        config.password !== prev.password
      ) {
        return true;
      }
      if (
        config.api_key &&
        config.api_key !== PASSWORD_PLACEHOLDER &&
        config.api_key !== prev.api_key
      ) {
        return true;
      }
      return false;
    }
    if (String(prev.host ?? '') !== String(config.host ?? '')) return true;
    if (String(prev.port ?? '') !== String(config.port ?? '')) return true;
    if (String(prev.database ?? '') !== String(config.database ?? '')) return true;
    if (String(prev.username ?? '') !== String(config.username ?? '')) return true;
    if (
      config.password &&
      config.password !== PASSWORD_PLACEHOLDER &&
      config.password !== prev.password
    ) {
      return true;
    }
    return false;
  };

  const persist = async (payload: Record<string, any>) => {
    if (currentRow) {
      await updateDataConnection(currentRow.id, payload);
      message.success(t('dataConnection.updateSuccess'));
    } else {
      await createDataConnection(payload);
      message.success(t('dataConnection.createSuccess'));
    }
    onClose();
    onSuccess?.();
  };

  const handleTestConnection = async () => {
    try {
      setTestConnectionLoading(true);
      const connectionFields =
        connectionType === 'rest_api'
          ? ['connection_type', 'base_url', 'headersText']
          : connectionType === 'elasticsearch'
            ? [
              'connection_type',
              'url',
              'index',
              'auth_type',
              ...(authType === 'basic' ? ['username', 'password'] : []),
              ...(authType === 'api_key' ? ['api_key'] : []),
            ]
            : [
              'connection_type',
              'host',
              'port',
              'database',
              'username',
              'password',
            ];
      await form.validateFields(connectionFields);
      const values = form.getFieldsValue(true);
      const config: Record<string, unknown> =
        connectionType === 'rest_api'
          ? {
            base_url: values.base_url,
            headers: parseJsonObject(
              values.headersText,
              `${t('dataSource.headers')}${t('dataSource.jsonObjectRequired')}`,
            ),
          }
          : connectionType === 'elasticsearch'
            ? {
              url: values.url,
              auth_type: values.auth_type || 'none',
              timeout_seconds: values.timeout_seconds ?? 30,
              index: values.index,
              ...(String(values.ca_cert || '').trim() ? { ca_cert: values.ca_cert } : {}),
              ...(values.auth_type === 'basic'
                ? { username: values.username, password: values.password }
                : {}),
              ...(values.auth_type === 'api_key' ? { api_key: values.api_key } : {}),
            }
            : {
              host: values.host,
              port: values.port,
              database: values.database,
              username: values.username,
              password: values.password,
            };
      const payload: DataConnectionTestPayload = {
        connection_type: connectionType,
        config,
      };

      if (currentRow) {
        await testDataConnectionDraft(currentRow.id, payload);
      } else {
        await testDataConnectionConfig(payload);
      }
      message.success(t('dataSource.testConnectionSuccess'));
    } catch (error: unknown) {
      if (
        typeof error === 'object' &&
        error !== null &&
        'errorFields' in error
      ) {
        return;
      }
      if (error instanceof HandledRequestError && error.status !== undefined) {
        return;
      }
      message.error(
        error instanceof Error
          ? error.message
          : t('dataSource.testConnectionFailed'),
      );
    } finally {
      setTestConnectionLoading(false);
    }
  };

  const onFinish = async (values: any) => {
    try {
      setLoading(true);
      const type = values.connection_type as DataConnectionType;
      let config: Record<string, any> = {};
      if (type === 'rest_api') {
        config = {
          base_url: values.base_url,
          headers: parseJsonObject(
            values.headersText,
            `${t('dataSource.headers')}${t('dataSource.jsonObjectRequired')}`,
          ),
        };
      } else if (type === 'elasticsearch') {
        const esAuth = values.auth_type || 'none';
        config = {
          url: values.url,
          auth_type: esAuth,
          timeout_seconds: values.timeout_seconds ?? 30,
          index: values.index,
        };
        if (String(values.ca_cert || '').trim()) {
          config.ca_cert = values.ca_cert;
        }
        if (esAuth === 'basic') {
          config.username = values.username;
          config.password =
            currentRow &&
            (!values.password?.trim() || values.password === PASSWORD_PLACEHOLDER)
              ? PASSWORD_PLACEHOLDER
              : values.password;
        }
        if (esAuth === 'api_key') {
          config.api_key =
            currentRow &&
            (!values.api_key?.trim() || values.api_key === PASSWORD_PLACEHOLDER)
              ? PASSWORD_PLACEHOLDER
              : values.api_key;
        }
      } else {
        config = {
          host: values.host,
          port: values.port,
          database: values.database,
          username: values.username,
          password: values.password,
        };
        if (
          currentRow &&
          (!values.password?.trim() || values.password === PASSWORD_PLACEHOLDER)
        ) {
          config.password = PASSWORD_PLACEHOLDER;
        }
      }

      const payload = {
        name: values.name.trim(),
        connection_type: type,
        description: values.description || '',
        groups: values.groups || [],
        is_active: values.is_active !== false,
        config,
      };

      if (currentRow && isSensitiveEndpointChanged(type, config)) {
        let refCount = currentRow.reference_count || 0;
        try {
          const refs = await getDataConnectionReferences(currentRow.id);
          refCount = Array.isArray(refs) ? refs.length : refCount;
        } catch {
          // keep list count
        }
        setLoading(false);
        Modal.confirm({
          title: t('dataConnection.editImpactTitle'),
          content: t(
            'dataConnection.editImpactContent',
            '将影响 {count} 个引用该连接的数据源，修改后后续取数立即使用新配置。',
            { count: refCount },
          ),
          okText: t('common.confirm'),
          cancelText: t('common.cancel'),
          centered: true,
          onOk: async () => {
            setLoading(true);
            try {
              await persist(payload);
            } catch (error: any) {
              message.error(
                error?.message || t('dataConnection.operationFailed'),
              );
            } finally {
              setLoading(false);
            }
          },
        });
        return;
      }

      await persist(payload);
    } catch (error: any) {
      message.error(error?.message || t('dataConnection.operationFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer
      title={
        currentRow
          ? `${t('common.edit')}${t('dataConnection.introTitle')} - ${currentRow.name}`
          : `${t('common.add')}${t('dataConnection.introTitle')}`
      }
      placement="right"
      width={600}
      open={open}
      maskClosable={false}
      onClose={handleClose}
      destroyOnClose
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button
            loading={testConnectionLoading}
            disabled={loading}
            onClick={handleTestConnection}
          >
            {t('dataSource.testConnection')}
          </Button>
          <Button
            type="primary"
            loading={loading}
            disabled={testConnectionLoading}
            style={{ marginLeft: 8 }}
            onClick={() => form.submit()}
          >
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={handleClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form form={form} layout="vertical" onFinish={onFinish}>
        <Form.Item
          name="name"
          label={t('dataConnection.name')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name="connection_type"
          label={t('dataConnection.type')}
          rules={[{ required: true, message: t('common.selectMsg') }]}
        >
          <Radio.Group disabled={!!currentRow}>
            <Radio.Button value="mysql">MySQL</Radio.Button>
            <Radio.Button value="postgresql">PostgreSQL</Radio.Button>
            <Radio.Button value="rest_api">REST API</Radio.Button>
            <Radio.Button value="elasticsearch">Elasticsearch</Radio.Button>
          </Radio.Group>
        </Form.Item>
        <Form.Item
          name="groups"
          label={t('common.group')}
          rules={[{ required: true, message: t('common.selectMsg') }]}
        >
          <GroupTreeSelect
            placeholder={`${t('common.selectMsg')}${t('common.group')}`}
            multiple={true}
            mode="ownership"
          />
        </Form.Item>
        <Form.Item
          name="is_active"
          label={t('dataConnection.enabled')}
          valuePropName="checked"
          initialValue={true}
        >
          <Switch />
        </Form.Item>
        <Form.Item name="description" label={t('dataConnection.describe')}>
          <Input.TextArea
            rows={4}
            placeholder={`${t('common.inputMsg')}${t('dataConnection.describe')}`}
          />
        </Form.Item>

        {connectionType === 'elasticsearch' ? (
          <>
            <Form.Item
              name="url"
              label={t('dataSource.url')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder="https://es.example.com:9200" />
            </Form.Item>
            <Form.Item
              name="index"
              label={t('dataSource.index')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder="logs-*" />
            </Form.Item>
            <Form.Item name="auth_type" label={t('dataSource.authType')} initialValue="none">
              <Radio.Group>
                <Radio.Button value="none">{t('dataSource.authTypes.none')}</Radio.Button>
                <Radio.Button value="basic">{t('dataSource.authTypes.basic')}</Radio.Button>
                <Radio.Button value="api_key">{t('dataSource.authTypes.apiKey')}</Radio.Button>
              </Radio.Group>
            </Form.Item>
            {authType === 'basic' ? (
              <>
                <Form.Item
                  name="username"
                  label={t('dataSource.username')}
                  rules={[{ required: true, message: t('common.inputMsg') }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="password"
                  label={t('dataSource.password')}
                  rules={[{ required: true, message: t('common.inputMsg') }]}
                >
                  <Input.Password
                    autoComplete="new-password"
                    onFocus={handlePasswordFocus}
                    onBlur={handlePasswordBlur}
                  />
                </Form.Item>
              </>
            ) : null}
            {authType === 'api_key' ? (
              <Form.Item
                name="api_key"
                label={t('dataSource.apiKey')}
                rules={[{ required: true, message: t('common.inputMsg') }]}
              >
                <Input.Password
                  autoComplete="new-password"
                  onFocus={(event) => {
                    if (!currentRow) return;
                    if (event.target.value === PASSWORD_PLACEHOLDER) {
                      form.setFieldValue('api_key', '');
                    }
                  }}
                  onBlur={(event) => {
                    if (!currentRow) return;
                    if (!event.target.value?.trim()) {
                      form.setFieldValue('api_key', PASSWORD_PLACEHOLDER);
                    }
                  }}
                />
              </Form.Item>
            ) : null}
            <Form.Item name="timeout_seconds" label={t('dataSource.timeout')} initialValue={30}>
              <InputNumber className="w-full" min={1} max={60} />
            </Form.Item>
            <Form.Item name="ca_cert" label={t('dataSource.caCert')}>
              <Input.TextArea
                rows={4}
                placeholder={'-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'}
              />
            </Form.Item>
          </>
        ) : connectionType === 'rest_api' ? (
          <>
            <Form.Item
              name="base_url"
              label={t('dataConnection.baseUrl')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder="https://api.example.com" />
            </Form.Item>
            <Form.Item name="headersText" label={t('dataSource.headers')}>
              <Input.TextArea
                rows={4}
                placeholder='{"Authorization":"Bearer ..."}'
              />
            </Form.Item>
          </>
        ) : (
          <>
            <Form.Item
              name="host"
              label={t('dataSource.host')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t('common.inputMsg')} />
            </Form.Item>
            <Form.Item
              name="port"
              label={t('dataSource.port')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <InputNumber
                className="w-full"
                min={1}
                max={65535}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item
              name="database"
              label={t('dataSource.database')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t('common.inputMsg')} />
            </Form.Item>
            <Form.Item
              name="username"
              label={t('dataSource.username')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t('common.inputMsg')} autoComplete="off" />
            </Form.Item>
            <Form.Item
              name="password"
              label={t('dataSource.password')}
              rules={[{ required: !currentRow, message: t('common.inputMsg') }]}
            >
              <Input.Password
                placeholder={t('common.inputMsg')}
                autoComplete="new-password"
                onFocus={handlePasswordFocus}
                onBlur={handlePasswordBlur}
              />
            </Form.Item>
          </>
        )}
      </Form>
    </Drawer>
  );
};

export default OperateModal;
