'use client';

import React, { useEffect } from 'react';
import GroupTreeSelect from '@/components/group-tree-select';
import { Drawer, Form, Input, InputNumber, Button, message, Modal, Radio, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { useUserInfoContext } from '@/context/userInfo';
import {
  DataConnectionOperateModalProps,
  DataConnectionType,
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
  const { selectedGroup } = useUserInfoContext();
  const {
    createDataConnection,
    updateDataConnection,
    getDataConnectionReferences,
  } = useDataConnectionApi();
  const connectionType = (Form.useWatch('connection_type', form) ||
    'mysql') as DataConnectionType;
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
          <Button type="primary" loading={loading} onClick={() => form.submit()}>
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

        {connectionType === 'rest_api' ? (
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
