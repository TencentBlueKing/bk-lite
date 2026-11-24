'use client';

import React, { useState, useEffect, useRef } from 'react';
import { message, Select, Button, Tag, Input, Drawer, Descriptions } from 'antd';
import { SearchOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useUserInfoContext } from '@/context/userInfo';
import CustomTable from '@/components/custom-table';
import FilterToolbar from '@/components/filter-toolbar';
import SystemManagerFillTable from '@/app/system-manager/components/system-manager-fill-table';
import TimeSelector from '@/components/time-selector';
import { useSecurityApi } from '@/app/system-manager/api/security';
import type { ColumnsType } from 'antd/es/table';
import type { TableRowSelection } from 'antd/es/table/interface';
import dayjs from 'dayjs';

const EMPTY_FILTERS: {
  status?: 'success' | 'failed';
  username?: string;
  source_ip?: string;
} = {};

interface UserLoginLog {
  id: number;
  username: string;
  login_time?: string;
  created_at?: string;
  login_method?: string;
  login_method_display?: string;
  used_otp?: boolean;
  os_info?: string;
  browser_info?: string;
  client_display?: string;
  source_ip?: string;
  status: string;
  status_display?: string;
  failure_reason?: string;
}

const UserLoginLogs: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { selectedGroup } = useUserInfoContext();
  const { getUserLoginLogs, exportUserLoginLogs } = useSecurityApi();
  const timeSelectorRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [logs, setLogs] = useState<UserLoginLog[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0
  });
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [timeRange, setTimeRange] = useState<number[]>(() => {
    const end = dayjs().valueOf();
    const start = dayjs().subtract(7, 'day').valueOf();
    return [start, end];
  });
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailRecord, setDetailRecord] = useState<UserLoginLog | null>(null);

  useEffect(() => {
    if (!selectedGroup?.id) {
      return;
    }
    fetchLogs();
  }, [selectedGroup?.id]);

  const unrecorded = t('system.security.outcomeUnrecorded');

  const formatRecorded = (value?: string) => value || unrecorded;

  const buildLoginFilters = (
    nextFilters = filters,
    nextTimeRange = timeRange,
  ) => {
    const params: Record<string, string> = {};
    if (nextFilters.status) {
      params.status = nextFilters.status;
    }
    if (nextFilters.username) {
      params.username = nextFilters.username;
    }
    if (nextFilters.source_ip) {
      params.source_ip = nextFilters.source_ip;
    }
    if (nextTimeRange && nextTimeRange.length === 2) {
      params.login_time_start = dayjs(nextTimeRange[0]).format('YYYY-MM-DD HH:mm:ss');
      params.login_time_end = dayjs(nextTimeRange[1]).format('YYYY-MM-DD HH:mm:ss');
    }
    return params;
  };

  const fetchLogs = async (
    page = 1,
    pageSize = 10,
    nextFilters = filters,
    nextTimeRange = timeRange,
  ) => {
    try {
      setLoading(true);
      const params: Record<string, string | number> = {
        page,
        page_size: pageSize,
        ...buildLoginFilters(nextFilters, nextTimeRange),
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
    setFilters(EMPTY_FILTERS);
    setTimeRange([]);
    if (timeSelectorRef.current?.reset) {
      timeSelectorRef.current.reset();
    }
    fetchLogs(1, pagination.pageSize, EMPTY_FILTERS, []);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const handleTableChange = (page: number, pageSize: number) => {
    fetchLogs(page, pageSize);
  };

  const rowSelection: TableRowSelection<UserLoginLog> = {
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

  const openDetail = (record: UserLoginLog) => {
    setDetailRecord(record);
    setDetailVisible(true);
  };

  const columns: ColumnsType<UserLoginLog> = [
    {
      title: t('system.security.loginTime'),
      dataIndex: 'login_time',
      key: 'login_time',
      width: 170,
      render: (text: string) => convertToLocalizedTime(text)
    },
    {
      title: t('system.security.loginAccount'),
      dataIndex: 'username',
      key: 'username',
      width: 140,
    },
    {
      title: t('system.security.loginMethod'),
      dataIndex: 'login_method_display',
      key: 'login_method',
      width: 130,
      render: (text: string) => formatRecorded(text)
    },
    {
      title: t('system.security.client'),
      dataIndex: 'client_display',
      key: 'client',
      width: 220,
      ellipsis: true,
      render: (text: string, record) =>
        formatRecorded(
          text || [record.os_info, record.browser_info].filter(Boolean).join(' ')
        )
    },
    {
      title: t('system.security.loginHost'),
      dataIndex: 'source_ip',
      key: 'source_ip',
      width: 140,
    },
    {
      title: t('system.security.loginStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string, record) => {
        return (
          <Tag color={status === 'success' ? 'green' : 'red'} className="m-0">
            {record.status_display}
          </Tag>
        );
      }
    },
    {
      title: t('common.detail'),
      key: 'detail',
      width: 80,
      fixed: 'right' as const,
      render: (_: unknown, record) => (
        <Button type="link" size="small" onClick={() => openDetail(record)}>
          {t('common.detail')}
        </Button>
      )
    }
  ];

  return (
    <div className="flex flex-col h-full w-full">
      <FilterToolbar className="w-full" contentClassName="w-full">
        <Select
          placeholder={t('system.security.loginStatus')}
          className="w-36"
          allowClear
          value={filters.status}
          onChange={(value) => setFilters({ ...filters, status: value })}
          options={[
            { label: t('system.security.loginStatusSuccess'), value: 'success' },
            { label: t('system.security.loginStatusFailed'), value: 'failed' }
          ]}
        />
        <Input
          placeholder={t('system.security.loginAccountPlaceholder')}
          className="w-48"
          allowClear
          value={filters.username}
          onChange={(e) => setFilters({ ...filters, username: e.target.value })}
        />
        <Input
          placeholder={t('system.security.sourceIpPlaceholder')}
          className="w-48"
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
        <div className="flex shrink-0 items-center gap-2">
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
            {t('common.search')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>
            {t('common.reset')}
          </Button>
          <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
            {t('common.export')}
          </Button>
        </div>
      </FilterToolbar>
      
      <SystemManagerFillTable>
        <CustomTable
          columns={columns}
          dataSource={logs}
          loading={loading}
          rowKey="id"
          rowSelection={rowSelection}
          scroll={{ x: 1000 }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `${t('common.total')} ${total} ${t('common.items')}`,
            onChange: handleTableChange,
            onShowSizeChange: handleTableChange
          }}
        />
      </SystemManagerFillTable>

      <Drawer
        title={t('common.detail')}
        width={560}
        open={detailVisible}
        onClose={() => {
          setDetailVisible(false);
          setDetailRecord(null);
        }}
        destroyOnHidden
      >
        {detailRecord && (
          <div className="flex flex-col gap-4">
            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.loginStatus')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.loginStatus')}>
                  <Tag color={detailRecord.status === 'success' ? 'green' : 'red'} className="m-0">
                    {formatRecorded(detailRecord.status_display)}
                  </Tag>
                </Descriptions.Item>
                {detailRecord.status === 'failed' && (
                  <Descriptions.Item label={t('system.security.failureReason')}>
                    <span className="text-red-500 font-medium">
                      {formatRecorded(detailRecord.failure_reason)}
                    </span>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </div>

            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.basicInfo')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.loginTime')}>
                  {detailRecord.login_time
                    ? convertToLocalizedTime(detailRecord.login_time)
                    : unrecorded}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.loginAccount')}>
                  {formatRecorded(detailRecord.username)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.loginMethod')}>
                  {formatRecorded(detailRecord.login_method_display)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.loginHost')}>
                  {formatRecorded(detailRecord.source_ip)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.client')}>
                  {formatRecorded(
                    detailRecord.client_display
                    || [detailRecord.os_info, detailRecord.browser_info].filter(Boolean).join(' ')
                  )}
                </Descriptions.Item>
              </Descriptions>
            </div>
          </div>
        )}
      </Drawer>

    </div>
  );
};

export default UserLoginLogs;
