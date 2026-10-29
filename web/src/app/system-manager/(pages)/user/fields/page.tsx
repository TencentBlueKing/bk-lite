'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Form, Input, Popconfirm, Select, Space, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import SystemManagerFillTable from '@/app/system-manager/components/system-manager-fill-table';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';

interface UserFieldRow {
  id: number;
  name: string;
  key: string;
  field_type: 'text' | 'number' | 'date';
  description: string;
  is_enabled: boolean;
  has_values: boolean;
  mapped: boolean;
}

const UserFieldsPage: React.FC = () => {
  const { t } = useTranslation();
  const { get, post } = useApiClient();
  const [rows, setRows] = useState<UserFieldRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<UserFieldRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const typeOptions = [
    { value: 'text', label: t('system.user.fields.typeText') },
    { value: 'number', label: t('system.user.fields.typeNumber') },
    { value: 'date', label: t('system.user.fields.typeDate') },
  ];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await get<UserFieldRow[]>('/system_mgmt/user_field/search/');
      setRows(Array.isArray(data) ? data : []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [get]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ field_type: 'text' });
    setOpen(true);
  };

  const openEdit = (record: UserFieldRow) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      key: record.key,
      field_type: record.field_type,
      description: record.description,
    });
    setOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await post('/system_mgmt/user_field/update_field/', {
          id: editing.id,
          name: values.name,
          key: values.key,
          field_type: values.field_type,
          description: values.description || '',
        });
      } else {
        await post('/system_mgmt/user_field/create_field/', {
          name: values.name,
          key: values.key,
          field_type: values.field_type,
          description: values.description || '',
        });
      }
      message.success(t('common.saveSuccess'));
      setOpen(false);
      await load();
    } catch {
      // 请求层已经提示后端返回的原因。
    } finally {
      setSaving(false);
    }
  };

  const handleDisable = async (record: UserFieldRow) => {
    try {
      await post('/system_mgmt/user_field/disable_field/', { id: record.id });
      message.success(t('common.updateSuccess'));
      await load();
    } catch {
      // 请求层已经提示后端返回的原因。
    }
  };

  const handleDelete = async (record: UserFieldRow) => {
    try {
      await post('/system_mgmt/user_field/delete_field/', { id: record.id });
      message.success(t('common.delSuccess'));
      await load();
    } catch {
      // 请求层已经提示后端返回的原因。
    }
  };

  const typeLocked = Boolean(editing && (editing.has_values || editing.mapped));

  const columns = [
    { title: t('common.name'), dataIndex: 'name', key: 'name' },
    { title: t('system.user.fields.key'), dataIndex: 'key', key: 'key' },
    {
      title: t('system.user.fields.type'),
      dataIndex: 'field_type',
      key: 'field_type',
      width: 100,
      render: (value: UserFieldRow['field_type']) =>
        typeOptions.find((item) => item.value === value)?.label || value,
    },
    { title: t('system.user.fields.description'), dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: t('system.user.table.status'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 100,
      render: (value: boolean) => (value ? t('system.user.fields.enabled') : t('system.user.fields.disabled')),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 180,
      render: (_: unknown, record: UserFieldRow) => (
        <Space>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button type="link" size="small" onClick={() => openEdit(record)}>
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          {record.is_enabled ? (
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Popconfirm
                title={t('system.user.fields.disableConfirm')}
                onConfirm={() => handleDisable(record)}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
              >
                <Button type="link" size="small">
                  {t('system.user.fields.disable')}
                </Button>
              </Popconfirm>
            </PermissionWrapper>
          ) : null}
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('system.user.fields.deleteConfirm')}
              onConfirm={() => handleDelete(record)}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
            >
              <Button type="link" size="small" danger disabled={record.has_values || record.mapped}>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-4 shrink-0">
        <TopSection title={t('system.user.fields.title')} content={t('system.user.fields.content')} />
      </div>
      <section className="flex min-h-0 flex-1 flex-col rounded-md bg-(--color-bg) p-4">
        <div className="mb-4 flex shrink-0 justify-end">
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {t('common.new')}
            </Button>
          </PermissionWrapper>
        </div>
        <SystemManagerFillTable>
          <CustomTable<UserFieldRow>
            dataSource={rows}
            columns={columns}
            loading={loading}
            rowKey="id"
            pagination={false}
          />
        </SystemManagerFillTable>
      </section>
      <OperateModal
        title={editing ? t('common.edit') : t('common.new')}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="key"
            label={t('system.user.fields.key')}
            rules={[{ required: true, pattern: /^[A-Za-z][A-Za-z0-9_]{0,63}$/, message: t('system.user.fields.keyPlaceholder') }]}
          >
            <Input disabled={Boolean(editing)} placeholder={t('system.user.fields.keyPlaceholder')} />
          </Form.Item>
          <Form.Item name="field_type" label={t('system.user.fields.type')} rules={[{ required: true }]}>
            <Select options={typeOptions} disabled={typeLocked} />
          </Form.Item>
          <Form.Item name="description" label={t('system.user.fields.description')}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
};

export default UserFieldsPage;
