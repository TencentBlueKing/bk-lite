'use client';
import React, { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import { message } from 'antd';
import CustomTable from '@/components/custom-table';
import { useDetailColumns } from '@/app/node-manager/hooks';
import useApiNode from '@/app/node-manager/api';
import useApiClient from '@/utils/request';
import type { Pagination, TableDataItem } from '@/app/node-manager/types';

const Collectordetail = () => {
  const { t } = useTranslation();
  const { getPackageList, deletePackage } = useApiNode();
  const { isLoading } = useApiClient();
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [tableLoading, setTableLoading] = useState<boolean>(false);

  const columns = useDetailColumns({
    handleDelete: (id) => handleDelete(id),
  });

  useEffect(() => {
    if (!isLoading) {
      getTableData();
    }
  }, [isLoading]);

  useEffect(() => {
    if (!isLoading) getTableData();
  }, [pagination.current, pagination.pageSize]);

  const getTableData = async () => {
    const searchParams = new URLSearchParams(window.location.search);
    const info = {
      name: searchParams.get('name') || '',
      system: [searchParams.get('system') || ''],
    };
    try {
      setTableLoading(true);
      const param = {
        object: info.name,
        os: info.system[0],
        page: pagination.current,
        page_size: pagination.pageSize,
      };
      const getPackage = getPackageList(param);
      const res = await Promise.all([getPackage]);
      const packageInfo = res[0];
      setTableData(packageInfo?.items || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: packageInfo?.count || 0,
        current: 1,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const handleDelete = (id: number) => {
    setTableLoading(true);
    deletePackage(id)
      .then(() => {
        getTableData();
        message.success(t('common.delSuccess'));
      })
      .catch(() => {
        setTableLoading(false);
      });
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  return (
    <div className="w-full h-[calc(100vh-230px)]">
      <CustomTable
        scroll={{ y: 'calc(100vh - 336px)', x: 'calc(100vw - 320px)' }}
        columns={columns}
        dataSource={tableData}
        pagination={pagination}
        loading={tableLoading}
        rowKey="id"
        onChange={handleTableChange}
      />
    </div>
  );
};

export default Collectordetail;
