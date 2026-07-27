'use client';

import React, { useState, useEffect, useRef } from 'react';
import styles from './index.module.scss';
import type { Dayjs } from 'dayjs';
import CustomTable from '@/components/custom-table';
import Introduction from '@/components/introduction';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Input, Select, DatePicker, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/alarm/context/common';
import { UserItem, AlarmLogItem } from '@/app/alarm/types/types';

interface Filters {
  operator?: string;
  type?: string;
  message: string;
  dateRange: [Dayjs | null, Dayjs | null] | null;
}

const OperationLog: React.FC = () => {
  const { t } = useTranslation();
  const { getLogList } = useSettingApi();
  const commonContext = useCommon();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [dataList, setDataList] = useState<AlarmLogItem[]>([]);
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
    { label: t('settings.operationLog.operationOpts.add'), value: 'add' },
    { label: t('settings.operationLog.operationOpts.modify'), value: 'modify' },
    { label: t('settings.operationLog.operationOpts.delete'), value: 'delete' },
    {
      label: t('settings.operationLog.operationOpts.execute'),
      value: 'execute',
    },
  ];

  const operators = userList.map((user: UserItem) => {
    const labelText = `${user.display_name} (${user.username})`;
    return {
      value: user.username,
      label: (
        <EllipsisWithTooltip
          text={labelText}
          className="whitespace-nowrap overflow-hidden text-ellipsis break-all"
        />
      ),
    };
  });

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
      };
      const queryParams = {
        page: allParams.current,
        page_size: allParams.pageSize,
        operator: allParams.operator,
        action: allParams.type,
        overview: allParams.message,
        created_at_after: allParams.dateRange?.[0]?.format(
          'YYYY-MM-DD HH:mm:ss'
        ),
        created_at_before: allParams.dateRange?.[1]?.format(
          'YYYY-MM-DD HH:mm:ss'
        ),
      };
      const data: any = await getLogList(queryParams);
      setDataList((data.items as AlarmLogItem[]) || []);
      setPagination((prev) => ({
        ...prev,
        total: data.count || 0,
      }));
    } catch {
      message.error(t('common.loadListFailed'));
      return { data: [], total: 0, success: false };
    } finally {
      setTableLoading(false);
    }
  };

  const handleFilterChange = (key: string, value: any) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPagination((prev) => ({ ...prev, current: 1 }));
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
        dataIndex: 'operator_object',
        key: 'operator_object',
        width: 160,
      },
      {
        title: t('OperationLog.operationType'),
        dataIndex: 'action',
        key: 'action',
        width: 120,
        render: (action: string) =>
          t(`settings.operationLog.operationOpts.${action}`),
      },
      {
        title: t('OperationLog.operationTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 200,
      },
      {
        title: t('OperationLog.summary'),
        dataIndex: 'overview',
        key: 'overview',
        width: 300,
      },
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
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.operator')}:
              </label>
              <Select
                allowClear
                showSearch
                style={{ width: 180 }}
                placeholder={t('common.selectTip')}
                options={operators}
                value={filters.operator}
                onChange={(value) => handleFilterChange('operator', value)}
                filterOption={(input, opt: any) => {
                  if (typeof opt?.label?.props?.text === 'string') {
                    return opt?.label?.props?.text
                      ?.toLowerCase()
                      .includes(input.toLowerCase());
                  }
                  return true;
                }}
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.operationType')}:
              </label>
              <Select
                style={{ width: 160 }}
                placeholder={t('common.selectTip')}
                options={operationTypes}
                value={filters.type}
                onChange={(value) => handleFilterChange('type', value)}
                allowClear
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.summary')}:
              </label>
              <Input
                style={{ width: 220 }}
                placeholder={t('common.inputTip')}
                value={inputValue}
                onChange={handleInputChange}
                onPressEnter={handleInputSearch}
                onClear={handleInputClear}
                allowClear
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.timeRange')}:
              </label>
              <DatePicker.RangePicker
                style={{ width: 380 }}
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
          scroll={{ y: 'calc(100vh - 490px)' }}
        />
      </div>
    </div>
  );
};

export default OperationLog;
