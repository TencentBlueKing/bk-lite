// Route: /system-manager/user/login-auth
'use client';

import React, { useEffect, useState } from 'react';
import {
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Popconfirm,
  Select,
  Space,
  Switch,
} from 'antd';
import CustomTable from '@/components/custom-table';
import Icon from '@/components/icon';
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from '@/components/permission';
import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import IconFontSelector from '@/app/system-manager/components/user/IconFontSelector';
import {
  useLoginAuthApi,
  type LoginAuthBindingPayload,
  type AvailableInstance,
  type LoginAuthBinding,
} from '@/app/system-manager/api/login-auth';
import { useTranslation } from '@/utils/i18n';
import { formatIntegrationInstanceDisplayName } from '@/app/system-manager/utils/intergrationCenter';
import { ColumnItem } from '@/types';

const LoginAuthPage: React.FC = () => {
  const { t } = useTranslation();
  const {
    getLoginAuthBindings,
    createLoginAuthBinding,
    updateLoginAuthBinding,
    deleteLoginAuthBinding,
    getAvailableInstances,
  } = useLoginAuthApi();
  const [form] = Form.useForm();

  const [bindings, setBindings] = useState<LoginAuthBinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sorting, setSorting] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editingBinding, setEditingBinding] = useState<LoginAuthBinding | null>(null);
  const [selectedIcon, setSelectedIcon] = useState<string>('');
  const [availableInstances, setAvailableInstances] = useState<AvailableInstance[]>([]);
  const [unmatchedAction, setUnmatchedAction] = useState<string>('deny');
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 10,
  });
  const builtinProviderKey = 'bk_lite_builtin';
  const attachProviderKeys = (
    items: LoginAuthBinding[],
    instances: AvailableInstance[] = availableInstances
  ) => items.map((item) => ({
    ...item,
    provider_key:
      item.provider_key ||
      instances.find((instance) => instance.id === item.integration_instance)?.provider_key,
  }));

  const fetchBindings = async (page = pagination.current, pageSize = pagination.pageSize) => {
    try {
      setLoading(true);
      const { count, items } = await getLoginAuthBindings({
        page,
        page_size: pageSize,
      });
      setPagination((prev) => ({
        ...prev,
        current: page,
        pageSize,
        total: count,
      }));
      setBindings(attachProviderKeys(items));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const fetchAvailableInstances = async () => {
    try {
      const data = await getAvailableInstances();
      const nextInstances = data || [];
      setAvailableInstances(nextInstances);
      setBindings((prev) => attachProviderKeys(prev, nextInstances));
    } catch {
      setAvailableInstances([]);
    }
  };

  useEffect(() => {
    fetchBindings();
    fetchAvailableInstances();
  }, []);

  const getBindingProviderKey = (binding: LoginAuthBinding) => {
    if (binding.provider_key) return binding.provider_key;
    return availableInstances.find((item) => item.id === binding.integration_instance)?.provider_key || '';
  };

  const isBuiltinBinding = (binding: LoginAuthBinding) => {
    const key = getBindingProviderKey(binding);
    if (!key) return true;
    return getBindingProviderKey(binding) === builtinProviderKey;
  }
  const editingBuiltinBinding = editingBinding ? isBuiltinBinding(editingBinding) : false;

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      await Promise.all([fetchBindings(), fetchAvailableInstances()]);
    } finally {
      setRefreshing(false);
    }
  };

  const handleTableChange = (page: number, pageSize: number) => {
    fetchBindings(page, pageSize);
  };

  const reorderBindingsWithPageOrder = (items: LoginAuthBinding[]) => {
    const baseOrder = (pagination.current - 1) * pagination.pageSize + 1;
    return items.map((item, index) => ({
      ...item,
      order: baseOrder + index,
    }));
  };

  const handleRowDragEnd = async (
    targetTableData: LoginAuthBinding[] | undefined,
  ) => {
    if (!targetTableData) return;

    const reorderedBindings = reorderBindingsWithPageOrder(targetTableData);
    const previousOrderMap = new Map(bindings.map((item) => [item.id, item.order]));
    const changedBindings = reorderedBindings.filter((item) => item.order !== previousOrderMap.get(item.id));
    if (changedBindings.length === 0) return;

    const previousBindings = bindings;
    setBindings(reorderedBindings);
    setSorting(true);

    try {
      await Promise.all(
        changedBindings.map((item) =>
          updateLoginAuthBinding(item.id, { order: item.order })
        )
      );
      await fetchBindings();
    } catch {
      setBindings(previousBindings);
      message.error(t('common.saveFailed'));
    } finally {
      setSorting(false);
    }
  };

  const handleAdd = () => {
    setEditingBinding(null);
    setSelectedIcon('');
    setUnmatchedAction('deny');
    form.resetFields();
    form.setFieldsValue({
      unmatched_user_action: 'deny',
      icon: '',
    });
    fetchAvailableInstances();
    setModalVisible(true);
  };

  const handleEdit = (record: LoginAuthBinding) => {
    setEditingBinding(record);
    setSelectedIcon(record.icon || '');
    setUnmatchedAction(record.unmatched_user_action);
    form.setFieldsValue({
      name: record.name,
      integration_instance: record.integration_instance,
      order: record.order,
      icon: record.icon,
      description: record.description,
      external_field: record.external_field,
      platform_field: record.platform_field,
      unmatched_user_action: record.unmatched_user_action,
      default_group_name: record.default_group_name,
    });
    fetchAvailableInstances();
    setModalVisible(true);
  };

  const handleToggleEnabled = async (record: LoginAuthBinding, checked: boolean) => {
    if (isBuiltinBinding(record)) return;
    try {
      await updateLoginAuthBinding(record.id, { enabled: checked });
      setBindings(prev =>
        prev.map(b => (b.id === record.id ? { ...b, enabled: checked } : b))
      );
    } catch {
      message.error(t('common.operationFailed'));
    }
  };

  const handleDelete = async (record: LoginAuthBinding) => {
    try {
      await deleteLoginAuthBinding(record.id);
      message.success(t('common.delSuccess'));
      await fetchBindings();
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      if (editingBinding) {
        const payload: Partial<LoginAuthBindingPayload> = editingBuiltinBinding
          ? {
            name: values.name.trim(),
            icon: values.icon || '',
            description: values.description || '',
            order: values.order,
          }
          : {
            name: values.name.trim(),
            integration_instance: values.integration_instance,
            icon: values.icon || '',
            description: values.description || '',
            order: values.order,
            external_field: values.external_field.trim(),
            platform_field: values.platform_field,
            unmatched_user_action: values.unmatched_user_action,
            default_group_name: values.unmatched_user_action === 'create'
              ? values.default_group_name?.trim() || ''
              : '',
          };
        const updated = await updateLoginAuthBinding(editingBinding.id, payload);
        setBindings(prev =>
          prev.map(b => (b.id === editingBinding.id ? { ...b, ...updated } : b))
        );
        message.success(t('common.saveSuccess'));
      } else {
        const payload: LoginAuthBindingPayload = {
          name: values.name.trim(),
          integration_instance: values.integration_instance,
          icon: values.icon || '',
          description: values.description || '',
          order: values.order,
          external_field: values.external_field.trim(),
          platform_field: values.platform_field,
          unmatched_user_action: values.unmatched_user_action,
          default_group_name: values.unmatched_user_action === 'create'
            ? values.default_group_name?.trim() || ''
            : '',
        };
        await createLoginAuthBinding(payload);
        message.success(t('common.addSuccess'));
        await fetchBindings();
      }
      setModalVisible(false);
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error(t('common.operationFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleModalCancel = () => {
    if (modalLoading) return;
    setModalVisible(false);
  };

  const handleIconChange = (iconName: string) => {
    setSelectedIcon(iconName);
    form.setFieldValue('icon', iconName);
  };

  const handleUnmatchedActionChange = (value: string) => {
    setUnmatchedAction(value);
    if (value !== 'create') {
      form.setFieldValue('default_group_name', '');
    }
  };

  const columns: ColumnItem[] = [
    {
      key: 'name',
      title: t('system.user.loginAuthPage.name'),
      dataIndex: 'name',
      render: (_, record) => {
        return (
          <div className='flex content-center'>
            <div className='w-[26px] mr-2 flex justify-center items-center'>
              {
                record.icon
                  ? <Icon type={record.icon} className="w-[26px]! h-[26px]!" />
                  : ''
              }
            </div>
            <div>
              <p className='font-semibold'>{record.name}</p>
              <span className='text-xs text-[var(--color-text-3)]'>{t(`system.user.loginAuthPage.currentOrder`)}：{record.order}</span>
            </div>
          </div>
        )
      }
    },
    {
      key: 'integration_instance_name',
      title: t('system.user.loginAuthPage.integratedSystems'),
      dataIndex: 'integration_instance_name',
      render: (_, record) => {
        if(record.provider_key && record.provider_key !== "bk_lite_builtin")
          return (<>{record.integration_instance_name} / {t(`system.integrationCenter.provider.${record.provider_key}`)}</>)
        return (<>{record.integration_instance_name}</>)
      }
    },
    {
      key: 'description',
      title: t('system.user.loginAuthPage.description'),
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      key: 'enabled',
      title: t('system.user.loginAuthPage.enabled'),
      dataIndex: 'enabled',
      render: (enabled: boolean, record) => (
        <Switch
          size="small"
          checked={isBuiltinBinding(record) ? true : enabled}
          disabled={isBuiltinBinding(record)}
          onChange={checked => handleToggleEnabled(record, checked)}
        />
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      dataIndex: 'actions',
      fixed: 'right',
      render: (_, record) => {
        const builtin = isBuiltinBinding(record);
        return (
          <Space>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                disabled={builtin}
                onClick={builtin ? undefined : () => handleEdit(record)}
              >
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Delete']}>
              {builtin ? (
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled
                >
                  {t('common.delete')}
                </Button>
              ) : (
                <Popconfirm
                  title={t('system.user.loginAuthPage.deleteConfirm')}
                  onConfirm={() => handleDelete(record)}
                >
                  <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              )}
            </PermissionWrapper>
          </Space>
        );
      },
    },
  ];

  return (
    <>
      <PageLayout
        height="calc(100vh - 260px)"
        topSection={
          <TopSection
            title={t('system.user.loginAuth')}
            content={t('system.user.loginAuthPage.pageDesc')}
          />
        }
        rightSection={
          <div className="flex h-full flex-col  bg-[var(--color-bg-1)] p-1">
            <div className="mb-2 flex flex-wrap items-start justify-end border-[var(--color-border-1)] pb-4">
              <div className="flex flex-wrap items-center gap-2">
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    {t('common.add')}
                  </Button>
                </PermissionWrapper>
                <Button type='text' icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing} />
              </div>
            </div>

            <div className="min-h-0 flex-1 bg-[var(--color-bg)] p-1">
              <CustomTable
                rowKey="id"
                loading={loading || sorting}
                columns={columns}
                dataSource={bindings}
                rowDraggable
                onRowDragEnd={(targetTableData) => handleRowDragEnd(targetTableData as LoginAuthBinding[] | undefined)}
                pagination={{
                  current: pagination.current,
                  total: pagination.total,
                  pageSize: pagination.pageSize,
                  showSizeChanger: true,
                  onChange: handleTableChange,
                }}
              />
            </div>
          </div>
        }
      />

      <OperateModal
        title={editingBinding ? t('common.edit') : t('common.add')}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={handleModalCancel}
        confirmLoading={modalLoading}
        width={600}
      >
        <Form form={form} layout="vertical">
          <div className="mb-6">
            <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
              {t('system.user.loginAuthPage.basicInfoTitle')}
            </div>
            <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
              {t('system.user.loginAuthPage.basicInfoDesc')}
            </div>
            <Form.Item
              name="name"
              label={t('system.user.loginAuthPage.name')}
              rules={[{ required: true, whitespace: true }]}
            >
              <Input placeholder={t('system.user.loginAuthPage.namePlaceholder')} />
            </Form.Item>
            {editingBuiltinBinding ? (
              <Form.Item label={t('system.user.loginAuthPage.integratedSystems')}>
                <Input value={editingBinding.integration_instance_name} disabled />
              </Form.Item>
            ) : (
              <Form.Item
                name="integration_instance"
                label={t('system.user.loginAuthPage.integratedSystems')}
                rules={[{ required: true }]}
              >
                <Select
                  placeholder={t('system.user.loginAuthPage.integrationInstancePlaceholder')}
                  options={availableInstances.map((i) => ({
                    value: i.id,
                    label: formatIntegrationInstanceDisplayName(i, t),
                  }))}
                />
              </Form.Item>
            )}
            <Form.Item
              label={t(`system.user.loginAuthPage.icon`)}
              name="icon"
              layout='horizontal'
              rules={[{ required: true, whitespace: true }]}
            >
              <div className="flex justify-start items-center">
                <IconFontSelector
                  value={selectedIcon}
                  onChange={handleIconChange}
                  variant="square"
                />
              </div>
            </Form.Item>

            <Form.Item
              name="description"
              label={t('system.user.loginAuthPage.description')}
            >
              <Input.TextArea rows={3} placeholder={t('system.user.loginAuthPage.descriptionPlaceholder')} />
            </Form.Item>
            {editingBinding ? (
              <Form.Item
                name="order"
                label={t('system.user.loginAuthPage.order')}
                rules={[{ required: true }]}
              >
                <InputNumber min={1} precision={0} className="w-full" />
              </Form.Item>
            ) : null}
          </div>

          {!editingBuiltinBinding ? (
            <div className="border-t border-[var(--color-border-1)] pt-6">
              <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
                {t('system.user.loginAuthPage.accountMatchingTitle')}
              </div>
              <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
                {t('system.user.loginAuthPage.accountMatchingDesc')}
              </div>
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
                <div className="mb-4 font-semibold text-[var(--color-text-1)]">
                  {t('system.user.loginAuthPage.fieldMappingTitle')}
                </div>
                <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 gap-y-3 text-[13px] text-[var(--color-text-3)]">
                  <div>{t('system.user.loginAuthPage.platformField')}</div>
                  <div />
                  <div>{t('system.user.loginAuthPage.externalField')}</div>
                </div>
                <div className="mt-3 grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 gap-y-3">
                  <Form.Item
                    name="platform_field"
                    rules={[{ required: true }]}
                    className="mb-0"
                  >
                    <Select
                      options={[
                        { value: 'username', label: t('system.user.loginAuthPage.platformUsername') },
                        { value: 'phone', label: t('system.user.loginAuthPage.platformPhone') },
                        { value: 'email', label: t('system.user.loginAuthPage.platformEmail') },
                      ]}
                    />
                  </Form.Item>
                  <div className="flex h-10 items-center justify-center text-lg text-[var(--color-primary)]">
                    =
                  </div>
                  <Form.Item
                    name="external_field"
                    rules={[{ required: true, whitespace: true }]}
                    className="mb-0"
                  >
                    <Input placeholder={t('system.user.loginAuthPage.externalFieldPlaceholder')} />
                  </Form.Item>
                </div>
                <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
                  {t('system.user.loginAuthPage.fieldMappingDesc')}
                </div>
              </div>
              <Form.Item
                name="unmatched_user_action"
                label={t('system.user.loginAuthPage.unmatchedUserAction')}
                initialValue="deny"
                className="mt-5"
              >
                <Select
                  options={[
                    { value: 'deny', label: t('system.user.loginAuthPage.actionDeny') },
                    { value: 'create', label: t('system.user.loginAuthPage.actionCreate') },
                  ]}
                  onChange={handleUnmatchedActionChange}
                />
              </Form.Item>
              {unmatchedAction === 'create' && (
                <Form.Item
                  name="default_group_name"
                  label={t('system.user.loginAuthPage.defaultGroupName')}
                  rules={[{ required: true, whitespace: true }]}
                >
                  <Input placeholder={t('system.user.loginAuthPage.defaultGroupNamePlaceholder')} />
                </Form.Item>
              )}
            </div>
          ) : null}
        </Form>
      </OperateModal>
    </>
  );
};

export default LoginAuthPage;
