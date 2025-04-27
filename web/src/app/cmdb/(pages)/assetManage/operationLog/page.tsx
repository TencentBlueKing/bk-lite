'use client';

import React, { useState, useEffect, useRef } from 'react';
import useApiClient from '@/utils/request';
import CustomTable from '@/components/custom-table';
import Introduction from '@/app/cmdb/components/introduction';
import styles from './index.module.scss';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { Input, Select, DatePicker, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/cmdb/context/common';
import { UserItem } from '@/app/cmdb/types/assetManage';

interface ListItem {
  id: string;
  oid: string;
  model: string;
  brand: string;
  device_type: string;
  built_in: boolean;
}

interface Filters {
  operator: undefined | string;
  type: undefined | string;
  message: string;
  dateRange: [Dayjs | null, Dayjs | null] | null;
}

const OperationLog: React.FC = () => {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const commonContext = useCommon();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [dataList, setDataList] = useState<ListItem[]>([]);
  const [columns, setColumns] = useState<any[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [filters, setFilters] = useState<Filters>({
    operator: undefined,
    type: undefined,
    message: '',
    dateRange: null,
  });

  const operationTypes = [
    { label: t('OperationLog.operationOpts.create_entity'), value: 'create_entity' },
    { label: t('OperationLog.operationOpts.update_entity'), value: 'update_entity' },
    { label: t('OperationLog.operationOpts.delete_entity'), value: 'delete_entity' },
    { label: t('OperationLog.operationOpts.execute'), value: 'execute' },
    { label: t('OperationLog.operationOpts.create_edge'), value: 'create_edge' },
    { label: t('OperationLog.operationOpts.delete_edge'), value: 'delete_edge' },
  ];

  const operators = userList.map(user => ({
    label: user.username,
    value: user.username
  }));

  useEffect(() => {
    setColumns(buildColumns());
    getTableList();
  }, []);

  const getTableList = async (params: any = {}) => {
    try {
      setTableLoading(true);
      const allParams = {
        ...pagination,
        ...filters,
        ...params,
      }
      const queryParams = {
        page: allParams.current,
        page_size: allParams.pageSize,
        operator: allParams.operator,
        type: allParams.type,
        message: allParams.message,
        created_at_after: allParams.dateRange?.[0]?.format('YYYY-MM-DD HH:mm:ss'),
        created_at_before: allParams.dateRange?.[1]?.format('YYYY-MM-DD HH:mm:ss'),
      };
      const data = await get('/cmdb/api/change_record', { params: queryParams });
      setDataList(data.items || []);
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

  const handleFilterChange = (key: string, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPagination(prev => ({ ...prev, current: 1 }));
    getTableList({ 
      ...filters,
      ...pagination,
      [key]: value,
      current: 1,
    });
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  const handleInputSearch = () => {
    handleFilterChange('message', inputValue);
  };

  const handleInputClear = () => {
    setInputValue('');
    handleFilterChange('message', '');
  };

  const handleTableChange = (newPagination: any) => {
    setPagination(newPagination);
    getTableList({
      ...newPagination,
    });
  };

  const buildColumns = () => {
    return [
      {
        title: t('OperationLog.operator'),
        dataIndex: 'operator',
        key: 'operator',
        width: 160,
      },
      {
        title: t('OperationLog.operationObject'),
        dataIndex: 'model_object',
        key: 'model_object',
        width: 160,
      },
      {
        title: t('OperationLog.operationType'),
        dataIndex: 'type',
        key: 'type',
        width: 120,
        render: (type: string) => t(`OperationLog.operationOpts.${type}`),
      },
      {
        title: t('OperationLog.operationTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 240,
        render: (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm:ss'),
      },
      {
        title: t('OperationLog.summary'),
        dataIndex: 'message',
        key: 'message',
        width: 300,
      }
    ];
  };

  return (
    <div className={styles.container}>
      <Introduction
        title={t('OperationLog.title')}
        message={t('OperationLog.description')}
      />
      <div className={styles.content}>
        <div className={`${styles.filterWrapper} mb-[20px]`}>
          <div className="flex items-center gap-4">
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">{t('OperationLog.operator')}:</label>
              <Select
                style={{ width: 140 }}
                placeholder={t('common.selectMsg')}
                options={operators}
                value={filters.operator}
                onChange={(value) => handleFilterChange('operator', value)}
                allowClear
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">{t('OperationLog.operationType')}:</label>
              <Select
                style={{ width: 140 }}
                placeholder={t('common.selectMsg')}
                options={operationTypes}
                value={filters.type}
                onChange={(value) => handleFilterChange('type', value)}
                allowClear
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">{t('OperationLog.summary')}:</label>
              <Input
                style={{ width: 240 }}
                placeholder={t('common.inputMsg')}
                value={inputValue}
                onChange={handleInputChange}
                onPressEnter={handleInputSearch}
                onClear={handleInputClear}
                allowClear
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">{t('OperationLog.timeRange')}:</label>
              <DatePicker.RangePicker
                style={{ width: 400 }}
                showTime
                value={filters.dateRange}
                onChange={(dates) => handleFilterChange('dateRange', dates)}
              />
            </div>
          </div>
        </div>
        <CustomTable
          size="middle"
          rowKey="id"
          loading={tableLoading}
          columns={columns}
          dataSource={dataList}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 470px)' }}
        />
      </div>
    </div>
  );
};

export default OperationLog;
