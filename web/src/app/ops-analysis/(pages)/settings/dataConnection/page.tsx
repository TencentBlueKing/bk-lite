'use client';

import React, { useEffect, useState } from 'react';
import type { TablePaginationConfig } from 'antd/es/table';
import OperateModal from './operateModal';
import PermissionWrapper from '@/components/permission';
import { Button, message, Modal, Switch } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import OpsAnalysisSettingsListShell from '@/app/ops-analysis/components/ops-analysis-settings-list-shell';
import { useTranslation } from '@/utils/i18n';
import { DataConnectionItem } from '@/app/ops-analysis/types/dataConnection';
import { useDataConnectionApi } from '@/app/ops-analysis/api/dataConnection';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const DataConnectionPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const {
    getDataConnectionList,
    deleteDataConnection,
    updateDataConnection,
    testDataConnection,
    getDataConnectionReferences,
  } = useDataConnectionApi();
  const [searchKey, setSearchKey] = useState('');
  const [searchValue, setSearchValue] = useState('');
  const [filteredList, setFilteredList] = useState<DataConnectionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [currentRow, setCurrentRow] = useState<DataConnectionItem | undefined>();
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const typeLabels: Record<string, string> = {
    mysql: 'MySQL',
    postgresql: 'PostgreSQL',
    rest_api: 'REST API',
    elasticsearch: 'Elasticsearch',
  };

  const fetchList = async (
    searchKeyParam?: string,
    paginationParam?: { current?: number; pageSize?: number },
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
      const { items, count } = await getDataConnectionList(params);
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
      console.error('获取连接库列表失败:', error);
      setFilteredList([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, [pagination.current, pagination.pageSize]);

  const handleFilter = (value?: string) => {
    const key = value !== undefined ? value : searchValue;
    setSearchKey(key);
    setSearchValue(key);
    const newPagination = { current: 1, pageSize: pagination.pageSize };
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchList(key, newPagination);
  };

  const handleEdit = (type: 'add' | 'edit', row?: DataConnectionItem) => {
    if (type === 'edit' && row) {
      setCurrentRow(row);
    } else {
      setCurrentRow(undefined);
    }
    setModalVisible(true);
  };

  const handleDelete = async (row: DataConnectionItem) => {
    try {
      const refs = await getDataConnectionReferences(row.id);
      const refList = Array.isArray(refs) ? refs : [];
      if (refList.length > 0) {
        Modal.warning({
          title: t('dataConnection.deleteBlocked'),
          content: t(
            'dataConnection.deleteBlockedContent',
            '仍有 {count} 个数据源引用该连接，请先解除引用。',
            { count: refList.length },
          ),
          centered: true,
        });
        return;
      }
    } catch {
      // 后端删除仍会 PROTECT，继续走确认即可
    }

    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        try {
          await deleteDataConnection(row.id);
          message.success(t('opsAnalysis.successfullyDeleted'));
          if (pagination.current > 1 && filteredList.length === 1) {
            setPagination((prev) => ({ ...prev, current: prev.current - 1 }));
            fetchList(searchKey, {
              current: pagination.current - 1,
              pageSize: pagination.pageSize,
            });
          } else {
            fetchList();
          }
        } catch (error: any) {
          message.error(error?.message || t('dataConnection.operationFailed'));
        }
      },
    });
  };

  const handleToggleActive = async (
    row: DataConnectionItem,
    checked: boolean,
  ) => {
    try {
      setTogglingId(row.id);
      await updateDataConnection(row.id, { is_active: checked });
      setFilteredList((prev) =>
        prev.map((item) =>
          item.id === row.id ? { ...item, is_active: checked } : item,
        ),
      );
      message.success(t('dataConnection.updateSuccess'));
    } catch (error: any) {
      message.error(error?.message || t('dataConnection.operationFailed'));
    } finally {
      setTogglingId(null);
    }
  };

  const handleTest = async (row: DataConnectionItem) => {
    try {
      setTestingId(row.id);
      await testDataConnection(row.id, { suppressErrorNotification: true });
      message.success(t('dataSource.testConnectionSuccess'));
    } catch (error: any) {
      message.error(error?.message || t('dataSource.testConnectionFailed'));
    } finally {
      setTestingId(null);
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
    fetchList(undefined, newPagination);
  };

  const columns = [
    {
      title: t('dataConnection.name'),
      dataIndex: 'name',
      key: 'name',
      width: 180,
    },
    {
      title: t('dataConnection.type'),
      dataIndex: 'connection_type',
      key: 'connection_type',
      width: 140,
      render: (value: string) => typeLabels[value] || value || '-',
    },
    {
      title: t('dataConnection.endpoint'),
      dataIndex: 'endpoint_summary',
      key: 'endpoint_summary',
      width: 220,
      ellipsis: true,
      render: (value: string) => value || '-',
    },
    {
      title: t('dataConnection.references'),
      dataIndex: 'reference_count',
      key: 'reference_count',
      width: 100,
      render: (value: number) => value ?? 0,
    },
    {
      title: t('dataConnection.enabled'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (value: boolean, row: DataConnectionItem) => (
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Switch
            size="small"
            checked={!!value}
            loading={togglingId === row.id}
            disabled={togglingId !== null && togglingId !== row.id}
            onChange={(checked) => handleToggleActive(row, checked)}
          />
        </PermissionWrapper>
      ),
    },
    {
      title: t('dataConnection.describe'),
      dataIndex: 'description',
      key: 'description',
      width: 200,
      ellipsis: true,
      render: (value: string) => value || '-',
    },
    {
      title: t('dataConnection.createdTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => (text ? convertToLocalizedTime(text) : '-'),
    },
    {
      title: t('common.actions'),
      key: 'operation',
      width: 180,
      fixed: 'right' as const,
      render: (_: unknown, row: DataConnectionItem) => (
        <div className="space-x-4">
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              loading={testingId === row.id}
              disabled={testingId !== null && testingId !== row.id}
              onClick={() => handleTest(row)}
            >
              {t('dataSource.testConnection')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              onClick={() => handleEdit('edit', row)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => handleDelete(row)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </div>
      ),
    },
  ];

  return (
    <OpsAnalysisSettingsListShell
      introTitle={t('dataConnection.introTitle')}
      introDescription={t('dataConnection.introMsg')}
      searchValue={searchValue}
      searchPlaceholder={t('common.search')}
      onSearchValueChange={setSearchValue}
      onSearch={(value) => handleFilter(value)}
      onSearchClear={() => handleFilter('')}
      actions={(
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => handleEdit('add')}
          >
            {t('common.new')}
          </Button>
        </PermissionWrapper>
      )}
      columns={columns}
      dataSource={filteredList}
      rowKey="id"
      pagination={pagination}
      tableLoading={loading}
      scroll={{ y: 'calc(100vh - 430px)' }}
      tableProps={{ onChange: handleTableChange }}
      modal={(
        <OperateModal
          open={modalVisible}
          currentRow={currentRow}
          onClose={() => setModalVisible(false)}
          onSuccess={() => {
            setModalVisible(false);
            fetchList();
          }}
        />
      )}
    />
  );
};

export default DataConnectionPage;
