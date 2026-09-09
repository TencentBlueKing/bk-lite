'use client';

import React, { useState, useEffect } from 'react';
import type { TablePaginationConfig } from 'antd/es/table';
import OperateModal from './operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { Button, Input, Card, message, Modal, Space, Tag } from 'antd';
import { SearchOutlined, UploadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  DatasourceItem,
  type DataSourceSourceType,
} from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useImportExportApi } from '@/app/ops-analysis/api/importExport';
import { ImportModal } from '@/app/ops-analysis/components/importExport';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useUserInfoContext } from '@/context/userInfo';
import {
  canEditBuiltinDatasourceGroups,
  isBuiltinDatasource,
  SOURCE_TYPE_EXCEL,
  SOURCE_TYPE_MYSQL,
  SOURCE_TYPE_NATS,
  SOURCE_TYPE_POSTGRESQL,
  SOURCE_TYPE_PROMETHEUS,
  SOURCE_TYPE_REST_API,
} from './operateModalUtils';

const getRestPath = (url?: string) => {
  if (!url) return '';
  try {
    const parsed = new URL(url);
    return parsed.pathname || '/';
  } catch {
    const [path] = url.split(/[?#]/);
    return path || url;
  }
};

const ALL_SOURCE_TYPES = '';

const Datasource: React.FC = () => {
  const { t } = useTranslation();
  const { isSuperUser } = useUserInfoContext();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getDataSourceList, deleteDataSource } = useDataSourceApi();
  const { exportObjects, downloadYaml } = useImportExportApi();
  const [searchKey, setSearchKey] = useState('');
  const [searchValue, setSearchValue] = useState('');
  const [sourceTypeFilter, setSourceTypeFilter] = useState(ALL_SOURCE_TYPES);
  const [filteredList, setFilteredList] = useState<DatasourceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalMode, setModalMode] = useState<'add' | 'edit' | 'view'>('add');
  const [currentRow, setCurrentRow] = useState<DatasourceItem | undefined>();
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [exportLoading, setExportLoading] = useState<number | null>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const sourceTypeLabels: Record<DataSourceSourceType, string> = {
    nats: t('dataSource.sourceTypes.nats'),
    mysql: t('dataSource.sourceTypes.mysql'),
    postgresql: t('dataSource.sourceTypes.postgresql'),
    rest_api: t('dataSource.sourceTypes.restApi'),
    excel: t('dataSource.sourceTypes.excel'),
    prometheus: t('dataSource.sourceTypes.prometheus'),
  };

  const sourceTypeFilterOptions: Array<{
    value: string;
    label: string;
  }> = [
    { value: ALL_SOURCE_TYPES, label: t('dataSource.allSourceTypes') },
    { value: SOURCE_TYPE_NATS, label: sourceTypeLabels.nats },
    { value: SOURCE_TYPE_REST_API, label: sourceTypeLabels.rest_api },
    { value: SOURCE_TYPE_POSTGRESQL, label: sourceTypeLabels.postgresql },
    { value: SOURCE_TYPE_MYSQL, label: sourceTypeLabels.mysql },
    { value: SOURCE_TYPE_EXCEL, label: sourceTypeLabels.excel },
    { value: SOURCE_TYPE_PROMETHEUS, label: sourceTypeLabels.prometheus },
  ];

  // 获取数据源列表
  const fetchDataSources = async (
    searchKeyParam?: string,
    paginationParam?: { current?: number; pageSize?: number },
    sourceTypeParam?: string
  ) => {
    try {
      setLoading(true);
      const currentPagination = paginationParam || pagination;
      const params: any = {
        page: currentPagination.current || pagination.current,
        page_size: currentPagination.pageSize || pagination.pageSize,
      };
      const currentSearchKey =
        searchKeyParam !== undefined ? searchKeyParam : searchKey;
      if (currentSearchKey && currentSearchKey.trim()) {
        params.search = currentSearchKey.trim();
      }
      const currentSourceType =
        sourceTypeParam !== undefined ? sourceTypeParam : sourceTypeFilter;
      if (currentSourceType) {
        params.source_type = currentSourceType;
      }
      const { items, count } = await getDataSourceList(params);
      if (items && Array.isArray(items)) {
        setFilteredList(items);
        setPagination((prev) => ({
          ...prev,
          current: currentPagination.current || prev.current,
          pageSize: currentPagination.pageSize || prev.pageSize,
          total: count || 0,
        }));
      }
    } catch (error) {
      console.error('获取数据源列表失败:', error);
      setFilteredList([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDataSources();
  }, [pagination.current, pagination.pageSize]);

  const handleFilter = (value?: string) => {
    const key = value !== undefined ? value : searchValue;
    setSearchKey(key);
    setSearchValue(key);
    const newPagination = { current: 1, pageSize: pagination.pageSize };
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchDataSources(key, newPagination, sourceTypeFilter);
  };

  const handleSourceTypeFilter = (type: string) => {
    if (type === sourceTypeFilter) return;
    setSourceTypeFilter(type);
    const newPagination = { current: 1, pageSize: pagination.pageSize };
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchDataSources(searchKey, newPagination, type);
  };

  const handleEdit = (type: 'add' | 'edit' | 'view', row?: DatasourceItem) => {
    setModalMode(type);
    if (type !== 'add' && row) {
      setCurrentRow(row);
    } else {
      setCurrentRow(undefined);
    }
    setModalVisible(true);
  };

  const handleDelete = (row: DatasourceItem) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        try {
          await deleteDataSource(row.id);
          message.success(t('successfullyDeleted'));

          if (pagination.current > 1 && filteredList.length === 1) {
            setPagination((prev) => ({ ...prev, current: prev.current - 1 }));
            fetchDataSources(searchKey, {
              current: pagination.current - 1,
              pageSize: pagination.pageSize,
            });
          } else {
            fetchDataSources();
          }
        } catch (error: any) {
          message.error(error.message);
        }
      },
    });
  };

  const handleExport = async (row: DatasourceItem) => {
    try {
      setExportLoading(row.id);
      const response = await exportObjects({
        object_type: 'datasource',
        object_ids: [row.id],
      });
      if (response.yaml_content) {
        downloadYaml(response.yaml_content, `datasource_${row.name}_export`);
        message.success(t('common.exportSuccess'));
      }
    } catch (error: any) {
      message.error(error?.message || t('common.exportFailed'));
    } finally {
      setExportLoading(null);
    }
  };

  const handleTableChange = (pg: TablePaginationConfig) => {
    const newPagination = {
      current: pg.current || 1,
      pageSize: pg.pageSize || 20,
    };
    setPagination((prev) => ({
      ...prev,
      ...newPagination,
    }));
    // 直接传递新的分页信息，避免状态更新延迟
    fetchDataSources(undefined, newPagination);
  };

  const renderSourceObject = (_: unknown, row: DatasourceItem) => {
    const sourceType = row.source_type || 'nats';
    const connectionConfig = row.connection_config || {};
    const queryConfig = row.query_config || {};

    if (sourceType === 'nats') {
      return row.rest_api || '-';
    }

    if (sourceType === 'rest_api') {
      const method = String(connectionConfig.method || 'GET').toUpperCase();
      const path = getRestPath(String(connectionConfig.url || ''));
      return path ? `${method} ${path}` : '-';
    }

    if (sourceType === 'mysql' || sourceType === 'postgresql') {
      if (queryConfig.sql) {
        return t('dataSource.sqlQuery');
      }
      const database = connectionConfig.database;
      const table = queryConfig.table;
      if (database && table) {
        return `${database}.${table}`;
      }
      return table || '-';
    }

    if (sourceType === 'excel') {
      return connectionConfig.filename || t('dataSource.excelImportedData');
    }

    if (sourceType === 'prometheus') {
      return connectionConfig.url || '-';
    }

    return '-';
  };

  const columns = [
    {
      title: t('dataSource.name'),
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (name: string, row: DatasourceItem) => (
        <Space size={6}>
          <span>{name}</span>
          {isBuiltinDatasource(row) ? (
            <Tag
              bordered={false}
              style={{
                marginInlineEnd: 0,
                paddingInline: 6,
                borderRadius: 4,
                background: 'var(--color-fill-2)',
                color: 'var(--color-text-3)',
                fontSize: 12,
                fontWeight: 400,
                lineHeight: '18px',
              }}
            >
              {t('common.builtIn')}
            </Tag>
          ) : null}
        </Space>
      ),
    },
    {
      title: t('dataSource.sourceType'),
      dataIndex: 'source_type',
      key: 'source_type',
      width: 140,
      render: (value: DataSourceSourceType | string) =>
        sourceTypeLabels[(value || 'nats') as DataSourceSourceType] || value || '-',
    },
    {
      title: t('dataSource.sourceObject'),
      key: 'source_object',
      width: 190,
      ellipsis: true,
      render: renderSourceObject,
    },
    {
      title: t('dataSource.describe'),
      dataIndex: 'desc',
      key: 'desc',
      width: 200,
    },
    {
      title: t('dataSource.createdTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => (text ? convertToLocalizedTime(text) : '-'),
    },
    {
      title: t('common.actions'),
      key: 'operation',
      width: 150,
      fixed: 'right' as const,
      render: (_: unknown, row: DatasourceItem) => (
        <div className="space-x-4">
          {isBuiltinDatasource(row) ? (
            canEditBuiltinDatasourceGroups(isSuperUser, row) ? (
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  type="link"
                  size="small"
                  onClick={() => handleEdit('edit', row)}
                >
                  {t('common.edit')}
                </Button>
              </PermissionWrapper>
            ) : (
              <PermissionWrapper requiredPermissions={['View']}>
                <Button
                  type="link"
                  size="small"
                  onClick={() => handleEdit('view', row)}
                >
                  {t('common.view')}
                </Button>
              </PermissionWrapper>
            )
          ) : (
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                size="small"
                onClick={() => handleEdit('edit', row)}
              >
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
          )}
          <PermissionWrapper requiredPermissions={['View']}>
            <Button
              type="link"
              size="small"
              loading={exportLoading === row.id}
              onClick={() => handleExport(row)}
            >
              {t('common.export')}
            </Button>
          </PermissionWrapper>
          {!isBuiltinDatasource(row) ? (
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Button type="link" size="small" danger onClick={() => handleDelete(row)}>
                {t('common.delete')}
              </Button>
            </PermissionWrapper>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col w-full h-full bg-[var(--color-bg-1)]">
      <Card
        style={{
          borderRadius: 0,
          marginBottom: '16px',
          paddingLeft: '12px',
          borderLeftWidth: '0px',
          borderTopWidth: '0px',
        }}
        styles={{
          body: { padding: '16px' },
        }}
      >
        <p className="font-extrabold text-base mb-2">
          {t('dataSource.introTitle')}
        </p>
        <p className="text-sm text-[var(--color-text-2)]">
          {t('dataSource.introMsg')}
        </p>
      </Card>
      <div className="px-6 pb-0">
        <div className="flex justify-between mb-[20px] gap-4">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <Input
              allowClear
              prefix={<SearchOutlined style={{ color: 'var(--color-text-3)' }} />}
              value={searchValue}
              placeholder={t('dataSource.searchPlaceholder')}
              style={{ width: 260 }}
              onChange={(e) => setSearchValue(e.target.value)}
              onPressEnter={(e) => handleFilter(e.currentTarget.value)}
              onClear={() => {
                setSearchValue('');
                handleFilter('');
              }}
            />
            <div className="flex flex-wrap items-center gap-2">
              {sourceTypeFilterOptions.map((option) => {
                const active = sourceTypeFilter === option.value;
                return (
                  <button
                    key={option.value || 'all'}
                    type="button"
                    className={`inline-flex h-8 items-center rounded px-3 text-sm transition-all duration-150 select-none cursor-pointer ${
                      active
                        ? 'border border-[var(--color-primary)] bg-[var(--color-primary-bg)] text-[var(--color-primary)] font-medium shadow-[0_1px_2px_rgba(0,0,0,0.04)]'
                        : 'border border-[var(--color-border-2)] bg-[var(--color-bg-1)] text-[var(--color-text-2)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] active:scale-[0.98]'
                    }`}
                    onClick={() => handleSourceTypeFilter(option.value)}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>
          <Space>
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button
                icon={<UploadOutlined />}
                onClick={() => setImportModalVisible(true)}
              >
                {t('common.import')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button type="primary" onClick={() => handleEdit('add')}>
                {t('common.addNew')}
              </Button>
            </PermissionWrapper>
          </Space>
        </div>
        <CustomTable
          size="middle"
          rowKey="id"
          columns={columns}
          loading={loading}
          dataSource={filteredList}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 430px)' }}
        />
        <OperateModal
          open={modalVisible}
          mode={modalMode}
          currentRow={currentRow}
          onClose={() => setModalVisible(false)}
          onSuccess={async () => {
            setModalVisible(false);
            fetchDataSources();
          }}
        />
        <ImportModal
          visible={importModalVisible}
          onCancel={() => setImportModalVisible(false)}
          targetDirectoryId={null}
          onSuccess={() => {
            fetchDataSources();
          }}
        />
      </div>
    </div>
  );
};

export default Datasource;
