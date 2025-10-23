'use client';
import React, { useEffect, useState, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { message, Button } from 'antd';
import CustomTable from '@/components/custom-table';
import { useDetailColumns } from '@/app/node-manager/hooks';
import useNodeManagerApi from '@/app/node-manager/api';
import useApiClient from '@/utils/request';
import type { Pagination, TableDataItem } from '@/app/node-manager/types';
import CollectorModal from '@/app/node-manager/components/sidecar/collectorModal';
import { ModalRef } from '@/app/node-manager/types';
import PermissionWrapper from '@/components/permission';

const Collectordetail = () => {
  const { t } = useTranslation();
  const { getPackageList, deletePackage } = useNodeManagerApi();
  const { isLoading } = useApiClient();
  const modalRef = useRef<ModalRef>(null);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [tableLoading, setTableLoading] = useState<boolean>(false);

  const getUrlParams = () => {
    const searchParams = new URLSearchParams(window.location.search);
    return {
      id: searchParams.get('id') || '',
      name: searchParams.get('name') || '',
      introduction: searchParams.get('introduction') || '',
      system: searchParams.get('system') || '',
      icon: searchParams.get('icon') || 'caijiqizongshu',
    };
  };

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
    const urlParams = getUrlParams();
    const info = {
      name: urlParams.name,
      system: [urlParams.system],
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

  const openModal = () => {
    const urlParams = getUrlParams();
    const formData = {
      id: urlParams.id,
      name: urlParams.name,
      description: urlParams.introduction,
      tagList: [urlParams.system],
      icon: urlParams.icon,
      executable_path: '',
      execute_parameters: '',
    };
    modalRef.current?.showModal({
      title: t('node-manager.packetManage.uploadPackage'),
      type: 'upload',
      form: formData,
      key: window.location.pathname.includes('collector')
        ? 'collector'
        : 'controller',
    });
  };

  const handleSubmit = () => {
    getTableData();
  };

  return (
    <div className="w-full h-[calc(100vh-230px)]">
      <div className="flex justify-end mb-[10px]">
        <PermissionWrapper requiredPermissions={['AddPacket']}>
          <Button type="primary" onClick={openModal}>
            {t('node-manager.packetManage.uploadPackage')}
          </Button>
        </PermissionWrapper>
      </div>

      <CustomTable
        scroll={{ y: 'calc(100vh - 376px)', x: 'calc(100vw - 320px)' }}
        columns={columns}
        dataSource={tableData}
        pagination={pagination}
        loading={tableLoading}
        rowKey="id"
        onChange={handleTableChange}
      />

      <CollectorModal ref={modalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default Collectordetail;
