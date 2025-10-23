'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import styles from './index.module.scss';
import OperateOid from './components/operateOid';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { NETWORK_DEVICE_OPTIONS } from '@/app/cmdb/constants/professCollection';
import { Button, Input, Select, Modal, message, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useOidApi } from '@/app/cmdb/api';

const { Option } = Select;

interface ListItem {
  id: string;
  oid: string;
  model: string;
  brand: string;
  device_type: string;
  built_in: boolean;
  [key: string]: any;
}

const OidLibrary: React.FC = () => {
  const { t } = useTranslation();

  const { getOidList, deleteOid } = useOidApi();

  const listCount = useRef<number>(0);
  const searchKeyRef = useRef<string>('');
  const deviceTypeRef = useRef<string[]>([]);
  const paginationRef = useRef({
    current: 1,
    total: 0,
    pageSize: 20,
  });

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
    searchKeyRef.current = searchKey;
  }, [searchKey]);

  useEffect(() => {
    deviceTypeRef.current = deviceType;
  }, [deviceType]);

  useEffect(() => {
    paginationRef.current = pagination;
  }, [pagination]);

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

  const delMap = useCallback(
    async (row: ListItem) => {
      Modal.confirm({
        title: t('common.delConfirm'),
        content: t('common.delConfirmCxt'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        centered: true,
        onOk: async () => {
          try {
            await deleteOid(row.id);
            message.success(t('successfullyDeleted'));

            const currentSearchKey = searchKeyRef.current;
            const currentDeviceType = deviceTypeRef.current;
            const currentPagination = paginationRef.current;
            if (currentPagination.current > 1 && listCount.current === 1) {
              const newCurrent = currentPagination.current - 1;
              setPagination((prev) => ({ ...prev, current: newCurrent }));
              getTableList({
                current: newCurrent,
                pageSize: currentPagination.pageSize,
                searchKey: currentSearchKey,
                deviceType: currentDeviceType,
              });
            } else {
              getTableList({
                current: currentPagination.current,
                pageSize: currentPagination.pageSize,
                searchKey: currentSearchKey,
                deviceType: currentDeviceType,
              });
            }
          } catch {
            message.error(t('OidLibrary.operateFailed'));
          }
        },
      });
    },
    [deleteOid]
  );

  const getTableList = async (
    params: {
      current?: number;
      pageSize?: number;
      searchKey?: string;
      deviceType?: string[];
    } = {}
  ) => {
    try {
      setTableLoading(true);

      const searchVal =
        params.searchKey !== undefined
          ? params.searchKey
          : searchKeyRef.current || searchKey;
      const deviceTypeVal =
        params.deviceType !== undefined
          ? params.deviceType
          : deviceTypeRef.current.length > 0
            ? deviceTypeRef.current
            : deviceType;

      const queryParams = {
        page:
          params.current !== undefined ? params.current : pagination.current,
        page_size:
          params.pageSize !== undefined ? params.pageSize : pagination.pageSize,
        model: filterType === 'version' ? searchVal : '',
        oid: filterType === 'oid' ? searchVal : '',
        brand: filterType === 'brand' ? searchVal : '',
        device_type: deviceTypeVal?.[0] || '',
      };

      const data = await getOidList(queryParams);
      setDataList(data.items || []);
      listCount.current = data.items?.length || 0;
      setPagination((prev) => ({
        ...prev,
        total: data.count || 0,
        current: params.current !== undefined ? params.current : prev.current,
      }));
    } catch {
      message.error('加载列表失败');
      return { data: [], total: 0, success: false };
    } finally {
      setTableLoading(false);
    }
  };

  const handleFilterChange = () => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    getTableList({
      current: 1,
      searchKey,
      deviceType,
    });
  };

  const handleFilterClear = () => {
    setSearchKey('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    getTableList({
      current: 1,
      searchKey: '',
      deviceType,
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
      deviceType: filters.device_type,
      searchKey,
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
        title: t('common.actions'),
        key: 'operation',
        width: 140,
        render: (text: any, record: ListItem) => (
          <div className="flex gap-4">
            <PermissionWrapper
              requiredPermissions={['Edit']}
              instPermissions={record.permission}
            >
              <Button
                type="link"
                size="small"
                disabled={record.built_in}
                onClick={() => operateMap('edit', record)}
              >
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper
              requiredPermissions={['Delete']}
              instPermissions={record.permission}
            >
              <Button
                type="link"
                size="small"
                disabled={record.built_in}
                onClick={() => delMap(record)}
              >
                {t('common.delete')}
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
    getTableList({
      current: newPagination.current,
      searchKey,
      deviceType,
    });
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
              placeholder={t('common.search')}
              style={{ width: 250 }}
              onChange={(e) => setSearchKey(e.target.value)}
              onPressEnter={handleFilterChange}
              onClear={handleFilterClear}
              className="!rounded-l-none"
            />
          </Space.Compact>
        </div>
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button type="primary" onClick={() => operateMap('add')}>
            {t('OidLibrary.newMapping')}
          </Button>
        </PermissionWrapper>
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
