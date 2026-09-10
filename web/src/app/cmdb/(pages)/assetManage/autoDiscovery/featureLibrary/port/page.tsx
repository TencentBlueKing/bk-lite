'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Tag,
  message,
} from 'antd';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import Introduction from '@/components/introduction';
import PermissionWrapper from '@/components/permission';
import { usePortFingerprintApi, type PortFingerprintItem } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';

const FEATURE_LIBRARY_PERMISSION_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/soid';

export const PORT_TARGET_TYPE_OPTIONS = [
  { value: 'mysql', label: 'MySQL' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mssql', label: 'SQL Server (MSSQL)' },
  { value: 'oracle', label: 'Oracle' },
  { value: 'redis', label: 'Redis' },
  { value: 'mongodb', label: 'MongoDB' },
  { value: 'es', label: 'Elasticsearch' },
  { value: 'memcached', label: 'Memcached' },
  { value: 'nginx', label: 'Nginx' },
  { value: 'tomcat', label: 'Tomcat' },
  { value: 'apache', label: 'Apache' },
  { value: 'kafka', label: 'Kafka' },
  { value: 'rabbitmq', label: 'RabbitMQ' },
  { value: 'zookeeper', label: 'ZooKeeper' },
];

export const getTargetTypeLabel = (value: string) => {
  const found = PORT_TARGET_TYPE_OPTIONS.find((item) => item.value === value);
  return found ? found.label : value;
};

const PortFingerprintPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const typeFromUrl = (searchParams.get('type') || searchParams.get('target_type') || '').trim();

  const { getPortFingerprintList, createPortFingerprint, deletePortFingerprint } =
    usePortFingerprintApi();

  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [dataList, setDataList] = useState<PortFingerprintItem[]>([]);
  const [selectedType, setSelectedType] = useState<string>(typeFromUrl);
  const [searchPort, setSearchPort] = useState<string>('');
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [modalLoading, setModalLoading] = useState<boolean>(false);
  const [form] = Form.useForm();

  const paginationRef = useRef(pagination);
  useEffect(() => {
    paginationRef.current = pagination;
  }, [pagination]);

  const fetchData = useCallback(
    async (params: { current?: number; pageSize?: number; type?: string; port?: string } = {}) => {
      try {
        setTableLoading(true);
        const curPage = params.current ?? paginationRef.current.current;
        const curPageSize = params.pageSize ?? paginationRef.current.pageSize;
        const curType = params.type !== undefined ? params.type : selectedType;
        const curPort = params.port !== undefined ? params.port : searchPort;

        const queryParams: Record<string, unknown> = {
          page: curPage,
          page_size: curPageSize,
        };
        if (curType) {
          queryParams.target_type = curType;
        }
        if (curPort) {
          queryParams.port = curPort;
        }

        const data = await getPortFingerprintList(queryParams);
        setDataList(data.items || []);
        setPagination((prev) => ({
          ...prev,
          total: data.count || 0,
          current: curPage,
          pageSize: curPageSize,
        }));
      } catch (error) {
        console.error(error);
        message.error(t('common.loadListFailed'));
      } finally {
        setTableLoading(false);
      }
    },
    [getPortFingerprintList, selectedType, searchPort, t]
  );

  useEffect(() => {
    setSelectedType(typeFromUrl);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ current: 1, type: typeFromUrl });
  }, [typeFromUrl]);

  const handleFilterChange = () => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ current: 1, type: selectedType, port: searchPort });
  };

  const handleResetFilter = () => {
    setSelectedType('');
    setSearchPort('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ current: 1, type: '', port: '' });
  };

  const handleDelete = (record: PortFingerprintItem) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        try {
          await deletePortFingerprint(record.id);
          message.success(t('successfullyDeleted'));
          fetchData();
        } catch (err: any) {
          message.error(err?.message || t('OidLibrary.operateFailed'));
        }
      },
    });
  };

  const handleOpenAddModal = () => {
    form.resetFields();
    form.setFieldsValue({
      protocol: 'tcp',
      target_type: selectedType || undefined,
    });
    setModalOpen(true);
  };

  const handleAddSubmit = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      await createPortFingerprint({
        port: Number(values.port),
        target_type: values.target_type,
        protocol: 'tcp',
      });
      message.success(t('successfullyAdded'));
      setModalOpen(false);
      form.resetFields();
      fetchData({ current: 1 });
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err?.message || t('OidLibrary.operateFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: t('OidLibrary.port'),
        dataIndex: 'port',
        key: 'port',
        width: 140,
        render: (port: number) => (
          <span className="font-mono font-medium text-[var(--color-text-1)]">{port}</span>
        ),
      },
      {
        title: t('OidLibrary.protocol'),
        dataIndex: 'protocol',
        key: 'protocol',
        width: 120,
        render: (proto: string) => (
          <Tag className="!m-0 !rounded !border-0 !bg-[var(--color-fill-2)] !px-1.5 !text-xs font-mono !text-[var(--color-text-2)] uppercase">
            {proto || 'tcp'}
          </Tag>
        ),
      },
      {
        title: t('OidLibrary.targetType'),
        dataIndex: 'target_type',
        key: 'target_type',
        render: (type: string) => (
          <div className="flex items-center gap-2">
            <span className="font-medium text-[var(--color-text-1)]">{getTargetTypeLabel(type)}</span>
            <span className="font-mono text-xs text-[var(--color-text-3)]">({type})</span>
          </div>
        ),
      },
      {
        title: t('OidLibrary.builtIn'),
        dataIndex: 'built_in',
        key: 'built_in',
        width: 140,
        render: (builtIn: boolean) => (
          <Tag
            className={`!m-0 !rounded !border-0 !px-2 !py-0.5 !text-xs ${
              builtIn
                ? '!bg-[color-mix(in_srgb,var(--color-primary)_12%,transparent)] !text-[var(--color-primary)] font-medium'
                : '!bg-[var(--color-fill-2)] !text-[var(--color-text-3)]'
            }`}
          >
            {builtIn ? t('OidLibrary.builtInYes') : t('OidLibrary.builtInNo')}
          </Tag>
        ),
      },
      {
        title: t('common.actions'),
        key: 'operation',
        width: 120,
        render: (_: unknown, record: PortFingerprintItem) => (
          <PermissionWrapper
            requiredPermissions={['Delete']}
            permissionPath={FEATURE_LIBRARY_PERMISSION_PATH}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              size="small"
              danger
              disabled={record.built_in}
              onClick={() => handleDelete(record)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        ),
      },
    ],
    [t]
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 overflow-x-auto">
        <Introduction
          title={t('OidLibrary.portIntroTitle')}
          message={t('OidLibrary.portIntroMessage')}
        />
      </div>

      <div className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <Select
            allowClear
            placeholder={t('OidLibrary.typePlaceholder')}
            value={selectedType || undefined}
            onChange={(val) => {
              setSelectedType(val || '');
            }}
            style={{ width: 200 }}
            options={PORT_TARGET_TYPE_OPTIONS}
          />
          <Input
            allowClear
            placeholder={t('OidLibrary.portPlaceholder')}
            value={searchPort}
            onChange={(e) => setSearchPort(e.target.value)}
            onPressEnter={handleFilterChange}
            style={{ width: 180 }}
          />
          <Button type="primary" ghost icon={<SearchOutlined />} onClick={handleFilterChange}>
            {t('common.search')}
          </Button>
          {(selectedType || searchPort) && (
            <Button onClick={handleResetFilter}>{t('common.reset')}</Button>
          )}
        </div>

        <PermissionWrapper
          requiredPermissions={['Add']}
          permissionPath={FEATURE_LIBRARY_PERMISSION_PATH}
        >
          <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenAddModal}>
            {t('OidLibrary.addPortFingerprint')}
          </Button>
        </PermissionWrapper>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        <CustomTable
          size="middle"
          rowKey="id"
          loading={tableLoading}
          columns={columns}
          dataSource={dataList}
          pagination={pagination}
          onChange={(newPag) => {
            setPagination((prev) => ({
              ...prev,
              current: newPag.current || 1,
              pageSize: newPag.pageSize || 20,
            }));
            fetchData({
              current: newPag.current,
              pageSize: newPag.pageSize,
            });
          }}
          scroll={{ y: 'calc(100vh - 456px)' }}
        />
      </div>

      <Modal
        title={t('OidLibrary.addPortFingerprint')}
        open={modalOpen}
        confirmLoading={modalLoading}
        onCancel={() => setModalOpen(false)}
        onOk={handleAddSubmit}
        destroyOnClose
      >
        <Form form={form} layout="vertical" className="pt-2">
          <Form.Item
            label={t('OidLibrary.port')}
            name="port"
            rules={[
              { required: true, message: t('OidLibrary.portPlaceholder') },
              {
                validator: async (_, value) => {
                  if (value === undefined || value === null || value === '') return;
                  const num = Number(value);
                  if (!Number.isInteger(num) || num < 1 || num > 65535) {
                    throw new Error(t('OidLibrary.portPlaceholder'));
                  }
                },
              },
            ]}
          >
            <InputNumber
              min={1}
              max={65535}
              precision={0}
              placeholder="1-65535"
              className="w-full font-mono"
            />
          </Form.Item>

          <Form.Item
            label={t('OidLibrary.targetType')}
            name="target_type"
            rules={[{ required: true, message: t('OidLibrary.typePlaceholder') }]}
          >
            <Select
              showSearch
              placeholder={t('OidLibrary.typePlaceholder')}
              options={PORT_TARGET_TYPE_OPTIONS}
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase()) ||
                (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>

          <Form.Item label={t('OidLibrary.protocol')} name="protocol" initialValue="tcp">
            <Input disabled value="TCP" className="uppercase font-mono" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PortFingerprintPage;
