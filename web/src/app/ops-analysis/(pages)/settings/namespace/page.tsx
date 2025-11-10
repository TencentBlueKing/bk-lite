'use client';

import React, { useState, useEffect } from 'react';
import OperateModal from './operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { Button, Input, Card, message, Modal, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { NamespaceItem } from '@/app/ops-analysis/types/namespace';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';

const Namespace: React.FC = () => {
  const { t } = useTranslation();
  const { getNamespaceList, deleteNamespace } = useNamespaceApi();
  const [searchKey, setSearchKey] = useState('');
  const [searchValue, setSearchValue] = useState('');
  const [filteredList, setFilteredList] = useState<NamespaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [currentRow, setCurrentRow] = useState<any>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  // 获取命名空间列表
  const fetchNamespaces = async (
    searchKeyParam?: string,
    paginationParam?: { current?: number; pageSize?: number }
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
        params.name = currentSearchKey.trim();
      }
      const { items, count } = await getNamespaceList(params);
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
      console.error('获取命名空间列表失败:', error);
      setFilteredList([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNamespaces();
  }, [pagination.current, pagination.pageSize]);

  const handleFilter = (value?: string) => {
    const key = value !== undefined ? value : searchValue;
    setSearchKey(key);
    setSearchValue(key);
    const newPagination = { current: 1, pageSize: pagination.pageSize };
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchNamespaces(key, newPagination);
  };

  const handleEdit = (type: 'add' | 'edit', row?: NamespaceItem) => {
    if (type === 'edit' && row) {
      setCurrentRow(row);
    } else {
      setCurrentRow(null);
    }
    setModalVisible(true);
  };

  const handleDelete = (row: NamespaceItem) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          await deleteNamespace(row.id);
          message.success(t('successfullyDeleted'));

          if (pagination.current > 1 && filteredList.length === 1) {
            setPagination((prev) => ({ ...prev, current: prev.current - 1 }));
            fetchNamespaces(searchKey, {
              current: pagination.current - 1,
              pageSize: pagination.pageSize,
            });
          } else {
            fetchNamespaces();
          }
        } catch (error: any) {
          message.error(error.message);
        }
      },
    });
  };

  const handleTableChange = (pg: any) => {
    const newPagination = {
      current: pg.current || 1,
      pageSize: pg.pageSize || 20,
    };
    setPagination((prev) => ({
      ...prev,
      ...newPagination,
    }));
    fetchNamespaces(undefined, newPagination);
  };

  const columns = [
    { title: t('namespace.name'), dataIndex: 'name', key: 'name', width: 150 },
    {
      title: t('namespace.account'),
      dataIndex: 'account',
      key: 'account',
      width: 150,
    },
    {
      title: t('namespace.domain'),
      dataIndex: 'domain',
      key: 'domain',
      width: 150,
    },
    {
      title: t('namespace.title'),
      dataIndex: 'namespace',
      key: 'namespace',
      width: 150,
    },
    {
      title: t('namespace.tls'),
      dataIndex: 'enable_tls',
      key: 'enable_tls',
      width: 80,
      render: (enable_tls: boolean) => (
        <Tag color={enable_tls ? 'green' : 'default'}>
          {enable_tls ? t('namespace.tlsEnabled') : t('namespace.tlsDisabled')}
        </Tag>
      ),
    },
    {
      title: t('namespace.describe'),
      dataIndex: 'desc',
      key: 'desc',
      width: 200,
    },
    {
      title: t('namespace.createdTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => (text ? new Date(text).toLocaleString() : '-'),
    },
    {
      title: t('common.actions'),
      key: 'operation',
      width: 100,
      render: (_: any, row: NamespaceItem) => (
        <div className="space-x-4">
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
            <Button type="link" size="small" onClick={() => handleDelete(row)}>
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
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
          {t('namespace.introTitle')}
        </p>
        <p className="text-sm text-[var(--color-text-2)]">
          {t('namespace.introMsg')}
        </p>
      </Card>
      <div className="px-6 pb-0">
        <div className="flex justify-between mb-[20px]">
          <div className="flex items-center">
            <Input
              allowClear
              value={searchValue}
              placeholder={t('common.search')}
              style={{ width: 250 }}
              onChange={(e) => setSearchValue(e.target.value)}
              onPressEnter={(e) => handleFilter(e.currentTarget.value)}
              onClear={() => {
                setSearchValue('');
                handleFilter('');
              }}
            />
          </div>
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" onClick={() => handleEdit('add')}>
              {t('common.addNew')}
            </Button>
          </PermissionWrapper>
        </div>
        <CustomTable
          size="middle"
          rowKey="id"
          columns={columns}
          loading={loading}
          dataSource={filteredList}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 410px)' }}
        />
        <OperateModal
          open={modalVisible}
          currentRow={currentRow}
          onClose={() => setModalVisible(false)}
          onSuccess={() => {
            setModalVisible(false);
            fetchNamespaces();
          }}
        />
      </div>
    </div>
  );
};

export default Namespace;
