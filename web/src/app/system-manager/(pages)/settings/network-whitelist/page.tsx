'use client';
import React, { useState, useEffect } from 'react';
import { Button, Space, Popconfirm, message, Form } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import { NetworkWhiteListItem, useSettingsApi } from '@/app/system-manager/api/settings';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import NetworkWhitelistFormModal, {
  type NetworkWhitelistEntryType,
} from '@/app/system-manager/components/network-whitelist-form-modal';

const DEFAULT_PAGE_SIZE = 10;

const NetworkWhitelistPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchNetworkWhiteList, createNetworkWhiteList, updateNetworkWhiteList, deleteNetworkWhiteList } = useSettingsApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [dataSource, setDataSource] = useState<NetworkWhiteListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: DEFAULT_PAGE_SIZE, total: 0 });
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NetworkWhiteListItem | null>(null);
  const [saving, setSaving] = useState(false);
  // 'cidr' | 'domain' — 表单当前展示哪种条目类型,创建时可改,编辑时锁定
  const [entryType, setEntryType] = useState<NetworkWhitelistEntryType>('cidr');
  const [form] = Form.useForm();

  const fetchData = async (page = pagination.current, pageSize = pagination.pageSize) => {
    setLoading(true);
    try {
      const response = await fetchNetworkWhiteList(page, pageSize);
      setDataSource((response.items || []).filter((item) => !item.is_build_in));
      setPagination({ current: page, pageSize, total: response.count || 0 });
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData(1, DEFAULT_PAGE_SIZE);
  }, []);

  const openCreate = () => {
    setEditing(null);
    setEntryType('cidr');
    form.resetFields();
    form.setFieldsValue({ enabled: true });
    setModalOpen(true);
  };

  const openEdit = (record: NetworkWhiteListItem) => {
    setEditing(record);
    setEntryType(record.domain_name ? 'domain' : 'cidr');
    form.setFieldsValue({
      network: record.network,
      domain_name: record.domain_name,
      remark: record.remark,
      enabled: record.enabled,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    // entryType 控制的字段如果切换过模式,另一个已被清空,所以只发当前模式的字段
    const payload =
      entryType === 'domain'
        ? {
          domain_name: values.domain_name,
          remark: values.remark,
          enabled: values.enabled,
        }
        : {
          network: values.network,
          remark: values.remark,
          enabled: values.enabled,
        };
    setSaving(true);
    try {
      if (editing) {
        await updateNetworkWhiteList(editing.id, payload);
      } else {
        await createNetworkWhiteList(payload);
      }
      message.success(t('common.updateSuccess'));
      setModalOpen(false);
      await fetchData(editing ? pagination.current : 1, pagination.pageSize);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteNetworkWhiteList(id);
      const targetPage = dataSource.length === 1 && pagination.current > 1 ? pagination.current - 1 : pagination.current;
      await fetchData(targetPage, pagination.pageSize);
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const columns = [
    {
      title: t('system.settings.networkWhitelist.entryType'),
      dataIndex: 'entry_type',
      key: 'entry_type',
      width: 100,
      render: (_: unknown, record: NetworkWhiteListItem) =>
        record.domain_name ? t('system.settings.networkWhitelist.typeDomain') : t('system.settings.networkWhitelist.typeCidr'),
    },
    {
      title: t('system.settings.networkWhitelist.entry'),
      dataIndex: 'entry',
      key: 'entry',
      width: 260,
      render: (_: unknown, record: NetworkWhiteListItem) => record.domain_name || record.network || '-',
    },
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
      render: (_: unknown, record: NetworkWhiteListItem) => record.is_build_in ? null : (
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
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-4 shrink-0">
        <TopSection
          title={t('system.settings.networkWhitelist.title')}
          content={t('system.settings.networkWhitelist.content')}
        />
      </div>
      <section className="flex min-h-0 flex-1 flex-col rounded-md bg-(--color-bg) p-4">
        <div className="mb-4 flex shrink-0 justify-end">
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {t('system.settings.networkWhitelist.add')}
            </Button>
          </PermissionWrapper>
        </div>
        <div className="min-h-0 flex-1">
          <CustomTable<NetworkWhiteListItem>
            dataSource={dataSource}
            columns={columns}
            loading={loading}
            pagination={{
              current: pagination.current,
              pageSize: pagination.pageSize,
              total: pagination.total,
              showSizeChanger: true,
              onChange: (page, pageSize) => {
                const targetPage = pageSize === pagination.pageSize ? page : 1;
                void fetchData(targetPage, pageSize);
              },
            }}
            rowKey="id"
          />
        </div>
      </section>

      <NetworkWhitelistFormModal
        open={modalOpen}
        editing={!!editing}
        entryType={entryType}
        form={form}
        saving={saving}
        onEntryTypeChange={(next) => {
          setEntryType(next);
          if (next === 'domain') {
            form.setFieldValue('network', '');
          } else {
            form.setFieldValue('domain_name', '');
          }
        }}
        onSubmit={handleSave}
        onCancel={() => setModalOpen(false)}
      />
    </div>
  );
};

export default NetworkWhitelistPage;
