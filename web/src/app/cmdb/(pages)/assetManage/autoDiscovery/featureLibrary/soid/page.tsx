'use client';

import React, { useState, useEffect, useRef } from 'react';
import styles from './index.module.scss';
import OperateOid from './components/operateOid';
import useApiClient from '@/utils/request';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { NETWORK_DEVICE_OPTIONS } from '@/app/cmdb/constants/professCollection';
import { Button, Input, Select, Modal, message, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';

const { Option } = Select;

interface ListItem {
  id: string;
  oid: string;
  model: string;
  brand: string;
  device_type: string;
  built_in: boolean;
}

const OidLibrary: React.FC = () => {
  const { t } = useTranslation();
  const { get, del } = useApiClient();
  const listCount = useRef<number>(0);
  const deviceTypeList = NETWORK_DEVICE_OPTIONS;
  const [deviceType, setDeviceType] = useState<string[]>([]);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [operateVisible, setOperateVisible] = useState<boolean>(false);
  const [searchKey, setSearchKey] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('version');
  const [dataList, setDataList] = useState<ListItem[]>([]);
  const [columns, setColumns] = useState<any[]>([]);
  const [currentRow, setCurrentRow] = useState<ListItem | null>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  useEffect(() => {
    getTableList();
  }, []);

  const operateMap = (type: 'add' | 'edit', row?: ListItem) => {
    if (type === 'edit' && row) {
      setCurrentRow({
        id: row.id,
        model: row.model,
        brand: row.brand,
        device_type: row.device_type,
        oid: row.oid,
        built_in: row.built_in,
      });
    } else {
      setCurrentRow(null);
    }
    setOperateVisible(true);
  };

  const delMap = async (row: ListItem) => {
    Modal.confirm({
      title: t('deleteTitle'),
      content: t('deleteContent'),
      okText: t('confirm'),
      cancelText: t('cancel'),
      centered: true,
      onOk: async () => {
        try {
          await del(`/cmdb/api/oid/${row.id}/`);
          message.success(t('successfullyDeleted'));
          if (pagination.current > 1 && listCount.current === 1) {
            setPagination((prev) => ({ ...prev, current: prev.current - 1 }));
            getTableList({
              current: pagination.current - 1,
              pageSize: pagination.pageSize,
            });
          } else {
            getTableList();
          }
        } catch {
          message.error(t('OidLibrary.operateFailed'));
        }
      },
    });
  };

  const getTableList = async (params: any = {}) => {
    try {
      setTableLoading(true);
      const searchVal =
        params.searchKey !== undefined ? params.searchKey : searchKey;
      const deviceTypeVal = params.device_type || deviceType;
      const queryParams = {
        page: params.current || pagination.current,
        page_size: params.pageSize || pagination.pageSize,
        model: filterType === 'version' ? searchVal : '',
        oid: filterType === 'oid' ? searchVal : '',
        brand: filterType === 'brand' ? searchVal : '',
        device_type: deviceTypeVal?.[0] || '',
      };
      const data = await get('/cmdb/api/oid/', { params: queryParams });
      setDataList(data.items || []);
      listCount.current = data.items?.length || 0;
      setPagination((prev) => ({
        ...prev,
        total: data.count || 0,
      }));
    } catch {
      message.error('加载列表失败');
      return { data: [], total: 0, success: false };
    } finally {
      setTableLoading(false);
    }
  };

  const handleFilterChange = () => {
    setPagination({ ...pagination, current: 1 });
    getTableList({
      ...pagination,
      current: 1,
      device_type: deviceType,
    });
  };

  const handleFilterClear = () => {
    setPagination({ ...pagination, current: 1 });
    getTableList({
      ...pagination,
      current: 1,
      searchKey: '',
      device_type: deviceType,
    });
  };

  const handleTableChange = (newPagination: any, filters: any) => {
    let curPage = newPagination;
    if (filters.device_type?.[0] !== deviceType?.[0]) {
      curPage = {
        ...newPagination,
        current: 1,
      };
    }
    setPagination(curPage);
    setDeviceType(filters.device_type || []);
    getTableList({
      ...curPage,
      device_type: filters.device_type,
    });
  };

  const getDeviceType = (id: string) => {
    return deviceTypeList.find((item) => item.key === id)?.label || '--';
  };

  const buildColumns = () => {
    const deviceTypeFilters = deviceTypeList.map((item) => ({
      text: item.label,
      value: item.key,
    }));

    return [
      {
        title: t('OidLibrary.model'),
        dataIndex: 'model',
        key: 'model',
      },
      {
        title: t('OidLibrary.brand'),
        dataIndex: 'brand',
        key: 'brand',
      },
      {
        title: 'OID',
        dataIndex: 'oid',
        key: 'oid',
      },
      {
        title: t('OidLibrary.deviceType'),
        dataIndex: 'device_type',
        key: 'device_type',
        filters: deviceTypeFilters,
        filterMultiple: false,
        render: (type: string) => getDeviceType(type),
      },
      {
        title: t('action'),
        key: 'operation',
        width: 140,
        render: (text: any, row: ListItem) => (
          <div className="flex gap-4">
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                size="small"
                disabled={row.built_in}
                onClick={() => operateMap('edit', row)}
              >
                {t('edit')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Button
                type="link"
                size="small"
                disabled={row.built_in}
                onClick={() => delMap(row)}
              >
                {t('delete')}
              </Button>
            </PermissionWrapper>
          </div>
        ),
      },
    ];
  };

  useEffect(() => {
    setColumns(buildColumns());
  }, [deviceTypeList]);

  const handleModalClose = () => {
    setOperateVisible(false);
    setCurrentRow(null);
  };

  const handleModalSubmit = () => {
    const newPagination = pagination;
    if (!currentRow) {
      newPagination.current = 1;
    }
    handleModalClose();
    setPagination(newPagination);
    getTableList(newPagination);
  };

  const handleFilterTypeChange = (value: string) => {
    setFilterType(value);
    setSearchKey('');
  };

  return (
    <div className="oid-library-container">
      <div className="nav-box flex justify-between mb-[20px]">
        <div className={`flex items-center ${styles.wrapper}`}>
          <Space.Compact>
            <Select
              value={filterType}
              style={{ width: 90 }}
              onChange={handleFilterTypeChange}
              className="!rounded-r-none"
            >
              <Option value="version">{t('OidLibrary.model')}</Option>
              <Option value="oid">OID</Option>
              <Option value="brand">{t('OidLibrary.brand')}</Option>
            </Select>
            <Input
              allowClear
              value={searchKey}
              placeholder={t('assetSearchTxt')}
              style={{ width: 250 }}
              onChange={(e) => setSearchKey(e.target.value)}
              onPressEnter={handleFilterChange}
              onClear={handleFilterClear}
              className="!rounded-l-none"
            />
          </Space.Compact>
        </div>
        <Button type="primary" onClick={() => operateMap('add')}>
          {t('OidLibrary.newMapping')}
        </Button>
      </div>
      <CustomTable
        size="middle"
        rowKey="id"
        loading={tableLoading}
        columns={columns}
        dataSource={dataList}
        pagination={pagination}
        onChange={handleTableChange}
        scroll={{ y: 'calc(100vh - 450px)' }}
      />
      <OperateOid
        visible={operateVisible}
        data={currentRow}
        deviceTypeList={deviceTypeList}
        onCancel={handleModalClose}
        onOk={handleModalSubmit}
      />
    </div>
  );
};

export default OidLibrary;
