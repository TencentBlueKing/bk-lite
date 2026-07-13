'use client';
import React, { useState, useEffect } from 'react';
import { Button, Table, Space, Popconfirm, message, Spin, Modal, Form, Input, Switch } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import { NetworkWhiteListItem, useSettingsApi } from '@/app/system-manager/api/settings';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const NetworkWhitelistPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchNetworkWhiteList, createNetworkWhiteList, updateNetworkWhiteList, deleteNetworkWhiteList } = useSettingsApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [dataSource, setDataSource] = useState<NetworkWhiteListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NetworkWhiteListItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchNetworkWhiteList();
      setDataSource(Array.isArray(data) ? data : []);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true });
    setModalOpen(true);
  };

  const openEdit = (record: NetworkWhiteListItem) => {
    setEditing(record);
    form.setFieldsValue({ network: record.network, remark: record.remark, enabled: record.enabled });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updateNetworkWhiteList(editing.id, values);
      } else {
        await createNetworkWhiteList(values);
      }
      message.success(t('common.updateSuccess'));
      setModalOpen(false);
      fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteNetworkWhiteList(id);
      setDataSource((prev) => prev.filter((item) => item.id !== id));
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const columns = [
    { title: t('system.settings.networkWhitelist.network'), dataIndex: 'network', key: 'network', width: 220 },
    { title: t('system.settings.networkWhitelist.remark'), dataIndex: 'remark', key: 'remark', ellipsis: true },
    {
      title: t('system.settings.networkWhitelist.enabled'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 100,
      render: (v: boolean) => (v ? t('common.yes') : t('common.no')),
    },
    {
      title: t('system.settings.networkWhitelist.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (text: string) => (text ? convertToLocalizedTime(text) : '-'),
    },
    {
      title: '',
      key: 'action',
      width: 100,
      render: (_: unknown, record: NetworkWhiteListItem) => (
        <Space size={0}>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('system.settings.networkWhitelist.deleteConfirm')}
              onConfirm={() => handleDelete(record.id)}
              okText={t('common.yes')}
              cancelText={t('common.no')}
            >
              <Button type="text" icon={<DeleteOutlined />} danger />
            </Popconfirm>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="mb-4">
        <TopSection
          title={t('system.settings.networkWhitelist.title')}
          content={t('system.settings.networkWhitelist.content')}
        />
      </div>
      <section className="rounded-md bg-(--color-bg) p-4" style={{ height: 'calc(100vh - 235px)' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px' }}>
            <Spin />
          </div>
        ) : (
          <>
            <div className="flex justify-end mb-4">
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  {t('system.settings.networkWhitelist.add')}
                </Button>
              </PermissionWrapper>
            </div>
            <Table dataSource={dataSource} columns={columns} pagination={false} rowKey="id" />
          </>
        )}
      </section>

      <Modal
        title={editing ? t('system.settings.networkWhitelist.edit') : t('system.settings.networkWhitelist.add')}
        open={modalOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="network"
            label={t('system.settings.networkWhitelist.network')}
            rules={[{ required: true, message: t('system.settings.networkWhitelist.networkRequired') }]}
            extra={t('system.settings.networkWhitelist.metadataHint')}
          >
            <Input placeholder={t('system.settings.networkWhitelist.networkPlaceholder')} />
          </Form.Item>
          <Form.Item name="remark" label={t('system.settings.networkWhitelist.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="enabled" label={t('system.settings.networkWhitelist.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default NetworkWhitelistPage;
