'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Input, Select, Button, message, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useClientData } from '@/context/client';
import dayjs from 'dayjs';
import { useSecurityApi } from '@/app/system-manager/api/security';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';

const { Search } = Input;

interface ErrorLog {
  id: number;
  username: string;
  app: string;
  module: string;
  error_message: string;
  domain: string;
  created_at: string;
}

const ErrorLogsPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { clientData } = useClientData();
  const timeSelectorRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [dataSource, setDataSource] = useState<ErrorLog[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [filters, setFilters] = useState({
    username: '',
    app: [] as string[],
  });
  const [timeRange, setTimeRange] = useState<number[]>(() => {
    const end = Date.now();
    const start = end - 7 * 24 * 60 * 60 * 1000;
    return [start, end];
  });

  const { getErrorLogs } = useSecurityApi();

  const fetchErrorLogs = async (page = 1) => {
    setLoading(true);
    try {
      const params: any = {
        page,
        page_size: pagination.pageSize,
      };

      if (filters.username) {
        params.username = filters.username;
      }

      if (filters.app && filters.app.length > 0) {
        params.app = filters.app.join(',');
      }

      if (timeRange && timeRange.length === 2) {
        params.time_start = dayjs(timeRange[0]).toISOString();
        params.time_end = dayjs(timeRange[1]).toISOString();
      }

      const response = await getErrorLogs(params);
      setDataSource(response.results || []);
      setPagination(prev => ({
        ...prev,
        current: page,
        total: response.count || 0,
      }));
    } catch (error) {
      message.error(t('common.fetchFailed'));
      console.error('Failed to fetch error logs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchErrorLogs(1);
  }, []);

  const handleSearch = () => {
    fetchErrorLogs(1);
  };

  const handleReset = () => {
    setFilters({
      username: '',
      app: [],
    });
    const end = Date.now();
    const start = end - 7 * 24 * 60 * 60 * 1000;
    setTimeRange([start, end]);
    if (timeSelectorRef.current?.reset) {
      timeSelectorRef.current.reset();
    }
    setTimeout(() => {
      fetchErrorLogs(1);
    }, 0);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const columns = [
    {
      title: t('system.security.operationTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time: string) => convertToLocalizedTime(time),
    },
    {
      title: t('system.security.operator'),
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: t('system.security.operationModule'),
      dataIndex: 'app',
      key: 'app',
    },
    {
      title: t('system.security.errorModule'),
      dataIndex: 'module',
      key: 'module',
    },
    {
      title: t('system.security.errorSummary'),
      dataIndex: 'error_message',
      key: 'error_message',
      ellipsis: {
        showTitle: false,
      },
      render: (text: string) => (
        <Tooltip placement="topLeft" title={text}>
          {text}
        </Tooltip>
      ),
    },
  ];

  return (
    <div className="w-full h-full bg-[var(--color-bg)] p-4">
      {/* Filter Section */}
      <div className="mb-4 p-4 rounded">
        <div className="flex items-center justify-end gap-3">
          <Search
            placeholder={t('system.security.operatorPlaceholder')}
            value={filters.username}
            onChange={(e) => setFilters({ ...filters, username: e.target.value })}
            onSearch={handleSearch}
            allowClear
            className="w-48"
          />
          <Select
            mode="multiple"
            placeholder={t('system.security.operationModulePlaceholder')}
            value={filters.app}
            onChange={(value) => setFilters({ ...filters, app: value })}
            allowClear
            className="w-48"
            maxTagCount="responsive"
            options={clientData.map((item) => ({
              label: item.display_name,
              value: item.name,
            }))}
          />
          <TimeSelector
            ref={timeSelectorRef}
            showTime
            clearable
            onlyTimeSelect
            onChange={handleTimeChange}
            defaultValue={{
              selectValue: 7 * 24 * 60,
              rangePickerVaule: null
            }}
          />
          <Button type="primary" onClick={handleSearch}>
            {t('common.search')}
          </Button>
          <Button onClick={handleReset}>{t('common.reset')}</Button>
        </div>
      </div>

      {/* Table */}
      <CustomTable
        columns={columns}
        dataSource={dataSource}
        loading={loading}
        rowKey="id"
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `${t('common.total')} ${total} ${t('common.items')}`,
          onChange: (page: number, pageSize?: number) => {
            setPagination({ ...pagination, current: page, pageSize: pageSize || 20 });
            fetchErrorLogs(page);
          },
        }}
        scroll={{ x: 1200, y: 'calc(100vh - 400px)' }}
      />
    </div>
  );
};

export default ErrorLogsPage;
