'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Button,
  Input,
  Select,
  Tag,
  Modal,
  message,
  Form,
  Radio,
  Alert,
  Upload,
  InputNumber,
} from 'antd';
import { PlusOutlined, InboxOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import useCloudRegionApi from '@/app/node-manager/api/useCloudRegionApi';
import { Target, WinRMScheme } from '@/app/job/types';
import { ColumnItem } from '@/types';
import GroupTreeSelect from '@/components/group-tree-select';
import SearchCombination from '@/components/search-combination';
import { SearchFilters, FieldConfig } from '@/components/search-combination/types';

const { Dragger } = Upload;

const TargetPage = () => {
  const { t } = useTranslation();
  const { isLoading: isApiReady } = useApiClient();
  const {
    getTargetList,
    createTarget,
    updateTarget,
    deleteTarget,
    testTargetConnection,
  } = useJobApi();
  const { getCloudList } = useCloudRegionApi();

  const [form] = Form.useForm();
  const [data, setData] = useState<Target[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'add' | 'edit'>('add');
  const [editingTarget, setEditingTarget] = useState<Target | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);

  const [cloudRegions, setCloudRegions] = useState<{ id: number; name: string }[]>([]);

  // Form field watchers
  const [sshCredentialType, setSshCredentialType] = useState<'key' | 'password'>('password');
  const osType = Form.useWatch('os_type', form) || 'linux';

  const winrmSchemeOptions = useMemo(
    () => ([
      { label: 'HTTP', value: 'http' as WinRMScheme },
      { label: 'HTTPS', value: 'https' as WinRMScheme },
    ]),
    []
  );

  useEffect(() => {
    if (!modalOpen) {
      return;
    }

    if (osType === 'windows') {
      const nextValues: Record<string, unknown> = {};

      if (form.getFieldValue('winrm_port') === undefined) {
        nextValues.winrm_port = 5985;
      }
      if (!form.getFieldValue('winrm_scheme')) {
        nextValues.winrm_scheme = 'http';
      }

      if (Object.keys(nextValues).length > 0) {
        form.setFieldsValue(nextValues);
      }
      return;
    }

    const nextValues: Record<string, unknown> = {};

    if (form.getFieldValue('ssh_port') === undefined) {
      nextValues.ssh_port = 22;
    }
    if (!form.getFieldValue('ssh_user')) {
      nextValues.ssh_user = 'root';
    }
    if (!form.getFieldValue('ssh_credential_type')) {
      nextValues.ssh_credential_type = 'password';
      setSshCredentialType('password');
    }

    if (Object.keys(nextValues).length > 0) {
      form.setFieldsValue(nextValues);
    }
  }, [form, modalOpen, osType]);

  const fetchCloudRegions = useCallback(async () => {
    try {
      const res = await getCloudList();
      setCloudRegions(Array.isArray(res) ? res : []);
    } catch {
      // error handled by interceptor
    }
  }, []);

  const fetchData = useCallback(
    async (params: { filters?: SearchFilters; current?: number; pageSize?: number } = {}) => {
      setLoading(true);
      try {
        const filters = params.filters ?? searchFilters;
        const queryParams: Record<string, unknown> = {
          page: params.current ?? pagination.current,
          page_size: params.pageSize ?? pagination.pageSize,
        };
        if (filters && Object.keys(filters).length > 0) {
          Object.entries(filters).forEach(([field, conditions]) => {
            conditions.forEach((condition) => {
              if (condition.lookup_expr === 'in' && Array.isArray(condition.value)) {
                queryParams[field] = (condition.value as string[]).join(',');
              } else {
                queryParams[field] = condition.value;
              }
            });
          });
        }
        const res = await getTargetList(queryParams as any);
        setData(res.items || []);
        setPagination((prev) => ({
          ...prev,
          total: res.count || 0,
        }));
      } finally {
        setLoading(false);
      }
    },
    [searchFilters, pagination.current, pagination.pageSize]
  );

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
      fetchCloudRegions();
    }
  }, [isApiReady]);

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [pagination.current, pagination.pageSize]);

  const handleSearchChange = useCallback((filters: SearchFilters) => {
    setSearchFilters(filters);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ filters, current: 1 });
  }, [fetchData]);

  const fieldConfigs: FieldConfig[] = useMemo(() => [
    {
      name: 'name',
      label: t('job.targetName'),
      lookup_expr: 'icontains',
    },
    {
      name: 'ip',
      label: t('job.ipAddress'),
      lookup_expr: 'icontains',
    },
    {
      name: 'cloud_region',
      label: t('job.cloudRegion'),
      lookup_expr: 'icontains',
    },
    {
      name: 'driver',
      label: t('job.executionDriver'),
      lookup_expr: 'in',
      options: [
        { id: 'ansible', name: t('job.driverAnsible') },
        { id: 'ssh', name: t('job.driverSSH') },
        { id: 'sidecar', name: 'Sidecar' },
      ],
    },
    {
      name: 'team',
      label: t('job.organization'),
      lookup_expr: 'icontains',
    },
  ], [t]);

  const handleTableChange = (pag: any) => {
    setPagination(pag);
  };

  const getDriverSelectOptions = () => {
    if (modalType === 'add') {
      return [{ label: t('job.driverAnsible'), value: 'ansible' }];
    }

    const options = [
      { label: t('job.driverAnsible'), value: 'ansible' },
      { label: t('job.driverSSH'), value: 'ssh' },
      { label: 'Sidecar', value: 'sidecar' },
    ];

    const currentDriver = form.getFieldValue('driver');
    if (currentDriver && !options.some((option) => option.value === currentDriver)) {
      return [...options, { label: currentDriver, value: currentDriver }];
    }

    return options;
  };

  const handleDelete = (record: Target) => {
    Modal.confirm({
      title: t('job.deleteTarget'),
      content: t('job.deleteTargetConfirm'),
      okText: t('job.confirm'),
      cancelText: t('job.cancel'),
      centered: true,
      onOk: async () => {
        await deleteTarget(record.id);
        message.success(t('job.deleteTarget'));
        fetchData();
      },
    });
  };

  const openAddModal = () => {
    setModalType('add');
    setEditingTarget(null);
    form.resetFields();
    form.setFieldsValue({
      os_type: 'linux',
      driver: 'ansible',
      ssh_port: 22,
      ssh_user: 'root',
      ssh_credential_type: 'password',
      winrm_port: 5985,
      winrm_scheme: 'http',
      winrm_user: '',
      winrm_cert_validation: true,
    });
    setSshCredentialType('password');
    setModalOpen(true);
  };

  const openEditModal = (record: Target) => {
    setModalType('edit');
    setEditingTarget(record);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      os_type: record.os_type,
      cloud_region_id: record.cloud_region_id,
      ip: record.ip,
      team: record.team || [],
      driver: record.driver,
      ssh_port: record.ssh_port || 22,
      ssh_user: record.ssh_user || 'root',
      ssh_credential_type: 'password',
      winrm_port: record.winrm_port || 5985,
      winrm_scheme: (record.winrm_scheme as WinRMScheme) || 'http',
      winrm_user: record.winrm_user || '',
      winrm_cert_validation: record.winrm_cert_validation ?? true,
    });
    setSshCredentialType('password');
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);
      const formData = new FormData();
      formData.append('name', values.name);
      formData.append('ip', values.ip);
      formData.append('os_type', values.os_type);
      if (values.cloud_region_id !== undefined && values.cloud_region_id !== null) {
        formData.append('cloud_region_id', String(values.cloud_region_id));
      }
      formData.append('driver', values.driver);
      formData.append('credential_source', 'manual');
      formData.append('credential_id', '');
      if (values.os_type === 'windows') {
        formData.append('winrm_port', String(values.winrm_port));
        formData.append('winrm_scheme', values.winrm_scheme || 'http');
        formData.append('winrm_user', values.winrm_user || '');
        formData.append('winrm_password', values.winrm_password || '');
        formData.append('winrm_cert_validation', String(values.winrm_cert_validation ?? true));
      } else {
        formData.append('ssh_port', String(values.ssh_port));
        formData.append('ssh_user', values.ssh_user || '');
        formData.append('ssh_credential_type', values.ssh_credential_type || 'password');
        if (values.ssh_credential_type === 'password') {
          formData.append('ssh_password', values.ssh_password || '');
        } else if (values.ssh_key_file?.fileList?.[0]?.originFileObj) {
          formData.append('ssh_key_file', values.ssh_key_file.fileList[0].originFileObj);
        } else if (values.ssh_key_file?.file) {
          formData.append('ssh_key_file', values.ssh_key_file.file);
        }
      }
      if (Array.isArray(values.team) && values.team.length > 0) {
        formData.append('team', JSON.stringify(values.team));
      }

      if (modalType === 'add') {
        await createTarget(formData);
        message.success(t('job.addTarget'));
      } else if (editingTarget) {
        await updateTarget(editingTarget.id, formData);
        message.success(t('job.editTarget'));
      }
      setModalOpen(false);
      fetchData();
    } catch {
      // validation or API error
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields();
      setTestLoading(true);
      const res = await testTargetConnection({
        ip: values.ip,
        driver: values.driver,
        cloud_region_id: values.cloud_region_id,
        os_type: values.os_type,
        credential_source: 'manual',
        credential_id: '',
        ...(values.os_type === 'windows'
          ? {
            winrm_port: values.winrm_port,
            winrm_scheme: values.winrm_scheme,
            winrm_user: values.winrm_user,
            winrm_password: values.winrm_password,
            winrm_cert_validation: values.winrm_cert_validation,
          }
          : {
            ssh_port: values.ssh_port,
            ssh_user: values.ssh_user,
            ssh_password: values.ssh_password,
          }),
      });
      if (res.success) {
        message.success(res.message || t('job.testConnectionSuccess'));
      } else {
        message.error(res.message || t('job.testConnectionFailed'));
      }
    } catch {
      // error handled by interceptor
    } finally {
      setTestLoading(false);
    }
  };

  const handleWinrmSchemeChange = (value: WinRMScheme) => {
    const nextPort = value === 'https' ? 5986 : 5985;
    form.setFieldsValue({
      winrm_scheme: value,
      winrm_port: nextPort,
    });
  };

  const getDriverColor = (driver: string) => {
    switch (driver) {
      case 'sidecar':
        return '#1890ff';
      case 'ssh':
      case 'ansible':
        return '#fa8c16';
      default:
        return undefined;
    }
  };

  const columns: ColumnItem[] = [
    {
      title: t('job.targetName'),
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: t('job.ipAddress'),
      dataIndex: 'ip',
      key: 'ip',
      width: 140,
    },
    {
      title: t('job.cloudRegion'),
      dataIndex: 'cloud_region_name',
      key: 'cloud_region_name',
      width: 120,
    },
    {
      title: t('job.osType'),
      dataIndex: 'os_type_display',
      key: 'os_type_display',
      width: 100,
    },
    {
      title: t('job.currentDriver'),
      dataIndex: 'driver',
      key: 'driver',
      width: 130,
      render: (_: unknown, record: Target) => (
        <span style={{ color: getDriverColor(record.driver) }}>
          {record.driver_display || record.driver}
        </span>
      ),
    },
    {
      title: t('job.credential'),
      dataIndex: 'credential',
      key: 'credential',
      width: 100,
      render: (_: unknown, record: Target) => {
        const hasCredential = record.ssh_user || record.ssh_port;
        return (
          <Tag
            color={hasCredential ? 'success' : 'error'}
            style={{ margin: 0 }}
          >
            {hasCredential ? t('job.credentialConfigured') : t('job.credentialNotConfigured')}
          </Tag>
        );
      },
    },
    {
      title: t('job.organization'),
      dataIndex: 'team_name',
      key: 'team_name',
      width: 120,
      render: (_: unknown, record: Target) => (
        <span>{Array.isArray(record.team_name) ? record.team_name.join(', ') : '-'}</span>
      ),
    },
    {
      title: t('job.operation'),
      dataIndex: 'action',
      key: 'action',
      width: 120,
      render: (_: unknown, record: Target) => (
        <div className="flex items-center gap-3">
          <a
            className="text-(--color-primary) cursor-pointer"
            onClick={() => openEditModal(record)}
          >
            {t('job.editRule')}
          </a>
          <a
            className="text-(--color-primary) cursor-pointer"
            onClick={() => handleDelete(record)}
          >
            {t('job.deleteTarget')}
          </a>
        </div>
      ),
    },
  ];

  return (
    <div className="w-full h-full flex flex-col">
      {/* Header */}
      <div
        className="mb-4 rounded-lg px-6 py-4 shrink-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2
          className="text-base font-medium m-0 mb-1"
          style={{ color: 'var(--color-text-1)' }}
        >
          {t('job.targetManagement')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.targetManagementDesc')}
        </p>
      </div>

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 flex flex-col min-h-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        {/* Toolbar */}
        <div className="mb-4 flex items-center justify-between shrink-0">
          <SearchCombination
            fieldConfigs={fieldConfigs}
            onChange={handleSearchChange}
            fieldWidth={120}
            selectWidth={300}
          />
          <div className="flex gap-2">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openAddModal}
            >
              {t('job.addTarget')}
            </Button>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0">
          <CustomTable
            columns={columns}
            dataSource={data}
            loading={loading}
            rowKey="id"
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
      </div>

      {/* Add/Edit Modal */}
      <OperateModal
        title={modalType === 'add' ? t('job.addTarget') : t('job.editTarget')}
        open={modalOpen}
        confirmLoading={confirmLoading}
        onCancel={() => setModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setModalOpen(false)}>{t('job.cancel')}</Button>
            <Button type="primary" loading={confirmLoading} onClick={handleSubmit}>
              {t('job.save')}
            </Button>
          </div>
        }
        width={680}
      >
        <Form form={form} layout="vertical" colon={false}>
          {/* Section: Basic Info */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-base">📋</span>
            <span className="text-sm font-medium" style={{ color: 'var(--color-text-1)' }}>
              {t('job.basicInfo')}
            </span>
          </div>

          <Form.Item
            name="name"
            label={t('job.targetName')}
            rules={[{ required: true, message: t('job.targetNamePlaceholder') }]}
          >
            <Input placeholder={t('job.targetNamePlaceholder')} />
          </Form.Item>

          <Form.Item
            name="os_type"
            label={t('job.operatingSystem')}
            rules={[{ required: true }]}
          >
            <Radio.Group>
              <Radio value="linux">{t('job.linux')}</Radio>
              <Radio value="windows">{t('job.windows')}</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            name="cloud_region_id"
            label={t('job.cloudRegion')}
            rules={[{ required: true, message: t('job.selectCloudRegion') }]}
          >
            <Select
              placeholder={t('job.selectCloudRegion')}
              options={cloudRegions.map((r) => ({
                label: r.name,
                value: r.id,
              }))}
            />
          </Form.Item>

          <Form.Item
            name="ip"
            label={t('job.ipAddress')}
            rules={[{ required: true, message: t('job.ipPlaceholder') }]}
          >
            <Input placeholder={t('job.ipPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="team"
            label={t('job.organization')}
            rules={[{ required: true, message: t('job.organizationPlaceholder') }]}
          >
            <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
          </Form.Item>

          {/* Section: Driver Config */}
          <div className="flex items-center gap-2 mb-4 mt-6">
            <span className="text-base">⚙️</span>
            <span className="text-sm font-medium" style={{ color: 'var(--color-text-1)' }}>
              {t('job.driverConfig')}
            </span>
          </div>

          <Form.Item
            name="driver"
            label={t('job.executionDriver')}
            rules={[{ required: true }]}
          >
            <Select
              placeholder={t('job.selectDriver')}
              options={getDriverSelectOptions()}
            />
          </Form.Item>
          <div
            className="text-xs mb-4"
            style={{ color: 'var(--color-text-3)', marginTop: -16 }}
          >
            {t('job.driverHelp')}
          </div>

          {osType === 'windows' ? (
            <>
              <Form.Item
                name="winrm_scheme"
                label={t('job.protocol')}
                rules={[{ required: true }]}
              >
                <Select options={winrmSchemeOptions} onChange={handleWinrmSchemeChange} />
              </Form.Item>

              <Form.Item
                name="winrm_port"
                label={t('job.port')}
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>

              <Form.Item
                name="winrm_user"
                label={t('job.username')}
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>

              <Form.Item
                name="winrm_password"
                label={t('job.password')}
                rules={[{ required: true, message: t('job.passwordPlaceholder') }]}
              >
                <Input.Password placeholder={t('job.passwordPlaceholder')} />
              </Form.Item>

              <Alert
                type="warning"
                showIcon
                message={t('job.windowsTestConnectionNote')}
                className="mb-4"
              />

              <Button
                block
                type="dashed"
                loading={testLoading}
                onClick={handleTestConnection}
              >
                {t('job.testConnection')}
              </Button>
            </>
          ) : (
            <>
              <Form.Item
                name="ssh_port"
                label={t('job.sshPort')}
              >
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>

              <Form.Item
                name="ssh_user"
                label={t('job.sshUser')}
                rules={[{ required: true }]}
              >
                <Input placeholder="root" />
              </Form.Item>

              <Form.Item
                name="ssh_credential_type"
                label={t('job.sshCredential')}
                required
              >
                <Radio.Group
                  onChange={(e) => setSshCredentialType(e.target.value)}
                >
                  <Radio value="key">{t('job.sshKey')}</Radio>
                  <Radio value="password">{t('job.sshPassword')}</Radio>
                </Radio.Group>
              </Form.Item>

              {sshCredentialType === 'password' ? (
                <Form.Item
                  name="ssh_password"
                  rules={[{ required: true, message: t('job.sshPasswordPlaceholder') }]}
                >
                  <Input.Password placeholder={t('job.sshPasswordPlaceholder')} />
                </Form.Item>
              ) : (
                <Form.Item
                  name="ssh_key_file"
                  rules={[{ required: true, message: t('job.selectKeyFile') }]}
                >
                  <Dragger
                    maxCount={1}
                    beforeUpload={() => false}
                    accept=".pem,.key,.pub"
                  >
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text text-sm">
                      {t('job.selectKeyFile')}
                    </p>
                  </Dragger>
                </Form.Item>
              )}

              <Alert
                type="warning"
                showIcon
                message={t('job.testConnectionNote')}
                className="mb-4"
              />

              <Button
                block
                type="dashed"
                loading={testLoading}
                onClick={handleTestConnection}
              >
                {t('job.testConnection')}
              </Button>
            </>
          )}
        </Form>
      </OperateModal>
    </div>
  );
};

export default TargetPage;
