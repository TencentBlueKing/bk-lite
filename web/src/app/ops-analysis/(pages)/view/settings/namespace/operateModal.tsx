'use client';

import React, { useEffect } from 'react';
import { Drawer, Form, Input, Button, message, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { NamespaceOperateModalProps } from '@/app/ops-analysis/types/namespace';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';

const OperateModal: React.FC<NamespaceOperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const { createNamespace, updateNamespace } = useNamespaceApi();

  useEffect(() => {
    if (!open) return;

    form.resetFields();

    if (currentRow) {
      form.setFieldsValue(currentRow);
    }
  }, [open, currentRow, form]);

  const onFinish = async (values: any) => {
    try {
      setLoading(true);

      const submitData = {
        name: values.name,
        account: values.account,
        password: values.password,
        domain: values.domain,
        namespace: values.namespace,
        enable_tls: values.enable_tls || false,
        desc: values.desc || '',
      };

      if (currentRow) {
        await updateNamespace(currentRow.id, submitData);
        message.success(t('namespace.updateNamespaceSuccess'));
      } else {
        await createNamespace(submitData);
        message.success(t('namespace.createNamespaceSuccess'));
      }

      onClose();
      onSuccess && onSuccess();
    } catch (error: any) {
      message.error(error.message || t('namespace.operationFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer
      title={
        currentRow
          ? `${t('common.edit')}${t('namespace.title')} - ${currentRow.name}`
          : `${t('common.add')}${t('namespace.title')}`
      }
      placement="right"
      width={600}
      open={open}
      onClose={onClose}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button
            type="primary"
            loading={loading}
            onClick={() => form.submit()}
          >
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={onClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        labelCol={{ span: 4 }}
        layout="horizontal"
        onFinish={onFinish}
      >
        <Form.Item
          name="name"
          label={t('namespace.name')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>

        <Form.Item
          name="account"
          label={t('namespace.account')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} autoComplete="off" />
        </Form.Item>

        <Form.Item
          name="password"
          label={t('namespace.password')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input.Password
            placeholder={t('common.inputMsg')}
            autoComplete="new-password"
          />
        </Form.Item>

        <Form.Item
          name="domain"
          label={t('namespace.domain')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>

        <Form.Item
          name="namespace"
          label={t('namespace.title')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>

        <Form.Item
          name="enable_tls"
          label={t('namespace.tls')}
          valuePropName="checked"
          initialValue={false}
        >
          <Switch />
        </Form.Item>

        <Form.Item name="desc" label={t('namespace.describe')}>
          <Input.TextArea placeholder={t('common.inputMsg')} rows={4} />
        </Form.Item>
      </Form>
    </Drawer>
  );
};

export default OperateModal;