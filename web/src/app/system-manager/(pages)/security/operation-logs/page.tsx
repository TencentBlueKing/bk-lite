'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Input, Select, Button, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useClientData } from '@/context/client';
import dayjs from 'dayjs';
import { useSecurityApi } from '@/app/system-manager/api/security';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';

const { Search } = Input;

interface OperationLog {
  id: number;
  username: string;
  source_ip: string;
  app: string;
  action_type: string;
  action_type_display: string;
  summary: string;
  domain: string;
  operation_time: string;
  created_at: string;
}

const OperationLogsPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { clientData } = useClientData();
  const timeSelectorRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [dataSource, setDataSource] = useState<OperationLog[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [filters, setFilters] = useState({
    username: '',
    app: '',
    actionType: '',
  });
  const [timeRange, setTimeRange] = useState<number[]>([]);

  const { getOperationLogs } = useSecurityApi();

  const fetchOperationLogs = async (page = 1) => {
    setLoading(true);
    try {
      const params: any = {
        page,
        page_size: pagination.pageSize,
      };

      if (filters.username) {
        params.username = filters.username;
      }

      if (filters.app) {
        params.app = filters.app;
      }

      if (filters.actionType) {
        params.action_type = filters.actionType;
      }

      if (timeRange && timeRange.length === 2) {
        params.start_time = dayjs(timeRange[0]).format('YYYY-MM-DD HH:mm:ss');
        params.end_time = dayjs(timeRange[1]).format('YYYY-MM-DD HH:mm:ss');
      }

      const response = await getOperationLogs(params);
      setDataSource(response.items || []);
      setPagination(prev => ({
        ...prev,
        current: page,
        total: response.count || 0,
      }));
    } catch (error) {
      message.error(t('common.fetchFailed'));
      console.error('Failed to fetch operation logs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOperationLogs(1);
  }, []);

  const handleSearch = () => {
    fetchOperationLogs(1);
  };

  const handleReset = () => {
    setFilters({
      username: '',
      app: '',
      actionType: '',
    });
    setTimeRange([]);
    if (timeSelectorRef.current?.reset) {
      timeSelectorRef.current.reset();
    }
    setTimeout(() => {
      fetchOperationLogs(1);
    }, 0);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const columns = [
    {
      title: t('system.security.operationTime'),
      dataIndex: 'operation_time',
      key: 'operation_time',
      render: (time: string) => convertToLocalizedTime(time),
    },
    {
      title: t('system.security.operator'),
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: t('system.security.sourceIp'),
      dataIndex: 'source_ip',
      key: 'source_ip',
    },
    {
      title: t('system.security.operationModule'),
      dataIndex: 'app',
      key: 'app',
    },
    {
      title: t('system.security.operationType'),
      dataIndex: 'action_type_display',
      key: 'action_type_display',
    },
    {
      title: t('system.security.operationDetail'),
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
    },
  ];

  return (
    <div className="w-full h-full bg-[var(--color-bg)] p-4">
      {/* Filter Section */}
      <div className="mb-4 bg-white p-4 rounded">
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
            placeholder={t('system.security.operationModulePlaceholder')}
            value={filters.app || undefined}
            onChange={(value) => setFilters({ ...filters, app: value })}
            allowClear
            className="w-48"
            options={clientData.map((item) => ({
              label: item.display_name,
              value: item.name,
            }))}
          />
          <Select
            placeholder={t('system.security.operationTypePlaceholder')}
            value={filters.actionType || undefined}
            onChange={(value) => setFilters({ ...filters, actionType: value })}
            allowClear
            className="w-48"
            options={[
              { label: t('system.security.actionTypeCreate'), value: 'create' },
              { label: t('system.security.actionTypeUpdate'), value: 'update' },
              { label: t('system.security.actionTypeDelete'), value: 'delete' },
              { label: t('system.security.actionTypeExecute'), value: 'execute' },
            ]}
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
            fetchOperationLogs(page);
          },
        }}
        scroll={{ x: 1200, y: 'calc(100vh - 400px)' }}
      />
    </div>
  );
};

export default OperationLogsPage;
