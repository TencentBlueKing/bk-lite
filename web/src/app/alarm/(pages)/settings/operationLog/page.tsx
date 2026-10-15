'use client';

import React, { useState, useEffect, useRef } from 'react';
import styles from './index.module.scss';
import type { Dayjs } from 'dayjs';
import CustomTable from '@/components/custom-table';
import TopSection from '@/components/top-section';
import SearchActionBar from '@/components/search-action-bar';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Select, DatePicker, message } from 'antd';
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
        created_at_after: allParams.dateRange?.[0]?.toISOString(),
        created_at_before: allParams.dateRange?.[1]?.toISOString(),
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
        // TODO(timezone): 与全站 convertToLocalizedTime 约定不一致——当前原样显示后端 DRF 输出的用户时区串，
        // 数值恰好正确，但属隐式依赖。后续统一为 convertToLocalizedTime 以消除约定分裂。
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
    <div className={`${styles.container} flex min-h-0 flex-1 flex-col`}>
      <TopSection
        className="mb-4"
        title={t('OperationLog.title')}
        content={t('OperationLog.description')}
      />
      <div className={`${styles.content} flex min-h-0 flex-1 flex-col`}>
        <SearchActionBar
          filters={(
            <>
              <Select
                allowClear
                showSearch
                className="w-[180px]"
                placeholder={t('OperationLog.operator')}
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
              <Select
                className="w-40"
                placeholder={t('OperationLog.operationType')}
                options={operationTypes}
                value={filters.type}
                onChange={(value) => handleFilterChange('type', value)}
                allowClear
              />
              <DatePicker.RangePicker
                className="w-[380px]"
                showTime
                value={filters.dateRange}
                onChange={(dates) => handleFilterChange('dateRange', dates)}
              />
            </>
          )}
          searchProps={{
            placeholder: t('OperationLog.summary'),
            allowClear: true,
            value: inputValue,
            onChange: handleInputChange,
            onPressEnter: handleInputSearch,
            onSearch: handleInputSearch,
            onClear: handleInputClear,
          }}
        />
        <div className="min-h-0 flex-1 overflow-hidden">
          <CustomTable
            size="middle"
            rowKey="id"
            loading={tableLoading}
            columns={columns}
            dataSource={dataList}
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
      </div>
    </div>
  );
};

export default OperationLog;
