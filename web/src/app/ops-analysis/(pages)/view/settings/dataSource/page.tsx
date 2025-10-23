'use client';

import React, { useState, useEffect } from 'react';
import type { TablePaginationConfig } from 'antd/es/table';
import OperateModal from './operateModal';
import CustomTable from '@/components/custom-table';
import { Button, Input, Card, message, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';

const Datasource: React.FC = () => {
  const { t } = useTranslation();
  const { getDataSourceList, deleteDataSource } = useDataSourceApi();
  const [searchKey, setSearchKey] = useState('');
  const [searchValue, setSearchValue] = useState('');
  const [filteredList, setFilteredList] = useState<DatasourceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [currentRow, setCurrentRow] = useState<DatasourceItem | undefined>();
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  // 获取数据源列表
  const fetchDataSources = async (
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
        params.search = currentSearchKey.trim();
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
    fetchDataSources(key, newPagination);
  };

  const handleEdit = (type: 'add' | 'edit', row?: DatasourceItem) => {
    if (type === 'edit' && row) {
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

  const columns = [
    { title: t('dataSource.name'), dataIndex: 'name', key: 'name', width: 150 },
    { title: 'REST API', dataIndex: 'rest_api', key: 'rest_api', width: 150 },
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
      render: (text: string) => (text ? new Date(text).toLocaleString() : '-'),
    },
    {
      title: t('common.edit'),
      key: 'operation',
      width: 100,
      render: (_: unknown, row: DatasourceItem) => (
        <div className="space-x-4">
          <Button
            type="link"
            size="small"
            onClick={() => handleEdit('edit', row)}
          >
            {t('common.edit')}
          </Button>
          <Button type="link" size="small" onClick={() => handleDelete(row)}>
            {t('common.delete')}
          </Button>
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
          <Button type="primary" onClick={() => handleEdit('add')}>
            {t('common.addNew')}
          </Button>
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
            fetchDataSources();
          }}
        />
      </div>
    </div>
  );
};

export default Datasource;
