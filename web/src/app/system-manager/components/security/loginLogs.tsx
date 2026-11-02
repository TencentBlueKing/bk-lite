'use client';

import React, { useState, useEffect, useRef } from 'react';
import { message, Select, Space, Button, Tag, Input } from 'antd';
import { SearchOutlined, DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { useSecurityApi } from '@/app/system-manager/api/security';
import type { ColumnsType } from 'antd/es/table';
import type { TableRowSelection } from 'antd/es/table/interface';
import dayjs from 'dayjs';

const UserLoginLogs: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getUserLoginLogs, exportUserLoginLogs } = useSecurityApi();
  const timeSelectorRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [logs, setLogs] = useState<any[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0
  });
  const [filters, setFilters] = useState<{
    status?: 'success' | 'failed';
    username?: string;
    source_ip?: string;
  }>({});
  const [timeRange, setTimeRange] = useState<number[]>(() => {
    const end = dayjs().valueOf();
    const start = dayjs().subtract(7, 'day').valueOf();
    return [start, end];
  });

  useEffect(() => {
    fetchLogs();
  }, []);

  const buildLoginFilters = () => {
    const params: Record<string, string> = {};
    if (filters.status) {
      params.status = filters.status;
    }
    if (filters.username) {
      params.username = filters.username;
    }
    if (filters.source_ip) {
      params.source_ip = filters.source_ip;
    }
    if (timeRange && timeRange.length === 2) {
      params.login_time_start = dayjs(timeRange[0]).format('YYYY-MM-DD HH:mm:ss');
      params.login_time_end = dayjs(timeRange[1]).format('YYYY-MM-DD HH:mm:ss');
    }
    return params;
  };

  const fetchLogs = async (page = 1, pageSize = 10) => {
    try {
      setLoading(true);
      const params: Record<string, string | number> = {
        page,
        page_size: pageSize,
        ...buildLoginFilters(),
      };

      const response = await getUserLoginLogs(params);
      setLogs(response.items || []);
      setPagination({
        current: page,
        pageSize,
        total: response.count || 0
      });
    } catch (error) {
      console.error('Failed to fetch user logs:', error);
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    fetchLogs(1, pagination.pageSize);
  };

  const handleReset = () => {
    setFilters({});
    setTimeRange([]);
    if (timeSelectorRef.current?.reset) {
      timeSelectorRef.current.reset();
    }
    setTimeout(() => {
      fetchLogs(1, pagination.pageSize);
    }, 0);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const handleTableChange = (page: number, pageSize: number) => {
    fetchLogs(page, pageSize);
  };

  const rowSelection: TableRowSelection<any> = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => {
      setSelectedRowKeys(keys);
    }
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const payload =
        selectedRowKeys.length > 0
          ? { selected_ids: selectedRowKeys }
          : buildLoginFilters();
      const blob = await exportUserLoginLogs(payload);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `login_logs_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`;
      link.click();
      window.URL.revokeObjectURL(url);
      message.success(t('common.exportSuccess'));
    } catch (error) {
      console.error('Export failed:', error);
      message.error(t('system.security.exportFailed'));
    } finally {
      setExporting(false);
    }
  };


  const columns: ColumnsType<any> = [
    {
      title: t('system.user.table.username'),
      dataIndex: 'username',
      key: 'username'
    },
    {
      title: t('system.security.loginTime'),
      dataIndex: 'login_time',
      key: 'login_time',
      render: (text: string) => convertToLocalizedTime(text)
    },
    {
      title: t('system.security.loginLocation'),
      dataIndex: 'location',
      key: 'location'
    },
    {
      title: t('system.security.operatingSystem'),
      dataIndex: 'os_info',
      key: 'os_info'
    },
    {
      title: t('system.security.browser'),
      dataIndex: 'browser_info',
      key: 'browser_info'
    },
    {
      title: t('system.security.loginHost'),
      dataIndex: 'source_ip',
      key: 'source_ip'
    },
    {
      title: t('system.security.loginStatus'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string, record: any) => {
        return (
          <Tag color={status === 'success' ? 'green' : 'red'}>
            {record.status_display}
          </Tag>
        );
      }
    }
  ];

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex-none flex justify-end mb-3">
        <Space wrap>
          <Select
              placeholder={t('system.security.loginStatus')}
              className="w-[120px]"
              allowClear
              value={filters.status}
              onChange={(value) => setFilters({ ...filters, status: value })}
              options={[
                { label: t('system.security.loginStatusSuccess'), value: 'success' },
                { label: t('system.security.loginStatusFailed'), value: 'failed' }
              ]}
            />
            <Input
              placeholder={t('system.user.table.username')}
              className="w-[200px]"
              allowClear
              value={filters.username}
              onChange={(e) => setFilters({ ...filters, username: e.target.value })}
            />
            <Input
              placeholder={t('system.security.sourceIpPlaceholder')}
              className="w-[200px]"
              allowClear
              value={filters.source_ip}
              onChange={(e) => setFilters({ ...filters, source_ip: e.target.value })}
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
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
              {t('common.search')}
            </Button>
            <Button onClick={handleReset}>
              {t('common.reset')}
            </Button>
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
              {t('common.export')}
            </Button>
          </Space>
      </div>
      
      <div className="flex-1 min-h-0 relative">
        <CustomTable
          columns={columns}
          dataSource={logs}
          loading={loading}
          rowKey="id"
          rowSelection={rowSelection}
          scroll={{ x: '100%' }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showQuickJumper: true,
            onChange: handleTableChange,
            onShowSizeChange: handleTableChange
          }}
        />
      </div>

    </div>
  );
};

export default UserLoginLogs;
